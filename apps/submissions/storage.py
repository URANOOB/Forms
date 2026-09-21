import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage


def response_file_storage():
    # Deliberately outside MEDIA_ROOT: downloads pass through the permission-checked view.
    return FileSystemStorage(location=settings.BASE_DIR / "private_uploads")


def response_file_path(instance, filename):
    return f"responses/{instance.answer.submission_id}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"
