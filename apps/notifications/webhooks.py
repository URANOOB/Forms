import re

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import resend_client
from .models import EmailDeliveryEvent, EmailNotification, EmailSendAttempt
from .services import EVENTS, apply_event, lock_provider_message


@csrf_exempt
@require_POST
def resend_webhook(request):
    if not settings.RESEND_WEBHOOK_SECRET:
        return HttpResponse(status=503)
    try:
        if int(request.META.get("CONTENT_LENGTH") or 0) > 65536:
            return HttpResponse(status=413)
    except (ValueError, TypeError):
        return HttpResponse(status=400)
    if len(request.body) > 65536:
        return HttpResponse(status=413)
    try:
        payload = resend_client.verify(request.body, request.headers)
    except (ValueError, TypeError, UnicodeError):
        return HttpResponse(status=400)
    if not isinstance(payload, dict):
        return HttpResponse(status=400)
    event_type = payload.get("type")
    if not isinstance(event_type, str):
        return HttpResponse(status=400)
    if event_type not in EVENTS:
        return HttpResponse(status=204)
    data = payload.get("data")
    if not isinstance(data, dict):
        return HttpResponse(status=400)
    event_id, message_id = request.headers.get("svix-id", ""), data.get("email_id")
    if any(
        not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value)
        for value in (event_id, message_id)
    ):
        return HttpResponse(status=400)
    try:
        occurred = parse_datetime(payload.get("created_at", ""))
        if not occurred or timezone.is_naive(occurred):
            raise ValueError
    except (ValueError, TypeError):
        return HttpResponse(status=400)
    with transaction.atomic():
        lock_provider_message(message_id)
        # Serialize event insertion with sender finalization using the provider ID.
        # Unknown events remain durable and are reconciled after the send returns.
        item = EmailNotification.objects.filter(provider_message_id=message_id).first()
        if item is None:
            attempt = EmailSendAttempt.objects.filter(provider_message_id=message_id).first()
            if attempt:
                item = attempt.notification
        if item:
            item = EmailNotification.objects.select_for_update().get(pk=item.pk)
        event, _ = EmailDeliveryEvent.objects.get_or_create(
            provider_event_id=event_id,
            defaults={
                "provider_message_id": message_id,
                "event_type": event_type,
                "occurred_at": occurred,
                "metadata": {},  # No payload, recipients, subject, rejection reason or headers.
            },
        )
        if event.provider_message_id != message_id or event.event_type != event_type:
            return HttpResponse(status=400)
        if item:
            apply_event(item, event)
    return HttpResponse(status=204)
