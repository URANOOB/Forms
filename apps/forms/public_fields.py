import math
import re

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

from .additional_choices import additional_text_config
from .choice_widgets import ImageCheckboxSelectMultiple, ImageRadioSelect, ImageSelect
from .question_fields import (
    FILE_TYPES,
    GRID_TYPES,
    SCALE_TYPES,
    AttachmentField,
    GridField,
    ScaleWidget,
    scale_settings,
)

DISPLAY_TYPES = {"HEADING", "INFORMATION", "IMAGE"}
CHOICE_TYPES = {"SINGLE_CHOICE", "MULTIPLE_CHOICE"}
TEXT_TYPES = {"SHORT_TEXT", "LONG_TEXT", "EMAIL", "PHONE"}


def phone_presentation(field):
    return field.field_type == "PHONE"


def finite_number(value):
    if not math.isfinite(value):
        raise ValidationError("Introduce un número finito.")


class DigitsNumberField(forms.FloatField):
    """Reject signs, decimals and exponents before numeric conversion."""

    def to_python(self, value):
        # Saved numeric conditions may contain integral floats; raw submitted strings
        # must still consist exclusively of digits.
        if isinstance(value, float) and math.isfinite(value) and value.is_integer():
            value = int(value)
        if value not in self.empty_values and not re.fullmatch(r"[0-9]+", str(value)):
            raise ValidationError("Este campo solo admite números del 0 al 9.")
        return super().to_python(value)

    def prepare_value(self, value):
        if isinstance(value, float) and math.isfinite(value) and value.is_integer():
            return str(int(value))
        return super().prepare_value(value)


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
    attrs = {
        "placeholder": field.placeholder
        or ("Ingrese su respuesta" if kind in {"SHORT_TEXT", "LONG_TEXT"} else "")
    }
    if kind in TEXT_TYPES:
        kwargs.update(validation)
        kwargs.setdefault("max_length", 10000 if kind == "LONG_TEXT" else 500)
        if kwargs.get("min_length", 0) > kwargs["max_length"]:
            raise ValidationError(f"El mínimo supera al máximo de texto en «{field.label}».")
        if kind == "EMAIL":
            result = forms.EmailField(**kwargs)
            attrs.update(
                {
                    "inputmode": "email",
                    "autocomplete": "email",
                    "autocapitalize": "none",
                    "spellcheck": "false",
                    "placeholder": field.placeholder or "correo@ejemplo.com",
                }
            )
        else:
            result = forms.CharField(**kwargs)
        if kind == "LONG_TEXT":
            result.widget = forms.Textarea(attrs={"rows": 4})
        if kind == "PHONE":
            result.strip = False
            result.validators.append(
                RegexValidator(
                    r"\A[0-9]{6,25}\Z",
                    "Ingrese un teléfono de 6 a 25 dígitos, sin espacios ni símbolos.",
                )
            )
            result.widget = forms.TextInput(attrs={"type": "tel"})
            attrs.update(
                {
                    "inputmode": "numeric",
                    "autocomplete": "tel",
                    "data-digits-only": "",
                    "placeholder": field.placeholder or "Ingrese el número de teléfono",
                    "pattern": "[0-9]{6,25}",
                }
            )
    elif kind == "NUMBER":
        result = DigitsNumberField(
            **kwargs,
            **validation,
            validators=[finite_number],
            widget=forms.TextInput(),
        )
        attrs.update(
            {
                "inputmode": "numeric",
                "pattern": "[0-9]+",
                "data-digits-only": "",
                "class": "numeric-input",
                "placeholder": field.placeholder or "Ingrese un número",
            }
        )
        for bound in ("min", "max"):
            if f"{bound}_value" in validation:
                attrs[bound] = validation[f"{bound}_value"]
    elif kind == "DATE":
        result = forms.DateField(
            **kwargs,
            input_formats=["%Y-%m-%d"],
            widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        )
    elif kind == "TIME":
        result = forms.TimeField(
            **kwargs,
            input_formats=["%H:%M", "%H:%M:%S"],
            widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
        )
    elif kind in SCALE_TYPES:
        start, end, symbol = scale_settings(field)
        result = forms.TypedChoiceField(
            **kwargs,
            coerce=int,
            empty_value=None,
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
            choices=[("", "Seleccione una opción"), ("true", "Sí"), ("false", "No")],
            coerce=lambda value: value == "true",
            empty_value=None,
        )
    elif kind in CHOICE_TYPES:
        if not isinstance(field.configuration.get("searchable", False), bool):
            raise ValidationError(f"Revisa la opción de búsqueda en «{field.label}».")
        additional_text_config(field)
        options = [
            (option.value, option.label) for option in field.options.all() if option.is_active
        ]
        image_urls = {
            option.value: option.image.get_absolute_url()
            for option in field.options.all()
            if option.is_active and option.image_id
        }
        if not options:
            raise ValidationError(f"Añade al menos una opción activa en «{field.label}».")
        if kind == "MULTIPLE_CHOICE":
            result = forms.MultipleChoiceField(
                **kwargs, choices=options, widget=ImageCheckboxSelectMultiple(image_urls)
            )
        else:
            result = forms.ChoiceField(
                **kwargs,
                choices=[("", "Seleccione una opción"), *options],
                widget=ImageSelect(image_urls),
            )
            if field.configuration.get("widget") == "radio":
                result = forms.ChoiceField(
                    **kwargs, choices=options, widget=ImageRadioSelect(image_urls)
                )
            elif field.configuration.get("searchable") is True:
                attrs["data-searchable"] = "true"
    else:
        raise ValidationError(f"Tipo de campo no soportado: {kind}.")
    result.widget.attrs.update(attrs)
    return result


def empty(value):
    return value is None or value == "" or value == [] or value == {}


def json_value(value):
    return value.isoformat() if hasattr(value, "isoformat") else value
