import uuid

from django import forms
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.forms.models import Form
from apps.forms.public_fields import empty, json_value
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
        for key, field in schema.by_id.items():
            if schema.inputs[key] is not None:
                self.fields[f"answer_{field.stable_key}"] = schema.inputs[key]

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
            if name not in self.fields:
                continue
            if not states[key]["visible"]:
                self._errors.pop(name, None)
                cleaned.pop(name, None)
                continue
            if states[key]["required"] and name not in self._errors and empty(values[key]):
                self.add_error(name, "Este campo es obligatorio.")
            elif (
                states[key]["required"] and name not in self._errors
                and isinstance(self.fields[name], GridField)
                and not self.fields[name].complete(values[key])
            ):
                self.add_error(name, "Responde todas las filas de la cuadrícula.")
            self.answers[field.pk] = values[key]
        return cleaned

    def section_rows(self):
        return [
            {
                "section": section,
                "rows": [
                    {
                        "field": field,
                        "upload_hint": (
                            f"Hasta {self.schema.inputs[str(field.pk)].max_files} archivo(s), "
                            f"{self.schema.inputs[str(field.pk)].max_mb} MB por archivo. "
                            + ", ".join(self.schema.inputs[str(field.pk)].extensions).upper()
                        ) if isinstance(self.schema.inputs[str(field.pk)], AttachmentField) else "",
                        "input": self[f"answer_{field.stable_key}"]
                        if f"answer_{field.stable_key}" in self.fields
                        else None,
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
                form.status != Form.Status.PUBLISHED or form.deleted_at
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
                    SubmissionAnswer.objects.create(submission=submission, field_id=key, value=value)
                    continue
                answer = SubmissionAnswer.objects.create(
                    submission=submission, field_id=key, value=None
                )
                metadata = []
                for upload in value or []:
                    attachment = SubmissionFile(
                        answer=answer, original_name=upload.name, size=upload.size,
                    )
                    attachment.file.save(upload.name, upload, save=False)
                    stored_files.append(attachment.file)
                    attachment.save()
                    metadata.append({
                        "id": str(attachment.pk), "name": attachment.original_name,
                        "size": attachment.size,
                    })
                answer.value = {"files": metadata}
                answer.save(update_fields=["value"])
            return submission
    except Exception:
        # File storage is not transactional; remove writes if the database rolls back.
        for stored in stored_files:
            stored.delete(save=False)
        raise
