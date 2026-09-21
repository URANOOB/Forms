import math

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

from .question_fields import (
    FILE_TYPES, GRID_TYPES, SCALE_TYPES, AttachmentField, GridField, ScaleWidget, scale_settings,
)

DISPLAY_TYPES = {"HEADING", "INFORMATION", "IMAGE"}
CHOICE_TYPES = {"SINGLE_CHOICE", "MULTIPLE_CHOICE"}
TEXT_TYPES = {"SHORT_TEXT", "LONG_TEXT", "EMAIL", "PHONE"}


def finite_number(value):
    if not math.isfinite(value):
        raise ValidationError("Introduce un número finito.")


def public_field(field):
    kind = field.field_type
    if kind in DISPLAY_TYPES:
        return None
    validation = field.validation
    allowed = {"min_length", "max_length"} if kind in TEXT_TYPES else set()
    if kind == "NUMBER":
        allowed = {"min_value", "max_value"}
    if set(validation) - allowed:
        raise ValidationError(
            f"Revisa las validaciones de «{field.label}»: hay opciones no admitidas."
        )
    for key, value in validation.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValidationError(f"El límite {key} de «{field.label}» debe ser numérico.")
        if key.endswith("length") and (not isinstance(value, int) or value < 0 or value > 20000):
            raise ValidationError("Los límites de texto deben estar entre 0 y 20000 caracteres.")
    prefix = "length" if kind in TEXT_TYPES else "value"
    if validation.get(f"min_{prefix}", -math.inf) > validation.get(f"max_{prefix}", math.inf):
        raise ValidationError(f"El mínimo supera al máximo en «{field.label}».")
    kwargs = {"required": False, "label": field.label, "help_text": field.help_text}
    attrs = {"placeholder": field.placeholder}
    if kind in TEXT_TYPES:
        kwargs.update(validation)
        kwargs.setdefault("max_length", 10000 if kind == "LONG_TEXT" else 500)
        if kwargs.get("min_length", 0) > kwargs["max_length"]:
            raise ValidationError(f"El mínimo supera al máximo de texto en «{field.label}».")
        if kind == "EMAIL":
            result = forms.EmailField(**kwargs)
        else:
            result = forms.CharField(**kwargs)
        if kind == "LONG_TEXT":
            result.widget = forms.Textarea(attrs={"rows": 4})
        if kind == "PHONE":
            result.validators.append(
                RegexValidator(r"^\+?[0-9().\-\s]{6,25}$", "Revisa el teléfono.")
            )
            result.widget = forms.TextInput(attrs={"type": "tel"})
    elif kind == "NUMBER":
        result = forms.FloatField(**kwargs, **validation, validators=[finite_number])
        result.widget.attrs["step"] = "any"
    elif kind == "DATE":
        result = forms.DateField(
            **kwargs,
            input_formats=["%Y-%m-%d"],
            widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        )
    elif kind == "TIME":
        result = forms.TimeField(
            **kwargs, input_formats=["%H:%M", "%H:%M:%S"],
            widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
        )
    elif kind in SCALE_TYPES:
        start, end, symbol = scale_settings(field)
        result = forms.TypedChoiceField(
            **kwargs, coerce=int, empty_value=None,
            choices=[(str(n), str(n)) for n in range(start, end + 1)],
            widget=ScaleWidget(field, start, end, symbol),
        )
    elif kind in GRID_TYPES:
        result = GridField(field, **kwargs)
    elif kind in FILE_TYPES:
        result = AttachmentField(field, **kwargs)
    elif kind == "BOOLEAN":
        result = forms.TypedChoiceField(
            **kwargs,
            choices=[("", "Selecciona una opción"), ("true", "Sí"), ("false", "No")],
            coerce=lambda value: value == "true",
            empty_value=None,
        )
    elif kind in CHOICE_TYPES:
        options = [
            (option.value, option.label) for option in field.options.all() if option.is_active
        ]
        if not options:
            raise ValidationError(f"Añade al menos una opción activa en «{field.label}».")
        if kind == "MULTIPLE_CHOICE":
            result = forms.MultipleChoiceField(
                **kwargs, choices=options, widget=forms.CheckboxSelectMultiple
            )
        else:
            result = forms.ChoiceField(**kwargs, choices=[("", "Selecciona una opción"), *options])
            if field.configuration.get("widget") == "radio":
                result = forms.ChoiceField(**kwargs, choices=options, widget=forms.RadioSelect)
    else:
        raise ValidationError(f"Tipo de campo no soportado: {kind}.")
    result.widget.attrs.update(attrs)
    return result


def empty(value):
    return value is None or value == "" or value == [] or value == {}


def json_value(value):
    return value.isoformat() if hasattr(value, "isoformat") else value
