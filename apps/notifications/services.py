import hashlib
import json
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from apps.submissions.models import SubmissionActivity

from . import resend_client
from .models import EmailDeliveryEvent, EmailSendAttempt, EmailSuppression
from .models import EmailNotification as Email
from .recipients import respondent, settings_for, valid_email

BLOCKED = {Email.Status.BOUNCED, Email.Status.COMPLAINED, Email.Status.SUPPRESSED}
EVENTS = {
    f"email.{name.lower()}": name
    for name in (
        "SENT",
        "DELIVERED",
        "DELIVERY_DELAYED",
        "BOUNCED",
        "COMPLAINED",
        "FAILED",
        "SUPPRESSED",
    )
}
RANK = {
    "PENDING": 0,
    "SENDING": 0,
    "SENT": 1,
    "DELIVERY_DELAYED": 2,
    "FAILED": 3,
    "DELIVERED": 4,
    "SUPPRESSED": 5,
    "BOUNCED": 6,
    "COMPLAINED": 7,
    "SKIPPED": 8,
}
SUBJECTS = {
    Email.Event.SUBMISSION_RECEIVED: "Nueva respuesta recibida",
    Email.Event.SUBMISSION_VALIDATED: "Tu solicitud fue aprobada",
    Email.Event.SUBMISSION_REJECTED: "Tu solicitud requiere correcciones",
}


def lock_provider_message(message_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [message_id])


def queue_notification(submission, review=None):
    if review and not (
        review.previous_status == "UNDER_REVIEW" and review.status in {"VALIDATED", "REJECTED"}
    ):
        return None
    event = f"SUBMISSION_{review.status}" if review else Email.Event.SUBMISSION_RECEIVED
    config = settings_for(submission.form)
    if review:
        recipient, reason = respondent(submission, config["respondent_email_stable_key"])
        enabled = config[f"notify_respondent_on_{review.status.lower()}"]
        kind = Email.Recipient.RESPONDENT
    else:
        recipient = valid_email(submission.form.created_by.email)
        reason = "" if recipient else "El creador del formulario no tiene un correo válido."
        enabled = config["notify_internal_on_submission"]
        kind = Email.Recipient.INTERNAL
    if not enabled:
        reason = "Notificación desactivada para este formulario."
    if not settings.EMAIL_NOTIFICATIONS_ENABLED:
        reason = "Envíos de correo desactivados en este entorno."
    key = hashlib.sha256(
        f"{event}:{review.pk if review else submission.pk}:{recipient}".encode()
    ).hexdigest()
    is_test = bool(settings.EMAIL_TEST_RECIPIENT)
    if recipient and is_test:
        recipient = settings.EMAIL_TEST_RECIPIENT
    notification, created = Email.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "submission": submission,
            "review": review,
            "form": submission.form,
            "form_name": submission.form.name,
            "event_type": event,
            "recipient_kind": kind,
            "recipient_email": recipient,
            "is_test": is_test,
            "subject": f"{SUBJECTS[event]} · {submission.form.name}".replace("\r", " ").replace(
                "\n", " "
            ),
            "status": Email.Status.SKIPPED if reason else Email.Status.PENDING,
            "last_error": reason,
        },
    )
    if created and not reason:
        transaction.on_commit(lambda pk=notification.pk: send_notification(pk), robust=True)
    return notification


def payload_for(notification):
    context = {
        "notification": notification,
        "short_id": str(notification.submission_id)[:8],
        "submitted_at": notification.submission.submitted_at,
        "reason": notification.review.note if notification.review else "",
        "detail_url": settings.PUBLIC_BASE_URL
        + reverse("admin:submissions_submission_detail", args=[notification.submission_id]),
        "form_url": settings.PUBLIC_BASE_URL + reverse("public_form", args=[notification.form_id]),
    }
    template = notification.event_type.lower()
    return {
        "from": settings.EMAIL_FROM,
        "to": [notification.recipient_email],
        "subject": notification.subject,
        "html": render_to_string(f"notifications/emails/{template}.html", context),
        "text": render_to_string(f"notifications/emails/{template}.txt", context),
    }


def can_retry(notification):
    return (
        notification.status == Email.Status.FAILED
        and (
            bool(notification.provider_message_id)
            or not notification.first_attempt_at
            or timezone.now() < notification.first_attempt_at + timedelta(hours=23)
        )
        and notification.last_error
        != "El contenido cambió desde el primer intento; se requiere revisión administrativa."
    )


