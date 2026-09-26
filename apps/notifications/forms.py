import re

from django import forms

from .recipients import clean_internal_recipients


class RecipientSettingsForm(forms.Form):
    notify_internal_on_submission = forms.BooleanField(
        required=False, label="Avisar cuando llegue una nueva respuesta"
    )
    internal_recipients = forms.CharField(
        required=False,
        max_length=5200,
        label="Destinatarios",
        help_text=(
            "Escribe hasta 20 correos, separados por comas, punto y coma o saltos de línea. "
            "Deja la lista vacía para avisar al creador del formulario."
        ),
        widget=forms.Textarea(
            attrs={
                "rows": 5,
                "placeholder": "equipo@institucion.com\ncoordinacion@institucion.com",
                "spellcheck": "false",
            }
        ),
    )

    def clean_internal_recipients(self):
        values = [
            part.strip()
            for part in re.split(r"[,;\r\n]+", self.cleaned_data["internal_recipients"])
            if part.strip()
        ]
        return clean_internal_recipients(values)
