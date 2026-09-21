"""Transactional editor: only drafts can be replaced; published schemas remain intact."""

import hashlib
import json
import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max

from .conditions import FormSchema
from .appearance import validate_appearance
from .models import ConditionalRule, FieldOption, Form, FormField, FormSection, FormVersion
from .public_fields import CHOICE_TYPES


class StaleDraft(ValidationError):
    pass


def current_version(form):
    return form.versions.filter(status="DRAFT").first() or form.active_version


def document(version):
    form = version.form
    sections = []
    fields = list(version.fields.select_related("image").prefetch_related("options"))
    for section in version.sections.all():
        sections.append(
            {
                "id": str(section.pk),
                "title": section.title,
                "description": section.description,
                "configuration": section.configuration,
                "fields": [
                    {
                        "id": str(field.pk),
                        "stable_key": field.stable_key,
                        "label": field.label,
                        "help_text": field.help_text,
                        "field_type": field.field_type,
                        "required": field.required,
                        "placeholder": field.placeholder,
                        "configuration": field.configuration,
                        "validation": field.validation,
                        "image": str(field.image_id) if field.image_id else None,
                        "image_url": field.image.get_absolute_url() if field.image_id else "",
                        "options": [
                            {
                                "label": option.label,
                                "value": option.value,
                                "is_active": option.is_active,
                            }
                            for option in field.options.all()
                        ],
                    }
                    for field in fields
                    if field.section_id == section.pk
                ],
            }
        )
    data = {
        "version": str(version.pk),
        "number": version.version_number,
        "status": version.status,
        "title": version.title or form.name,
        "description": version.description if version.title else form.description,
        "appearance": version.appearance,
        "welcome": {
            **version.welcome,
            "image": str(version.welcome_image_id) if version.welcome_image_id else None,
            "image_url": version.welcome_image.get_absolute_url() if version.welcome_image_id else "",
        },
        "sections": sections,
        "rules": [
            {
                "source": str(rule.source_field_id),
                "operator": rule.operator,
                "expected": rule.expected_value,
                "action": rule.action,
                "target_field": str(rule.target_field_id) if rule.target_field_id else None,
                "target_section": str(rule.target_section_id) if rule.target_section_id else None,
                "group_key": rule.group_key,
                "group_operator": rule.group_operator,
            }
            for rule in version.rules.all()
        ],
    }
    data["fingerprint"] = hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=True).encode()
    ).hexdigest()
    data["settings"] = {
        "status": form.status,
        "status_label": "No publicado" if form.status == Form.Status.DRAFT else form.get_status_display(),
        "active_version": form.active_version.version_number if form.active_version_id else None,
        "created_by": form.created_by.get_full_name() or form.created_by.get_username(),
        "created_at": form.created_at.isoformat(),
        "updated_at": form.updated_at.isoformat(),
        "versions": [
            {"number": item.version_number, "status": "Guardada" if item.status == FormVersion.Status.DRAFT else item.get_status_display(),
             "schema_version": item.schema_version, "created_at": item.created_at.isoformat(),
             "published_at": item.published_at.isoformat() if item.published_at else None}
            for item in form.versions.order_by("-version_number")
        ],
    }
    return data


def text_value(data, key, limit, default=""):
    value = data.get(key, default)
    if not isinstance(value, str) or len(value) > limit:
        raise ValidationError(f"Revisa «{key}» (máximo {limit} caracteres).")
    return value.strip()


def object_value(data, key):
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ValidationError(f"«{key}» debe ser un objeto.")
    return value


def rows(data, key, limit):
    value = data.get(key, [])
    if (
        not isinstance(value, list)
        or len(value) > limit
        or any(not isinstance(x, dict) for x in value)
    ):
        raise ValidationError(f"Revisa «{key}» (máximo {limit} elementos).")
    return value


