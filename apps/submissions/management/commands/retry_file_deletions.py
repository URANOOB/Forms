from django.core.management.base import BaseCommand, CommandError

from apps.submissions.file_cleanup import delete_pending_file
from apps.submissions.models import PendingFileDeletion


class Command(BaseCommand):
    help = "Reintenta eliminaciones de archivos pendientes tras un purgado; ejecutar diariamente."

    def handle(self, *args, **options):
        failed = 0
        for task_id in PendingFileDeletion.objects.values_list("pk", flat=True).iterator(
            chunk_size=100
        ):
            failed += not delete_pending_file(task_id)
        if failed:
            raise CommandError(f"Archivos pendientes de eliminar: {failed}.")
        self.stdout.write("Eliminaciones de archivos completadas.")
