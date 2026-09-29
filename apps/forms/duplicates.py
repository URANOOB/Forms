"""Explicit identity fields, scoped to one form across its versions."""

from django.core.exceptions import ValidationError

DUPLICATE_TYPES = {"SHORT_TEXT", "NUMBER", "EMAIL", "PHONE", "SINGLE_CHOICE"}


def validate_duplicate_fields(value, fields):
    available = {f.stable_key for f in fields if f.field_type in DUPLICATE_TYPES}
    if (
        not isinstance(value, list)
        or len(value) > 3
        or any(not isinstance(key, str) or key not in available for key in value)
        or len(set(value)) != len(value)
    ):
        raise ValidationError("Selecciona hasta tres campos distintos para detectar duplicados.")
    return value
