from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from .models import FormNotificationSettings

SETTING_FLAGS = (
    "notify_internal_on_submission",
    "notify_respondent_on_validated",
    "notify_respondent_on_rejected",
)
DEFAULTS = {
    **dict.fromkeys(SETTING_FLAGS, True),
    "respondent_email_stable_key": "",
    "internal_recipients": [],
}


def settings_for(form):
    values = FormNotificationSettings.objects.filter(form=form).values(*DEFAULTS).first()
    return values or DEFAULTS.copy()


def save_settings(form, data, fields):
    if not isinstance(data, dict) or set(data) - set(DEFAULTS):
        raise ValidationError("Configuración de notificaciones inválida.")
    values = {**settings_for(form), **data}
    if any(type(values[key]) is not bool for key in SETTING_FLAGS):
        raise ValidationError("Las opciones de correo deben ser verdaderas o falsas.")
    key = values["respondent_email_stable_key"]
    if not isinstance(key, str) or (
        key and key not in {f.stable_key for f in fields if f.field_type == "EMAIL"}
    ):
        raise ValidationError("Selecciona un campo EMAIL existente para las notificaciones.")
    values["internal_recipients"] = clean_internal_recipients(values["internal_recipients"])
    FormNotificationSettings.objects.update_or_create(form=form, defaults=values)


def clean_internal_recipients(values):
    if not isinstance(values, list) or len(values) > 20:
        raise ValidationError("Puedes configurar hasta 20 direcciones de correo.")
    recipients = []
    seen = set()
    for value in values:
        email = valid_email(value)
        if not email:
            raise ValidationError(
                "Revisa los destinatarios: todas las direcciones deben ser válidas."
            )
        if email.casefold() not in seen:
            recipients.append(email)
            seen.add(email.casefold())
    return recipients


def valid_email(value):
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if len(value) > 254:
        return ""
    try:
        validate_email(value)
    except ValidationError:
        return ""
    local, domain = value.rsplit("@", 1)
    return f"{local}@{domain.lower()}"


def respondent(submission, configured_key=""):
    answers = submission.answers.filter(
        field__field_type="EMAIL", field__form_version_id=submission.form_version_id
    )
    if configured_key:
        value = (
            answers.filter(field__stable_key=configured_key).values_list("value", flat=True).first()
        )
        email = valid_email(value)
        return (
            email,
            ""
            if email
            else "El campo EMAIL configurado no contiene un correo válido en esta respuesta.",
        )
    candidates = [
        email for value in answers.values_list("value", flat=True) if (email := valid_email(value))
    ]
    if len(candidates) == 1:
        return candidates[0], ""
    if len(candidates) > 1:
        return "", "Hay varios campos de correo y no se configuró cuál corresponde al respondiente."
    return "", "La respuesta no contiene un correo válido."
