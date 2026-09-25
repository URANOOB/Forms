import logging

from .models import PendingFileDeletion, SubmissionFile

logger = logging.getLogger(__name__)


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
