from django.core.management.base import BaseCommand
from django.db.models.functions import Now

from apps.accounts.models import RateLimitBucket


class Command(BaseCommand):
    help = "Elimina contadores de rate limiting vencidos; ejecutar diariamente."

    def handle(self, *args, **options):
        count, _ = RateLimitBucket.objects.filter(expires_at__lte=Now()).delete()
        self.stdout.write(f"Contadores vencidos eliminados: {count}.")
