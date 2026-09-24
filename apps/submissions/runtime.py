import uuid

from django import forms
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.forms.additional_choices import additional_input, additional_text_config
from apps.forms.models import Form
from apps.forms.public_fields import empty, json_value, phone_presentation
from apps.forms.question_fields import FILE_TYPES, AttachmentField, GridField

from .models import Submission, SubmissionAnswer, SubmissionFile

TOKEN_SALT = "public-form-submission"


def new_token(form):
    return signing.dumps(
        {"form": str(form.pk), "version": str(form.active_version_id), "nonce": str(uuid.uuid4())},
        salt=TOKEN_SALT,
    )


def read_token(token, form):
    try:
        payload = signing.loads(token, salt=TOKEN_SALT, max_age=86400)
        if payload["form"] != str(form.pk) or payload["version"] != str(form.active_version_id):
            raise ValueError
        return uuid.UUID(payload["nonce"])
    except (signing.BadSignature, KeyError, TypeError, ValueError) as error:
        raise ValidationError(
            "El formulario cambió o el enlace de envío venció. Revisa tus datos y vuelve a enviar."
        ) from error


class PublicResponseForm(forms.Form):
    def __init__(self, schema, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.schema = schema
        self.additional_text = {}
        for key, field in schema.by_id.items():
            if schema.inputs[key] is not None:
                name = f"answer_{field.stable_key}"
                self.fields[name] = schema.inputs[key]
                config = additional_text_config(field)
                if config:
                    self.additional_text[key] = config
                    self.fields[f"{name}__extra"] = additional_input(
                        config,
                        label=f"{field.label}: {config['placeholder']}",
                    )

    def clean(self):
        cleaned = super().clean()
        values = {
            key: json_value(cleaned.get(f"answer_{field.stable_key}"))
            for key, field in self.schema.by_id.items()
        }
        _, states = self.schema.journey(values)
        self.answers = {}
        for key, field in self.schema.by_id.items():
            name = f"answer_{field.stable_key}"
            extra_name = f"{name}__extra"
            if name not in self.fields:
                continue
            if not states[key]["visible"]:
                self._errors.pop(name, None)
                cleaned.pop(name, None)
                self._errors.pop(extra_name, None)
                cleaned.pop(extra_name, None)
                continue
            if states[key]["required"] and name not in self._errors and empty(values[key]):
                self.add_error(name, "Este campo es obligatorio.")
            elif (
                states[key]["required"]
                and name not in self._errors
                and isinstance(self.fields[name], GridField)
                and not self.fields[name].complete(values[key])
            ):
                self.add_error(name, "Responda todas las filas de la cuadrícula.")
            if (config := self.schema.option_filters.get(key)) and not empty(values[key]):
                source = config["source"]
                if (
                    not states[source]["visible"]
                    or not states[source]["available"]
                    or values[source] not in config["values"].get(values[key], [])
                ):
                    self.add_error(name, "Seleccione una opción del agrupador elegido.")
            self.answers[field.pk] = values[key]
            if key in self.additional_text:
                if values[key] in self.additional_text[key]["values"]:
                    text = cleaned.get(extra_name, "")
                    if not text and extra_name not in self._errors:
                        self.add_error(extra_name, "Complete este campo adicional.")
                    self.answers[field.pk] = {"selected": values[key], "text": text}
                else:
                    # Ignore stale or forged details for options that do not request text.
                    self._errors.pop(extra_name, None)
                    cleaned.pop(extra_name, None)
        return cleaned

    def section_rows(self):
        question_numbers = {
            field.pk: number
            for number, field in enumerate(
                (
                    field
                    for field in self.schema.fields
                    if f"answer_{field.stable_key}" in self.fields
                ),
                start=1,
            )
        }
        return [
            {
                "section": section,
                "rows": [
                    {
                        "field": field,
                        "number": question_numbers.get(field.pk),
                        "is_phone": phone_presentation(field),
                        "upload_hint": (
                            f"Hasta {self.schema.inputs[str(field.pk)].max_files} archivo(s), "
                            f"{self.schema.inputs[str(field.pk)].max_mb} MB por archivo. "
                            + ", ".join(self.schema.inputs[str(field.pk)].extensions).upper()
                        )
                        if isinstance(self.schema.inputs[str(field.pk)], AttachmentField)
                        else "",
                        "input": self[f"answer_{field.stable_key}"]
                        if f"answer_{field.stable_key}" in self.fields
                        else None,
                        "additional_input": self[f"answer_{field.stable_key}__extra"]
                        if str(field.pk) in self.additional_text
                        else None,
                        "additional_label": self.additional_text.get(str(field.pk), {}).get(
                            "placeholder", ""
                        ),
                        "additional_hint": {
                            "other": "Especifique la información correspondiente a «Otro».",
                            "any": "Ingrese la información adicional de la opción seleccionada.",
                            "option": "Ingrese la información adicional de la opción indicada.",
                        }.get(self.additional_text.get(str(field.pk), {}).get("mode"), ""),
                    }
                    for field in self.schema.fields
                    if field.section_id == section.pk
                ],
            }
            for section in self.schema.sections
        ]


def save_response(form_id, version_id, nonce, answers):
    stored_files = []
    try:
        with transaction.atomic():
            form = Form.objects.select_for_update().get(pk=form_id)
            if (
                form.status != Form.Status.PUBLISHED
                or form.deleted_at
                or form.active_version_id != version_id
            ):
                raise ValidationError(
                    "Este formulario ya no recibe respuestas en esta versión. Recarga la página."
                )
            existing = Submission.objects.filter(idempotency_key=nonce).first()
            if existing:
                if existing.form_id != form.pk or existing.form_version_id != version_id:
                    raise ValidationError("El envío no corresponde a este formulario.")
                return existing
            allowed = dict(form.active_version.fields.values_list("pk", "field_type"))
            if not set(answers).issubset(allowed):
                raise ValidationError("La respuesta contiene campos de otra versión.")
            submission = Submission.objects.create(
                form=form, form_version_id=version_id, idempotency_key=nonce
            )
            for key, value in answers.items():
                if allowed[key] not in FILE_TYPES:
                    SubmissionAnswer.objects.create(
                        submission=submission, field_id=key, value=value
                    )
                    continue
                answer = SubmissionAnswer.objects.create(
                    submission=submission, field_id=key, value=None
                )
                metadata = []
                for upload in value or []:
                    attachment = SubmissionFile(
                        answer=answer,
                        original_name=upload.name,
                        size=upload.size,
                    )
                    attachment.file.save(upload.name, upload, save=False)
                    stored_files.append(attachment.file)
                    attachment.save()
                    metadata.append(
                        {
                            "id": str(attachment.pk),
                            "name": attachment.original_name,
                            "size": attachment.size,
                        }
                    )
                answer.value = {"files": metadata}
                answer.save(update_fields=["value"])
            return submission
    except Exception:
        # File storage is not transactional; remove writes if the database rolls back.
        for stored in stored_files:
            stored.delete(save=False)
        raise
