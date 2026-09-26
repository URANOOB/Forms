from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from apps.notifications.models import EmailNotification
from apps.notifications.services import send_notification


class Command(BaseCommand):
    help = "Procesa correos pendientes, fallidos y envíos interrumpidos con idempotencia."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        if not settings.EMAIL_NOTIFICATIONS_ENABLED:
            raise CommandError("EMAIL_NOTIFICATIONS_ENABLED está desactivado.")
        if not 1 <= options["limit"] <= 500:
            raise CommandError("--limit debe estar entre 1 y 500.")
        queryset = (
            EmailNotification.objects.filter(
                Q(status="PENDING")
                | Q(status="FAILED")
                & (
                    Q(provider_message_id__isnull=False)
                    | Q(first_attempt_at__isnull=True)
                    | Q(first_attempt_at__gt=timezone.now() - timedelta(hours=23))
                )
                | Q(status="SENDING", lease_until__lte=timezone.now())
            )
            .exclude(
                last_error=(
                    "El contenido cambió desde el primer intento; "
                    "se requiere revisión administrativa."
                )
            )
            .order_by("created_at")
            .values_list("pk", flat=True)[: options["limit"]]
        )
        sent = sum(send_notification(pk, retry=True) for pk in list(queryset))
        self.stdout.write(f"Envíos confirmados por Resend: {sent}.")