@transaction.atomic
def save_document(form_id, data, publish=False):
    form = Form.objects.select_for_update().get(pk=form_id)
    if form.deleted_at or form.status == "ARCHIVED":
        raise ValidationError("Este formulario no se puede editar.")
    version = current_version(form)
    if version:
        version = FormVersion.objects.select_for_update().get(pk=version.pk)
        if data.get("fingerprint") != document(version)["fingerprint"]:
            raise StaleDraft("Hay cambios más recientes. Recarga la página antes de guardar.")
    elif data.get("version"):
        raise StaleDraft("La versión cambió. Recarga la página.")
    title = text_value(data, "title", 200) or "Formulario sin título"
    description = text_value(data, "description", 10000)
    appearance = validate_appearance(object_value(data, "appearance"), form)
    welcome = object_value(data, "welcome")
    welcome_config = {
        "title": text_value(welcome, "title", 200),
        "text": text_value(welcome, "text", 10000),
        "button_label": text_value(welcome, "button_label", 60) or "Comenzar",
        "horizontal": text_value(welcome, "horizontal", 10, "right"),
        "vertical": text_value(welcome, "vertical", 10, "center"),
    }
    if welcome_config["horizontal"] not in {"left", "center", "right"} or welcome_config["vertical"] not in {"top", "center", "bottom"}:
        raise ValidationError("Selecciona una posición válida para el recuadro de bienvenida.")
    welcome_image = None
    if welcome.get("image"):
        try:
            welcome_image = form.images.get(pk=welcome["image"])
        except (ValueError, TypeError, ValidationError, form.images.model.DoesNotExist):
            raise ValidationError("La imagen de bienvenida no pertenece a este formulario.") from None
    sections_data = rows(data, "sections", 50)
    if sum(len(rows(s, "fields", 200)) for s in sections_data) > 200:
        raise ValidationError("El formulario admite hasta 200 preguntas o bloques.")
    rules_data = rows(data, "rules", 300)
    if not version or version.status != "DRAFT":
        number = (form.versions.aggregate(n=Max("version_number"))["n"] or 0) + 1
        version = FormVersion.objects.create(form=form, version_number=number)
    # The form/version locks above exclude publication and concurrent editor writes.
    version.rules.all().delete()
    version.sections.all().delete()
    version.title, version.description = title, description
    version.welcome, version.welcome_image = welcome_config, welcome_image
    version.appearance = appearance
    version.save()
    sections, fields = {}, {}
    for i, section_data in enumerate(sections_data):
        key = text_value(section_data, "id", 100)
        if not key or key in sections:
            raise ValidationError("Identificador de sección duplicado o vacío.")
        configuration = object_value(section_data, "configuration")
        if not isinstance(configuration.get("hide_header", False), bool):
            raise ValidationError("Revisa la opción de mostrar el título de la sección.")
        section = FormSection.objects.create(
            form_version=version,
            order=i,
            title=text_value(section_data, "title", 200) or "Sección sin título",
            description=text_value(section_data, "description", 10000),
            configuration=configuration,
        )
        sections[key] = section
        for j, field_data in enumerate(rows(section_data, "fields", 200)):
            key = text_value(field_data, "id", 100)
            if not key or key in fields:
                raise ValidationError("Identificador de pregunta duplicado o vacío.")
            kind = text_value(field_data, "field_type", 20)
            image = None
            if field_data.get("image"):
                try:
                    image = form.images.get(pk=field_data["image"])
                except (ValueError, TypeError, ValidationError, form.images.model.DoesNotExist):
                    raise ValidationError("La imagen no pertenece a este formulario.") from None
            if kind == "IMAGE" and not image:
                raise ValidationError("Selecciona una imagen o elimina el bloque de imagen vacío.")
            if not isinstance(field_data.get("required", False), bool):
                raise ValidationError("Revisa si la pregunta es obligatoria.")
            field = FormField.objects.create(
                form_version=version,
                section=section,
                order=j,
                stable_key=text_value(field_data, "stable_key", 100) or f"q_{uuid.uuid4().hex}",
                label=text_value(field_data, "label", 240) or "Pregunta sin título",
                help_text=text_value(field_data, "help_text", 10000),
                field_type=kind,
                required=field_data.get("required", False),
                placeholder=text_value(field_data, "placeholder", 240),
                configuration=object_value(field_data, "configuration"),
                validation=object_value(field_data, "validation"),
                image=image,
            )
            fields[key] = field
            options = rows(field_data, "options", 100)
            if options and kind not in CHOICE_TYPES:
                raise ValidationError("Sólo las preguntas de selección admiten opciones.")
            for k, option in enumerate(options):
                FieldOption.objects.create(
                    field=field,
                    order=k,
                    label=text_value(option, "label", 240),
                    value=text_value(option, "value", 150),
                    is_active=option.get("is_active", True),
                )
    # Section ids are regenerated on every draft save; remap navigation as well.
    for section_data in sections_data:
        section = sections[text_value(section_data, "id", 100)]
        destination = section.configuration.get("next_section", "NEXT")
        if not isinstance(destination, str):
            raise ValidationError("Selecciona un destino válido para la sección.")
        if destination not in {"NEXT", "SUBMIT"}:
            if destination not in sections:
                raise ValidationError("La sección de destino ya no existe. Revisa la navegación.")
            section.configuration = {
                **section.configuration,
                "next_section": str(sections[destination].pk),
            }
            section.save(update_fields=["configuration"])
    for i, rule in enumerate(rules_data):
        source = fields.get(rule.get("source"))
        target_field = fields.get(rule.get("target_field"))
        target_section = sections.get(rule.get("target_section"))
        if not source or (bool(target_field) == bool(target_section)):
            raise ValidationError(
                "Selecciona una pregunta de origen y un destino para cada condición."
            )
        ConditionalRule.objects.create(
            form_version=version,
            source_field=source,
            target_field=target_field,
            target_section=target_section,
            order=i,
            operator=text_value(rule, "operator", 20),
            expected_value=rule.get("expected"),
            action=text_value(rule, "action", 12),
            group_key=rule.get("group_key") or None,
            group_operator=text_value(rule, "group_operator", 3, "AND"),
        )
    FormSchema(version)  # Validate values and reject cycles before committing any changes.
    form.name, form.description = title, description
    form.save(update_fields=["name", "description", "updated_at"])
    if publish or form.status in {Form.Status.PUBLISHED, Form.Status.PAUSED}:
        from .publication import publish_form

        publish_form(form.pk, preserve_access=not publish)
        version.refresh_from_db()
    # A draft loaded before the save may still cache the older form metadata.
    form.refresh_from_db()
    version.form = form
    return document(version)
