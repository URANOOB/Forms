"""Presentation settings shared across a form's response versions."""

from django.core.exceptions import ValidationError

SUMMARY_TYPES = {
    "SHORT_TEXT",
    "LONG_TEXT",
    "EMAIL",
    "PHONE",
    "NUMBER",
    "DATE",
    "TIME",
    "BOOLEAN",
    "SINGLE_CHOICE",
    "MULTIPLE_CHOICE",
    "LINEAR_SCALE",
    "RATING",
}


def validate_response_summary(config, fields):
    if not isinstance(config, dict):
        raise ValidationError("Revisa los campos del resumen de respuestas.")
    available = {field.stable_key: field for field in fields if field.field_type in SUMMARY_TYPES}
    title = config.get("title", "")
    entries = config.get("fields", [])
    if not isinstance(title, str) or (title and title not in available):
        raise ValidationError("Selecciona un campo válido para identificar al respondiente.")
    if not isinstance(entries, list) or len(entries) > 3:
        raise ValidationError("El resumen admite hasta tres datos además del título.")
    seen = {title} if title else set()
    cleaned = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValidationError("Revisa los datos del resumen de respuestas.")
        key, masked = entry.get("key"), entry.get("masked", False)
        if not isinstance(key, str) or key not in available or key in seen:
            raise ValidationError("Selecciona campos distintos y existentes para el resumen.")
        if not isinstance(masked, bool):
            raise ValidationError("Revisa la opción de ocultar parte del dato.")
        seen.add(key)
        cleaned.append({"key": key, "masked": masked, "label": available[key].label})
    return {"title": title, "fields": cleaned} if title or cleaned else {}
