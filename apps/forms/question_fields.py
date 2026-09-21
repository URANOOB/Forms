"""Widgets and validation for scales, grids and respondent attachments."""

import re
from pathlib import Path

from django import forms
from django.core.exceptions import ValidationError

GRID_TYPES = {"GRID_SINGLE", "GRID_MULTIPLE"}
FILE_TYPES = {"FILE", "DOCUMENT"}
SCALE_TYPES = {"LINEAR_SCALE", "RATING"}
UPLOAD_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "webp", "docx", "xlsx", "txt", "csv"}


def integer_setting(config, key, default, low, high):
    value = config.get(key, default)
    if type(value) is not int or not low <= value <= high:
        raise ValidationError(f"«{key}» debe estar entre {low} y {high}.")
    return value


def scale_settings(field):
    config = field.configuration
    start = 1 if field.field_type == "RATING" else integer_setting(config, "min", 1, 0, 1)
    end = integer_setting(config, "max", 5, 2, 10)
    symbol = config.get("symbol", "star")
    if not isinstance(symbol, str) or symbol not in {"star", "heart", "thumb"}:
        raise ValidationError("Selecciona estrellas, corazones o pulgares para la calificación.")
    for key in ("min_label", "max_label"):
        if not isinstance(config.get(key, ""), str) or len(config.get(key, "")) > 150:
            raise ValidationError("Las etiquetas de la escala admiten hasta 150 caracteres.")
    return start, end, symbol


class ScaleWidget(forms.RadioSelect):
    template_name = "public/widgets/scale.html"

    def __init__(self, field, start, end, symbol):
        super().__init__()
        self.scale = {
            "rating": field.field_type == "RATING",
            "symbol": {"star": "★", "heart": "♥", "thumb": "👍"}[symbol],
            "min_label": field.configuration.get("min_label", ""),
            "max_label": field.configuration.get("max_label", ""),
            "max": end,
        }

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"]["scale"] = self.scale
        return context


def grid_axis(config, key, limit):
    items = config.get(key, [])
    if not isinstance(items, list) or not 1 <= len(items) <= limit:
        raise ValidationError(f"La cuadrícula necesita entre 1 y {limit} {key == 'rows' and 'filas' or 'columnas'}.")
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValidationError("Revisa las filas y columnas de la cuadrícula.")
        key_value, label = item.get("id"), item.get("label")
        if (
            not isinstance(key_value, str)
            or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", key_value)
            or key_value in seen
            or not isinstance(label, str)
            or not label.strip()
            or len(label) > 150
        ):
            raise ValidationError("Cada fila y columna necesita un identificador único y un título.")
        seen.add(key_value)
    return items


class GridWidget(forms.Widget):
    template_name = "public/widgets/grid.html"

    def __init__(self, rows, columns, multiple):
        super().__init__()
        self.rows, self.columns, self.multiple = rows, columns, multiple

    def value_from_datadict(self, data, files, name):
        result = {}
        for row in self.rows:
            row_name = f"{name}__{row['id']}"
            value = data.getlist(row_name) if self.multiple else data.get(row_name, "")
            if value:
                result[row["id"]] = value
        return result

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        value = value if isinstance(value, dict) else {}
        context["widget"].update({
            "columns": self.columns,
            "input_type": "checkbox" if self.multiple else "radio",
            "rows": [
                {**row, "name": f"{name}__{row['id']}", "cells": [
                    {**column, "selected": column["id"] in value.get(row["id"], [])
                     if self.multiple else column["id"] == value.get(row["id"])}
                    for column in self.columns
                ]}
                for row in self.rows
            ],
        })
        return context


class GridField(forms.Field):
    def __init__(self, field, **kwargs):
        self.rows = grid_axis(field.configuration, "rows", 20)
        self.columns = grid_axis(field.configuration, "columns", 10)
        self.multiple = field.field_type == "GRID_MULTIPLE"
        super().__init__(widget=GridWidget(self.rows, self.columns, self.multiple), **kwargs)

    def clean(self, value):
        if not value:
            return {}
        if not isinstance(value, dict) or set(value) - {row["id"] for row in self.rows}:
            raise ValidationError("Revisa las respuestas de la cuadrícula.")
        allowed = {column["id"] for column in self.columns}
        for selected in value.values():
            if self.multiple:
                if not isinstance(selected, list) or any(not isinstance(v, str) or v not in allowed for v in selected):
                    raise ValidationError("Selecciona opciones válidas en la cuadrícula.")
            elif not isinstance(selected, str) or selected not in allowed:
                raise ValidationError("Selecciona una opción válida por fila.")
        return value

    def complete(self, value):
        return isinstance(value, dict) and all(value.get(row["id"]) for row in self.rows)


class MultipleFileInput(forms.FileInput):
    allow_multiple_selected = True


class AttachmentField(forms.FileField):
    def __init__(self, field, **kwargs):
        config = field.configuration
        self.max_files = integer_setting(config, "max_files", 1, 1, 5)
        self.max_mb = integer_setting(config, "max_mb", 5, 1, 10)
        extensions = config.get("extensions", sorted(UPLOAD_EXTENSIONS))
        if not isinstance(extensions, list) or not extensions or any(
            not isinstance(extension, str) or extension not in UPLOAD_EXTENSIONS for extension in extensions
        ):
            raise ValidationError("Selecciona los tipos de archivo permitidos.")
        self.extensions = extensions
        super().__init__(widget=MultipleFileInput(attrs={
            "accept": ",".join(f".{extension}" for extension in extensions),
            "data-max-files": self.max_files,
            "data-max-bytes": self.max_mb * 1024 * 1024,
        }), **kwargs)

    def clean(self, data, initial=None):
        if not data:
            return []
        uploads = data if isinstance(data, (list, tuple)) else [data]
        if len(uploads) > self.max_files:
            raise ValidationError(f"Puedes subir hasta {self.max_files} archivo(s).")
        for upload in uploads:
            super().clean(upload)
            extension = Path(upload.name).suffix.lower().lstrip(".")
            if extension not in self.extensions:
                raise ValidationError("Ese tipo de archivo no está permitido.")
            if upload.size > self.max_mb * 1024 * 1024:
                raise ValidationError(f"Cada archivo debe pesar como máximo {self.max_mb} MB.")
            header = upload.read(16)
            upload.seek(0)
            signatures = {
                "pdf": header.startswith(b"%PDF-"),
                "png": header.startswith(b"\x89PNG\r\n\x1a\n"),
                "jpg": header.startswith(b"\xff\xd8\xff"),
                "jpeg": header.startswith(b"\xff\xd8\xff"),
                "webp": header.startswith(b"RIFF") and header[8:12] == b"WEBP",
                "docx": header.startswith(b"PK\x03\x04"),
                "xlsx": header.startswith(b"PK\x03\x04"),
            }
            if extension in signatures and not signatures[extension]:
                raise ValidationError("El contenido del archivo no coincide con su extensión.")
        return list(uploads)
