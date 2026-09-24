import math
import re

from django import forms
from django.core.exceptions import ValidationError

ADDITIONAL_TEXT_PLACEHOLDER = "Por favor escriba cual"
ADDITIONAL_TEXT_LIMIT = 500


def additional_text_config(field):
    """Keep the selected option as the condition source; collect its detail separately."""
    if field.field_type != "SINGLE_CHOICE" or field.configuration.get("widget") == "radio":
        return None
    mode = field.configuration.get("additional_text", "other")
    if not isinstance(mode, str) or mode not in {"other", "any", "option"}:
        raise ValidationError("Selecciona cuándo se solicita el texto adicional.")
    input_type = field.configuration.get("additional_text_type", "text")
    if not isinstance(input_type, str) or input_type not in {"text", "number", "email"}:
        raise ValidationError("El campo adicional debe ser de texto, número o correo electrónico.")
    placeholder = field.configuration.get(
        "additional_text_placeholder", ADDITIONAL_TEXT_PLACEHOLDER
    )
    if not isinstance(placeholder, str) or len(placeholder) > 200:
        raise ValidationError("El placeholder del campo adicional admite hasta 200 caracteres.")
    placeholder = placeholder.strip() or ADDITIONAL_TEXT_PLACEHOLDER
    options = [option for option in field.options.all() if option.is_active]
    if mode == "any":
        values = [option.value for option in options]
    elif mode == "option":
        target = field.configuration.get("additional_text_option")
        if not isinstance(target, str) or target not in {option.value for option in options}:
            raise ValidationError(
                f"Elige una opción válida para el texto adicional de «{field.label}»."
            )
        values = [target]
    else:
        values = [
            option.value
            for option in options
            if option.label.strip().casefold() in {"otro", "otra", "otros", "otras"}
        ]
    return (
        {
            "mode": mode,
            "values": values,
            "type": input_type,
            "placeholder": placeholder,
        }
        if values
        else None
    )


def validate_additional_number(value):
    if not re.fullmatch(r"[0-9]+", value):
        raise ValidationError("Este campo solo admite números del 0 al 9.")
    number = forms.FloatField().clean(value)
    if not math.isfinite(number):
        raise ValidationError("Introduce un número finito.")


def additional_input(config, label):
    attrs = {"placeholder": config["placeholder"], "data-additional-text": ""}
    kwargs = {"required": False, "max_length": ADDITIONAL_TEXT_LIMIT, "label": label}
    if config["type"] == "email":
        attrs.update(
            {
                "inputmode": "email",
                "autocomplete": "email",
                "autocapitalize": "none",
                "spellcheck": "false",
            }
        )
        return forms.EmailField(**kwargs, widget=forms.EmailInput(attrs=attrs))
    if config["type"] == "number":
        attrs.update(
            {
                "inputmode": "numeric",
                "pattern": "[0-9]+",
                "data-digits-only": "",
                "class": "numeric-input",
            }
        )
        # Retain the entered text, including zero, without changing the stored answer format.
        return forms.CharField(
            **kwargs,
            strip=False,
            widget=forms.TextInput(attrs=attrs),
            validators=[validate_additional_number],
        )
    return forms.CharField(**kwargs, widget=forms.TextInput(attrs=attrs))
