import uuid

from django.db import models
from django.utils import timezone


class FormNotificationSettings(models.Model):
    form = models.OneToOneField(
        "forms.Form", on_delete=models.CASCADE, related_name="email_settings"
    )
    notify_internal_on_submission = models.BooleanField(default=True)
    notify_respondent_on_validated = models.BooleanField(default=True)
    notify_respondent_on_rejected = models.BooleanField(default=True)
    respondent_email_stable_key = models.CharField(max_length=100, blank=True)


class EmailNotification(models.Model):
    class Event(models.TextChoices):
        SUBMISSION_RECEIVED = "SUBMISSION_RECEIVED", "Nueva respuesta"
        SUBMISSION_VALIDATED = "SUBMISSION_VALIDATED", "Solicitud aprobada"
        SUBMISSION_REJECTED = "SUBMISSION_REJECTED", "Solicitud rechazada"

    class Recipient(models.TextChoices):
        INTERNAL = "INTERNAL", "Interno"
        RESPONDENT = "RESPONDENT", "Respondiente"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        SENDING = "SENDING", "En proceso"
        SENT = "SENT", "Enviado"
        DELIVERED = "DELIVERED", "Entregado"
        DELIVERY_DELAYED = "DELIVERY_DELAYED", "Entrega demorada"
        FAILED = "FAILED", "Fallido"
        BOUNCED = "BOUNCED", "Rebotado"
        COMPLAINED = "COMPLAINED", "Marcado como spam"
        SUPPRESSED = "SUPPRESSED", "Suprimido"
        SKIPPED = "SKIPPED", "Omitido"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    form = models.ForeignKey("forms.Form", null=True, on_delete=models.SET_NULL)
    form_name = models.CharField(max_length=200)
    submission = models.ForeignKey(
        "submissions.Submission",
        null=True,
        on_delete=models.SET_NULL,
        related_name="email_notifications",
    )
    review = models.ForeignKey("submissions.SubmissionReview", null=True, on_delete=models.SET_NULL)
    event_type = models.CharField(max_length=24, choices=Event)
    recipient_kind = models.CharField(max_length=12, choices=Recipient)
    recipient_email = models.EmailField(blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=Status, default=Status.PENDING)
    subject = models.CharField(max_length=300)
    provider = models.CharField(max_length=20, default="resend")
    provider_message_id = models.CharField(max_length=100, null=True, blank=True, unique=True)
    idempotency_key = models.CharField(max_length=64, unique=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    last_event_at = models.DateTimeField(null=True, blank=True)
    last_provider_event = models.CharField(max_length=40, blank=True)
    first_attempt_at = models.DateTimeField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    generation = models.PositiveIntegerField(default=0)
    payload_hash = models.CharField(max_length=64, blank=True)
    is_test = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "correo"
        verbose_name_plural = "correos"
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["event_type", "created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    status__in=[
                        "PENDING",
                        "SENDING",
                        "SENT",
                        "DELIVERED",
                        "DELIVERY_DELAYED",
                        "FAILED",
                        "BOUNCED",
                        "COMPLAINED",
                        "SUPPRESSED",
                        "SKIPPED",
                    ]
                ),
                name="notification_valid_status",
            )
        ]

    @property
    def masked_email(self):
        if "@" not in self.recipient_email:
            return "Sin destinatario"
        local, domain = self.recipient_email.rsplit("@", 1)
        return f"{local[:2]}***@{domain}"


class EmailSendAttempt(models.Model):
    notification = models.ForeignKey(
        EmailNotification, on_delete=models.CASCADE, related_name="send_attempts"
    )
    number = models.PositiveIntegerField()
    generation = models.PositiveIntegerField()
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True)
    status = models.CharField(max_length=20, default="SENDING")
    error = models.CharField(max_length=500, blank=True)
    provider_message_id = models.CharField(max_length=100, blank=True, db_index=True)

    class Meta:
        ordering = ["-started_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["notification", "number"], name="notification_attempt_number"
            )
        ]


class EmailDeliveryEvent(models.Model):
    # An event may arrive before the send HTTP response. Retain only operational
    # metadata, then attach it once the provider ID has been persisted.
    notification = models.ForeignKey(
        EmailNotification, null=True, on_delete=models.CASCADE, related_name="delivery_events"
    )
    provider_event_id = models.CharField(max_length=100, unique=True)
    provider_message_id = models.CharField(max_length=100, db_index=True)
    event_type = models.CharField(max_length=40)
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict)

    class Meta:
        ordering = ["occurred_at", "pk"]


class EmailSuppression(models.Model):
    email = models.EmailField(unique=True)
    reason = models.CharField(max_length=20)
    created_at = models.DateTimeField(default=timezone.now)
