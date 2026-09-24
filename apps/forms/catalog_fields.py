"""Configurable Excel fields, with explicit single-parent option dependencies."""

import json
import uuid
from collections import defaultdict

from django.core.exceptions import ValidationError

MAX_FIELDS = 20


def suggest_fields(headers, mapping):
    definitions = []
    group, code, description = (mapping[key] for key in ("group", "code", "description"))
    for column in [group, code] if group is not None else [code]:
        definitions.append(
            {
                "id": f"field_{len(definitions) + 1}",
                "label": headers[column][:240],
                "value_column": column,
                "label_columns": [column, description]
                if column == code and description is not None
                else [column],
                "parent": definitions[0]["id"] if definitions else "",
                "searchable": True,
                "required": False,
            }
        )
    return definitions


def read_definitions(settings, headers, defaults):
    if "fields" not in settings:
        for field in defaults:
            field["required"] = settings.get("required") == "true"
        definitions = defaults
    else:
        try:
            definitions = json.loads(settings["fields"])
        except (ValueError, TypeError) as error:
            raise ValidationError("No se pudo leer la configuración de los campos.") from error
    if not isinstance(definitions, list) or not 1 <= len(definitions) <= MAX_FIELDS:
        raise ValidationError(f"Añade entre 1 y {MAX_FIELDS} campos por importación.")
    seen = set()
    for field in definitions:
        if not isinstance(field, dict):
            raise ValidationError("Revisa la configuración de cada campo.")
        key, label, parent = field.get("id"), field.get("label"), field.get("parent", "")
        if not isinstance(key, str) or not key or len(key) > 100 or key in seen:
            raise ValidationError("Cada campo debe tener un identificador distinto.")
        if not isinstance(label, str) or not label.strip() or len(label.strip()) > 240:
            raise ValidationError("Escribe un nombre de 1 a 240 caracteres para cada campo.")
        field["label"] = label.strip()
        if not isinstance(parent, str) or (parent and parent not in seen):
            raise ValidationError("Un campo solo puede depender de otro situado antes que él.")
        field["parent"] = parent
        columns = field.get("label_columns")
        if not isinstance(columns, list) or not columns or len(columns) > len(headers):
            raise ValidationError(f"Elige las columnas del texto visible de «{label}».")
        if any(
            type(col) is not int or not 0 <= col < len(headers)
            for col in [field.get("value_column"), *columns]
        ):
            raise ValidationError(f"Selecciona columnas válidas para «{label}».")
        if len(set(columns)) != len(columns):
            raise ValidationError(f"No repitas columnas en el texto visible de «{label}».")
        if any(type(field.get(flag)) is not bool for flag in ("searchable", "required")):
            raise ValidationError("Revisa el componente y la obligatoriedad de cada campo.")
        seen.add(key)
    return definitions


def build_fields_proposal(rows, definitions):
    fields, row_values, keys = [], {}, {}
    issues, warnings = [], []
    parents = {field["parent"] for field in definitions if field["parent"]}
    selected = sorted(
        {col for field in definitions for col in [field["value_column"], *field["label_columns"]]}
    )
    duplicates = len(rows) - len({tuple(row[col] for col in selected) for _, row in rows})
    if duplicates:
        warnings.append(f"Se omiten {duplicates} filas repetidas en las columnas elegidas.")
    for definition in definitions:
        key, parent = definition["id"], definition["parent"]
        parent_values = row_values.get(parent, [""] * len(rows))
        # Intermediate values repeated under different parents must remain distinct.
        # Otherwise City=Centro in two regions could expose the other region's streets.
        contexts = defaultdict(set)
        for index, (_, row) in enumerate(rows):
            contexts[row[definition["value_column"]]].add(parent_values[index])
        scoped = (
            {value for value, values in contexts.items() if len(values) > 1}
            if parent and key in parents
            else set()
        )
        identities, labels, memberships, values = {}, {}, {}, []
        for index, (number, row) in enumerate(rows):
            raw_value = row[definition["value_column"]]
            texts = [row[col] for col in definition["label_columns"]]
            text = " — ".join(texts)
            parent_value = parent_values[index]
            identity = (raw_value, parent_value if raw_value in scoped else "")
            if identity not in identities:
                identities[identity] = (
                    f"catalog_{uuid.uuid4().hex}" if raw_value in scoped else raw_value
                )
            value = identities[identity]
            values.append(value)
            if not raw_value or not all(texts):
                issues.append(
                    f"Fila {number}, «{definition['label']}»: "
                    "faltan valores en las columnas elegidas."
                )
                continue
            if len(raw_value) > 150 or len(text) > 240:
                issues.append(
                    f"Fila {number}, «{definition['label']}»: el valor supera 150 caracteres "
                    "o el texto supera 240."
                )
                continue
            if value in labels and labels[value] != text:
                issues.append(
                    f"Fila {number}, «{definition['label']}»: el valor «{raw_value}» "
                    "tiene distintos textos visibles."
                )
                continue
            labels[value] = text
            if parent and parent_value not in memberships.setdefault(value, []):
                memberships[value].append(parent_value)
        row_values[key] = values
        keys[key] = f"q_{uuid.uuid4().hex}"
        configuration = {
            "widget": "select",
            "searchable": definition["searchable"],
            "catalog_import": True,
        }
        if parent:
            configuration["option_filter"] = {"source": keys[parent], "values": memberships}
        fields.append(
            {
                "id": str(uuid.uuid4()),
                "stable_key": keys[key],
                "label": definition["label"],
                "field_type": "SINGLE_CHOICE",
                "required": definition["required"],
                "help_text": "",
                "placeholder": "",
                "validation": {},
                "image": None,
                "image_url": "",
                "configuration": configuration,
                "options": [
                    {"value": value, "label": label, "is_active": True}
                    for value, label in labels.items()
                ],
            }
        )
        if scoped:
            warnings.append(
                f"«{definition['label']}» repite valores en distintos grupos. "
                "Se guardarán identificadores internos para mantener separadas sus opciones "
                "dependientes; puedes consultarlos en la vista previa."
            )
        if any(len(items) > 1 for items in memberships.values()):
            warnings.append(
                f"«{definition['label']}» tiene opciones en varios grupos; "
                "estarán disponibles en cada uno."
            )
    if issues:
        return None, issues, warnings
    proposal = {
        "fields": fields,
        "field_count": len(fields),
        "option_count": sum(len(field["options"]) for field in fields),
        "explanation": "Cada campo usa las columnas elegidas. Las dependencias filtran "
        "las opciones según las filas del Excel. Prueba la propuesta antes de añadirla.",
    }
    return proposal, [], warnings
