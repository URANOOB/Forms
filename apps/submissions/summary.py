"""Small response summaries; identifiers are never inferred from arbitrary answers."""

import json
import re
import unicodedata

from django.db.models import Prefetch, prefetch_related_objects
from django.utils import timezone

from apps.forms.models import FieldOption
from apps.forms.response_summary import SUMMARY_TYPES

from .models import SubmissionAnswer


def normalized(value):
    value = "".join(
        c for c in unicodedata.normalize("NFKD", value.lower()) if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def role(answer):
    label = normalized(answer.field.label)
    if label in {
        "nombre",
        "nombres",
        "nombre completo",
        "nombres completos",
        "nombres y apellidos",
        "nombre y apellido",
        "nombre y apellidos",
        "nombre del paciente",
        "paciente",
        "nombre del solicitante",
        "respondiente",
        "nombre del respondiente",
    }:
        return "name"
    if label in {"apellido", "apellidos", "primer apellido", "segundo apellido"}:
        return "surname"
    if label in {
        "documento",
        "numero de documento",
        "numero documento",
        "documento de identidad",
        "numero de identificacion",
        "identificacion",
        "cedula",
        "cedula de ciudadania",
        "numero de cedula",
        "cc",
        "dni",
        "pasaporte",
        "numero de pasaporte",
    }:
        return "document"
    if label in {"numero de orden", "numero orden", "orden", "radicado", "numero de solicitud"}:
        return "order"
    if label in {
        "eps",
        "aseguradora",
        "institucion",
        "empresa",
        "correo",
        "correo electronico",
        "email",
        "telefono",
        "celular",
    }:
        return "context"
    return ""


def load_summary_data(submissions):
    answers = (
        SubmissionAnswer.objects.select_related("field")
        .order_by("field__section__order", "field__section_id", "field__order", "field_id")
        .prefetch_related(
            Prefetch(
                "field__options", queryset=FieldOption.objects.only("field_id", "value", "label")
            ),
            "files",
        )
    )
    prefetch_related_objects(
        submissions, Prefetch("answers", queryset=answers, to_attr="summary_answers")
    )


def answer_text(answer):
    value = answer.value
    if answer.field.field_type in {"FILE", "DOCUMENT"}:
        return ", ".join(file.original_name for file in answer.files.all())
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "Sí" if value else "No"
    options = {option.value: option.label for option in answer.field.options.all()}
    if isinstance(value, list):
        return ", ".join(options.get(str(item), str(item)) for item in value)
    if isinstance(value, dict):
        if "selected" in value:
            selected = str(value.get("selected", ""))
            return ": ".join(filter(None, [options.get(selected, selected), value.get("text", "")]))
        return json.dumps(value, ensure_ascii=False)
    return options.get(str(value), str(value)).strip()


def masked(value):
    return "•••• " + value[-4:] if len(value) > 4 else "•" * len(value)


def summary_for(submission):
    answers = [a for a in submission.summary_answers if a.field.field_type in SUMMARY_TYPES]
    by_key = {a.field.stable_key: a for a in answers}
    config = submission.form.response_summary
    names = [a for a in answers if role(a) in {"name", "surname"} and answer_text(a)]
    names.sort(key=lambda a: role(a) == "surname")
    primary = by_key.get(config.get("title")) if config.get("title") else None
    if primary:
        title = answer_text(primary)
        if role(primary) == "document":
            title = masked(title)
    elif config.get("title"):
        title = ""
    else:
        title = " ".join(answer_text(a) for a in names)
        if not title:
            primary = next((a for a in answers if role(a) == "order" and answer_text(a)), None)
            title = f"{primary.field.label}: {answer_text(primary)}" if primary else ""
    selected = (
        config.get("fields", [])
        if config
        else [
            {"key": a.field.stable_key, "masked": role(a) == "document", "label": a.field.label}
            for a in sorted(answers, key=lambda a: role(a) != "document")
            if role(a) in {"document", "order", "context"} and a != primary and answer_text(a)
        ][:3]
    )
    details = []
    for entry in selected:
        answer = by_key.get(entry["key"])
        value = answer_text(answer) if answer else ""
        details.append(
            {
                "label": answer.field.label if answer else entry.get("label", "Dato"),
                "value": masked(value) if entry.get("masked") and value else value or "Sin dato",
                "document": bool(answer and role(answer) == "document"),
            }
        )
    files = sum(len(a.files.all()) for a in submission.summary_answers)
    local = timezone.localtime(submission.submitted_at)
    today = timezone.localdate()
    day = (
        "Hoy"
        if local.date() == today
        else "Ayer"
        if (today - local.date()).days == 1
        else local.strftime("%d/%m/%Y")
    )
    minutes = max(0, int((timezone.now() - submission.submitted_at).total_seconds() / 60))
    relative = (
        "Hace un momento"
        if minutes < 1
        else f"Hace {minutes} min"
        if minutes < 60
        else f"Hace {minutes // 60} h"
        if minutes < 1440
        else f"{day}, {local:%H:%M}"
    )
    return {
        "title": title or "Respuesta sin identificación",
        "details": details,
        "document": next((d["value"] for d in details if d["document"]), "—"),
        "files": files,
        "date": f"{day}, {local:%H:%M}",
        "relative": relative,
    }
