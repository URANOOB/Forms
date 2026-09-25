"""Read-only presentation of received answers, preserving the original schema and values."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import PurePath
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from .summary import normalized, role

MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def display_date(value):
    try:
        parsed = date.fromisoformat(str(value))
        return f"{parsed.day} {MONTHS[parsed.month - 1]} {parsed.year}"
    except (TypeError, ValueError):
        return str(value)


def integer_text(value):
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        try:
            number = Decimal(str(value))
            if number.is_finite() and number == number.to_integral_value():
                return str(int(number))
        except (InvalidOperation, ValueError, OverflowError):
            pass
    return str(value)


def display_value(field, value, text):
    if value is None or value == "" or value == []:
        return text
    if field.field_type == "DATE":
        return display_date(value)
    if field.field_type not in {"SHORT_TEXT", "NUMBER", "PHONE"}:
        return text
    label = normalized(field.label)
    if field.field_type == "PHONE" or re.search(r"\b(telefono|celular|movil)\b", label):
        number = integer_text(value)
        if re.fullmatch(r"\+?\d{7,15}", number):
            prefix = "+" if number.startswith("+") else ""
            digits = number.lstrip("+")
            if len(digits) == 10:
                return f"{prefix}{digits[:3]} {digits[3:6]} {digits[6:]}"
            return prefix + " ".join(digits[i : i + 3] for i in range(0, len(digits), 3))
        return text
    # Only format identifiers when the label identifies the field as a document.
    if role(SimpleNamespace(field=field)) == "document":
        number = integer_text(value)
        if number.isascii() and number.isdigit():
            return re.sub(r"(?<=\d)(?=(\d{3})+$)", ".", number)
    if field.field_type == "NUMBER" and isinstance(value, (int, float, Decimal)):
        return integer_text(value)
    return text


def value_kind(field, value, text):
    if isinstance(value, bool) or (
        field.field_type == "SINGLE_CHOICE" and normalized(text) in {"si", "no"}
    ):
        return "boolean"
    if field.field_type == "SINGLE_CHOICE" and normalized(text) in {
        "confirmado",
        "no confirmado",
        "pendiente",
        "en proceso",
        "completado",
    }:
        return "status"
    return ""


def response_sections(obj):
    sections = {}
    answers = (
        obj.answers.select_related("field__section")
        .prefetch_related("field__options", "files")
        .order_by("field__section__order", "field__section_id", "field__order", "field_id")
    )
    for answer in answers:
        section = answer.field.section
        bucket = sections.setdefault(
            section.pk,
            {
                "id": f"response-section-{obj.pk}-{section.pk}",
                "title": section.title,
                "answers": [],
                "identity": False,
            },
        )
        bucket["identity"] = bucket["identity"] or role(answer) in {"name", "document"}
        value = answer.value
        options = {option.value: option.label for option in answer.field.options.all()}
        attachments = []
        if answer.field.field_type in {"FILE", "DOCUMENT"}:
            preview_types = {
                ".pdf": "pdf",
                ".png": "image",
                ".jpg": "image",
                ".jpeg": "image",
                ".webp": "image",
                ".txt": "text",
                ".csv": "text",
            }
            for file in answer.files.all():
                extension = PurePath(file.original_name).suffix.lower()
                attachments.append(
                    {
                        "name": file.original_name,
                        "url": file.get_absolute_url(),
                        "size": file.size,
                        "extension": extension.lstrip(".").upper() or "ARCHIVO",
                        "preview": preview_types.get(extension, "unsupported"),
                    }
                )
            text = "" if attachments else "No proporcionado"
        elif answer.field.field_type in {"GRID_SINGLE", "GRID_MULTIPLE"}:
            config = answer.field.configuration
            columns = {column["id"]: column["label"] for column in config.get("columns", [])}
            value = value if isinstance(value, dict) else {}
            lines = []
            for row in config.get("rows", []):
                selected = value.get(row["id"], [])
                selected = selected if isinstance(selected, list) else [selected]
                result = (
                    ", ".join(columns.get(item, item) for item in selected) or "No proporcionado"
                )
                lines.append(f"{row['label']}: {result}")
            text = "\n".join(lines)
        elif answer.field.field_type in {"LINEAR_SCALE", "RATING"} and value is not None:
            text = f"{value} de {answer.field.configuration.get('max', 5)}"
        elif answer.field.field_type == "SINGLE_CHOICE" and isinstance(value, dict):
            selected = value.get("selected", "")
            label = options.get(selected, selected) or "No proporcionado"
            detail = value.get("text", "")
            text = f"{label}: {detail}" if detail else label
        elif isinstance(value, bool):
            text = "Sí" if value else "No"
        elif isinstance(value, list):
            text = ", ".join(options.get(item, item) for item in value) or "No proporcionado"
        elif value is None or value == "":
            text = "No proporcionado"
        else:
            text = options.get(str(value), str(value))
        text = display_value(answer.field, value, text)
        empty = not attachments and (value is None or value == "" or value == [])
        kind = value_kind(answer.field, value, text) if not empty else ""
        bucket["answers"].append(
            {
                "label": answer.field.label,
                "value": text,
                "kind": kind,
                "boolean_yes": normalized(text) == "si",
                "files": attachments,
                "wide": answer.field.field_type
                in {"FILE", "DOCUMENT", "LONG_TEXT", "GRID_SINGLE", "GRID_MULTIPLE"}
                or len(text) > 90
                or "\n" in text
                or bool(re.search(r"\b(direccion|domicilio)\b", normalized(answer.field.label))),
                "empty": empty,
                "attachment_field": answer.field.field_type in {"FILE", "DOCUMENT"},
            }
        )

    result = list(sections.values())
    for section in result:
        section["file_count"] = sum(len(answer["files"]) for answer in section["answers"])
        section["files_only"] = all(answer["attachment_field"] for answer in section["answers"])
        if re.fullmatch(
            r"(seccion( \d+| sin titulo)?|informacion general)?", normalized(section["title"])
        ):
            section["title"] = (
                "Documentos"
                if section["files_only"]
                else "Datos del solicitante"
                if section["identity"]
                else "Datos de la respuesta"
            )
    return result


def render_response_details(sections, compact_heading=False):
    return mark_safe(
        render_to_string(
            "admin/submissions/answers.html",
            {
                "sections": sections,
                "compact_heading": compact_heading,
            },
        )
    )
