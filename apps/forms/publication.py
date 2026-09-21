from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .conditions import FormSchema
from .models import Form, FormVersion
from .public_fields import DISPLAY_TYPES


@transaction.atomic
def publish_form(form_id, *, preserve_access=False):
    form = Form.objects.select_for_update().get(pk=form_id)
    if form.deleted_at or form.status == Form.Status.ARCHIVED:
        raise ValidationError("No se puede publicar un formulario archivado.")
    version = form.versions.select_for_update().filter(status=FormVersion.Status.DRAFT).first()
    if version is None:
        if not form.active_version_id:
            raise ValidationError("El formulario necesita una versión en borrador.")
        version = FormVersion.objects.select_for_update().get(pk=form.active_version_id)
        if version.status != FormVersion.Status.PUBLISHED:
            raise ValidationError("La versión activa no está publicada.")
    schema = FormSchema(version)
    if not any(field.field_type not in DISPLAY_TYPES for field in schema.fields):
        raise ValidationError("Añade al menos un campo de respuesta antes de publicar.")
    if version.status == FormVersion.Status.DRAFT:
        if not version.title:
            version.title = form.name
            version.description = form.description
        version.status = FormVersion.Status.PUBLISHED
        version.published_at = timezone.now()
        version.save()
    form.active_version = version
    if not preserve_access:
        form.status = Form.Status.PUBLISHED
    form.name = version.title or form.name
    form.description = version.description
    form.full_clean()
    form.save(update_fields=["active_version", "status", "name", "description", "updated_at"])
    return form


@transaction.atomic
def set_form_status(form_id, status):
    if status not in {Form.Status.PAUSED, Form.Status.ARCHIVED}:
        raise ValueError("Estado no admitido.")
    form = Form.objects.select_for_update().get(pk=form_id)
    if form.deleted_at:
        raise ValidationError("Este formulario fue eliminado.")
    if status == Form.Status.PAUSED and form.status != Form.Status.PUBLISHED:
        raise ValidationError("Sólo se puede pausar un formulario publicado.")
    form.status = status
    form.save(update_fields=["status", "updated_at"])
    return form


@transaction.atomic
def set_form_access(form_id, operation):
    form = Form.objects.select_for_update().get(pk=form_id)
    if form.deleted_at or form.status == Form.Status.ARCHIVED:
        raise ValidationError("No se puede cambiar el acceso de un formulario archivado.")
    if operation == "unpublish":
        form.status = Form.Status.DRAFT
    elif operation in {"pause", "resume"}:
        if (form.status not in {Form.Status.PUBLISHED, Form.Status.PAUSED}
                or not form.active_version_id
                or form.active_version.status != FormVersion.Status.PUBLISHED):
            raise ValidationError("Publica el formulario antes de activar la recepción.")
        form.status = Form.Status.PAUSED if operation == "pause" else Form.Status.PUBLISHED
    else:
        raise ValueError("Operación no admitida.")
    form.save(update_fields=["status", "updated_at"])
    return form


@transaction.atomic
def delete_form(form_id):
    form = Form.objects.select_for_update().get(pk=form_id)
    if not form.deleted_at:
        form.deleted_at = timezone.now()
        form.status = Form.Status.ARCHIVED
        form.save(update_fields=["deleted_at", "status", "updated_at"])
    return form
