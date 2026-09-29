import logging

from django.db import transaction

from .models import PendingFileDeletion, SubmissionFile

logger = logging.getLogger(__name__)


def queue_file_deletion(name):
    task, _ = PendingFileDeletion.objects.get_or_create(name=name)
    transaction.on_commit(lambda: delete_pending_file(task.pk), robust=True)


def compensate_uploads(files):
    # Call only after exiting the failed transaction so retry records survive it.
    # Each file is independent: one unavailable object must not skip the rest.
    for file in files:
        try:
            task, _ = PendingFileDeletion.objects.get_or_create(name=file.name)
            delete_pending_file(task.pk)
        except Exception:
            logger.exception("No se pudo registrar la limpieza de %s", file.name)


def delete_pending_file(task_id):
    task = PendingFileDeletion.objects.filter(pk=task_id).first()
    if task is None:
        return True
    try:
        SubmissionFile._meta.get_field("file").storage.delete(task.name)
    except Exception:
        logger.exception("No se pudo eliminar el archivo; tarea de reintento %s", task_id)
        return False
    task.delete()
    return True
