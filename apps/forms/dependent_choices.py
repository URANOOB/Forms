"""Version-local option relations reference stable field keys, never mutable row ids."""

from django.core.exceptions import ValidationError

from .catalog_import import MAX_OPTIONS


def option_filters(fields):
    by_key = {field.stable_key: field for field in fields}
    result = {}
    positions = {field.stable_key: index for index, field in enumerate(fields)}
    for field in fields:
        config = field.configuration.get("option_filter")
        if config is None:
            continue
        error = f"Revisa las opciones relacionadas de «{field.label}»."
        if not isinstance(config, dict) or not isinstance(config.get("source"), str):
            raise ValidationError(error)
        source = by_key.get(config["source"])
        if source is None or source == field or source.field_type != "SINGLE_CHOICE":
            raise ValidationError(
                f"{error} El campo de origen debe ser una selección simple existente."
            )
        if field.field_type != "SINGLE_CHOICE" or field.configuration.get("widget") != "select":
            raise ValidationError(f"{error} El campo dependiente debe ser un desplegable.")
        if positions[source.stable_key] >= positions[field.stable_key]:
            raise ValidationError(f"Coloca «{source.label}» antes de «{field.label}».")
        values = config.get("values")
        if not isinstance(values, dict) or len(values) > MAX_OPTIONS:
            raise ValidationError(error)
        parent_values = {option.value for option in source.options.all() if option.is_active}
        child_values = {option.value for option in field.options.all() if option.is_active}
        if set(values) != child_values:
            raise ValidationError(f"{error} Cada opción activa necesita sus agrupadores.")
        for parents in values.values():
            if (
                not isinstance(parents, list)
                or not parents
                or len(parents) > MAX_OPTIONS
                or any(not isinstance(value, str) for value in parents)
                or len(set(parents)) != len(parents)
                or not set(parents).issubset(parent_values)
            ):
                raise ValidationError(f"{error} Hay agrupadores vacíos, repetidos o inexistentes.")
        result[str(field.pk)] = {"source": str(source.pk), "values": values}
    return result