def send_notification(notification_id, retry=False):
    # Even a caller outside the normal on_commit path cannot perform network I/O
    # inside an enclosing database transaction.
    if connection.in_atomic_block or not settings.EMAIL_NOTIFICATIONS_ENABLED:
        return False
    with transaction.atomic():
        item = (
            Email.objects.select_for_update(of=("self",))
            .select_related("submission", "review", "form")
            .get(pk=notification_id)
        )
        now = timezone.now()
        if item.status == Email.Status.SENDING and item.lease_until and item.lease_until <= now:
            item.status = Email.Status.FAILED
            item.last_error = "El proceso de envío fue interrumpido."
            item.send_attempts.filter(status=Email.Status.SENDING).update(
                status=Email.Status.FAILED, finished_at=now, error=item.last_error
            )
        elif item.status != Email.Status.PENDING and not (retry and can_retry(item)):
            return False
        if (
            item.first_attempt_at
            and not item.provider_message_id
            and now >= item.first_attempt_at + timedelta(hours=23)
        ):
            item.status = Email.Status.FAILED
            item.last_error = (
                "La ventana segura de reintento venció; revisa Resend antes de un nuevo envío."
            )
            item.save()
            return False
        if (
            not item.submission_id
            or item.submission.deleted_at
            or not item.form_id
            or item.form.deleted_at
            or (item.event_type != Email.Event.SUBMISSION_RECEIVED and not item.review_id)
        ):
            item.status, item.last_error = (
                Email.Status.SKIPPED,
                "La respuesta, formulario o revisión ya no está disponible.",
            )
            item.save()
            return False
        if EmailSuppression.objects.filter(email=item.recipient_email).exists():
            item.status, item.last_error = (
                Email.Status.SUPPRESSED,
                "El destinatario tiene un rebote, queja o supresión registrados.",
            )
            item.save()
            return False
        # A provider-confirmed failure may start a new delivery generation.
        # Ambiguous transport failures retain the same provider idempotency key.
        if item.status == Email.Status.FAILED and item.provider_message_id:
            item.generation += 1
            item.provider_message_id = None
            item.first_attempt_at = None
            item.payload_hash = ""
            item.sent_at = item.delivered_at = item.last_event_at = None
            item.last_provider_event = ""
        try:
            payload = payload_for(item)
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        except Exception:
            item.status, item.last_error = (
                Email.Status.FAILED,
                "No se pudo preparar el correo. Revisa la configuración.",
            )
            item.save()
            return False
        if item.payload_hash and digest != item.payload_hash:
            item.status = Email.Status.FAILED
            item.last_error = (
                "El contenido cambió desde el primer intento; se requiere revisión administrativa."
            )
            item.save()
            return False
        item.payload_hash = digest
        item.first_attempt_at = item.first_attempt_at or now
        item.lease_until = now + timedelta(minutes=2)
        item.attempts += 1
        item.status, item.last_error = Email.Status.SENDING, ""
        item.save()
        attempt = EmailSendAttempt.objects.create(
            notification=item, number=item.attempts, generation=item.generation
        )
        delivery_key = f"{item.idempotency_key}:{item.generation}"
    try:
        message_id = resend_client.send(payload, delivery_key)
        if not isinstance(message_id, str) or not message_id or len(message_id) > 100:
            raise ValueError("Invalid provider identifier")
    except Exception as error:
        with transaction.atomic():
            item = Email.objects.select_for_update().get(pk=notification_id)
            attempt.status, attempt.error = Email.Status.FAILED, resend_client.safe_error(error)
            attempt.finished_at = timezone.now()
            attempt.save()
            if (
                item.generation == attempt.generation
                and item.attempts == attempt.number
                and item.status == Email.Status.SENDING
            ):
                item.status, item.last_error = Email.Status.FAILED, attempt.error
                item.lease_until = None
                item.save()
        return False
    with transaction.atomic():
        lock_provider_message(message_id)
        item = Email.objects.select_for_update().get(pk=notification_id)
        attempt.status, attempt.provider_message_id = Email.Status.SENT, message_id
        attempt.finished_at = timezone.now()
        attempt.save()
        if item.generation != attempt.generation:
            return True
        item.provider_message_id = message_id
        first_sent = not item.sent_at
        item.sent_at = item.sent_at or timezone.now()
        item.lease_until, item.last_error = None, ""
        if item.status in {Email.Status.SENDING, Email.Status.FAILED}:
            item.status = Email.Status.SENT
        item.save()
        if item.submission_id and first_sent:
            SubmissionActivity.objects.create(
                submission_id=item.submission_id,
                event_type="email_sent",
                description=f"{item.get_event_type_display()} · correo enviado",
            )
        reconcile_events(item)
    return True


def apply_event(item, event):
    first_seen = event.notification_id is None
    event.notification = item
    event.save(update_fields=["notification"])
    status = EVENTS[event.event_type]
    if status in BLOCKED:
        EmailSuppression.objects.get_or_create(
            email=item.recipient_email, defaults={"reason": status}
        )
    if event.provider_message_id != item.provider_message_id:
        return
    if RANK[status] >= RANK[item.status]:
        item.status = status
        item.last_provider_event = event.event_type
        item.last_error = (
            "" if status in {"SENT", "DELIVERED"} else dict(Email.Status.choices)[status]
        )
    item.last_event_at = max(filter(None, [item.last_event_at, event.occurred_at]))
    if status == Email.Status.DELIVERED:
        item.delivered_at = item.delivered_at or event.occurred_at
    item.save()
    if item.submission_id and first_seen and status != Email.Status.SENT:
        SubmissionActivity.objects.create(
            submission_id=item.submission_id,
            event_type="email_delivery",
            description=f"{item.get_event_type_display()} · {dict(Email.Status.choices)[status]}",
        )


def reconcile_events(item):
    for event in EmailDeliveryEvent.objects.filter(
        provider_message_id=item.provider_message_id
    ).order_by("occurred_at", "pk"):
        apply_event(item, event)
