"""Bound the whole form, including repeated multipart parameters."""

from django.conf import settings
from django.core.exceptions import ValidationError

from .additional_choices import additional_text_config
from .question_fields import AttachmentField, GridField


def validate_request_budget(fields, inputs):
    parameters, files = 0, 0
    for field in fields:
        entry = inputs[str(field.pk)]
        if isinstance(entry, GridField):
            parameters += len(entry.rows) * (len(entry.columns) if entry.multiple else 1)
        elif isinstance(entry, AttachmentField):
            files += entry.max_files
        elif field.field_type == "MULTIPLE_CHOICE":
            parameters += sum(option.is_active for option in field.options.all())
        elif entry is not None:
            parameters += 1 + bool(additional_text_config(field))
    # Staff editing can send one remove_files parameter for every attachment.
    if parameters + files + 16 > settings.DATA_UPLOAD_MAX_NUMBER_FIELDS:
        raise ValidationError(
            "El formulario supera el límite total de respuestas seleccionables. "
            "Reduce las opciones de selección múltiple o las cuadrículas."
        )
    if files > settings.DATA_UPLOAD_MAX_NUMBER_FILES:
        raise ValidationError(
            f"El formulario admite como máximo {settings.DATA_UPLOAD_MAX_NUMBER_FILES} "
            "archivos en total. Reduce la cantidad de preguntas de adjuntos o sus límites."
        )
