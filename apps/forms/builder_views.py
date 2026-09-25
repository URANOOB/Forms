import io
import json
import uuid
import warnings

from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.http import FileResponse, Http404, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.accounts.models import legacy_form_container
from apps.submissions.runtime import PublicResponseForm

from .appearance import theme_context
from .builder import StaleDraft, current_version, document, save_document, text_value
from .conditions import FormSchema
from .models import Form, FormField, FormImage, FormVersion
from .presets import PRESETS
from .welcome import welcome_data


def editor_field_types():
    labels = dict(FormField.Type.choices)
    labels["NUMBER"] = "Numérico"
    labels["PHONE"] = "Número de teléfono"
    labels["DROPDOWN"] = "Desplegable"
    labels["DROPDOWN_EXTRA"] = "Desplegable con opción adicional"
    labels["DROPDOWN_SEARCH"] = "Desplegable con búsqueda"
    order = [
        "SHORT_TEXT",
        "LONG_TEXT",
        "NUMBER",
        "EMAIL",
        "PHONE",
        "SINGLE_CHOICE",
        "MULTIPLE_CHOICE",
        "DROPDOWN",
        "DROPDOWN_SEARCH",
        "DROPDOWN_EXTRA",
        "FILE",
        "LINEAR_SCALE",
        "RATING",
        "GRID_SINGLE",
        "GRID_MULTIPLE",
        "DATE",
        "TIME",
        "BOOLEAN",
        "HEADING",
        "INFORMATION",
        "IMAGE",
    ]
    return [(key, labels[key]) for key in order]


def new_document(preset_key):
    preset = PRESETS.get(preset_key, {})
    fields = []
    for key, label, kind, required, *choices in preset.get("fields", []):
        fields.append(
            {
                "id": str(uuid.uuid4()),
                "stable_key": key,
                "label": label,
                "field_type": kind,
                "required": required,
                "help_text": "",
                "placeholder": "",
                "configuration": {},
                "validation": {},
                "image": None,
                "image_url": "",
                "options": [
                    {"label": label, "value": str(i + 1), "is_active": True}
                    for i, label in enumerate(choices[0] if choices else [])
                ],
            }
        )
    return {
        "version": None,
        "number": 1,
        "status": "DRAFT",
        "fingerprint": "",
        "title": preset.get("name", "Formulario sin título"),
        "description": preset.get("description", ""),
        "rules": [],
        "sections": [
            {
                "id": str(uuid.uuid4()),
                "title": "Información general",
                "description": "",
                "configuration": {},
                "fields": fields,
            }
        ]
        if fields
        else [],
    }


def new_editor_view(model_admin, request):
    if not model_admin.has_add_permission(request) or not model_admin.has_change_permission(
        request
    ):
        raise PermissionDenied
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            if not isinstance(data, dict):
                raise ValidationError("Solicitud inválida.")
            token = signing.loads(data.get("creation_token", ""), salt="new-form", max_age=86400)
            if token["user"] != str(request.user.pk):
                raise PermissionDenied
            with transaction.atomic():
                # The signed UUID makes retrying creation safe after a lost response.
                form, created = Form.objects.get_or_create(
                    pk=token["form"],
                    defaults={
                        "workspace": legacy_form_container(),
                        "created_by": request.user,
                        "name": text_value(data, "title", 200) or "Formulario sin título",
                        "slug": f"formulario-{token['form']}",
                    },
                )
                if form.created_by_id != request.user.pk:
                    raise PermissionDenied
                if created:
                    version = FormVersion.objects.create(form=form, version_number=1)
                    model_admin.log_addition(request, form, "Creó borrador en constructor")
                else:
                    version = current_version(form)
                    if (
                        form.deleted_at
                        or not version
                        or version.status != "DRAFT"
                        or version.fields.exists()
                    ):
                        raise StaleDraft("Este formulario ya se guardó. Ábrelo desde Formularios.")
                result = document(version)
                result.update(
                    editor_url=reverse("admin:forms_form_builder_edit", args=[form.pk]),
                    settings_url=reverse("admin:forms_form_change", args=[form.pk]),
                    responses_url=reverse("admin:forms_form_builder_responses", args=[form.pk])
                    if request.user.has_perm("submissions.view_submission")
                    else "",
                    share_url=form.get_public_url(request),
                )
            return JsonResponse(result)
        except StaleDraft as error:
            return JsonResponse({"error": " ".join(error.messages)}, status=409)
        except (ValidationError, signing.BadSignature, ValueError, TypeError, KeyError) as error:
            return JsonResponse(
                {
                    "error": " ".join(error.messages)
                    if isinstance(error, ValidationError)
                    else "No se pudo crear. Recarga la página e inténtalo de nuevo."
                },
                status=400,
            )
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET", "POST"])
    return render(
        request,
        "admin/forms/builder.html",
        {
            **model_admin.admin_site.each_context(request),
            "opts": model_admin.model._meta,
            "title": "Crear formulario",
            "is_new": True,
            **theme_context(),
            "builder_data": new_document(request.GET.get("template")),
            "creation_token": signing.dumps(
                {"user": str(request.user.pk), "form": str(uuid.uuid4())}, salt="new-form"
            ),
            "field_types": editor_field_types(),
        },
    )


def editor_view(model_admin, request, object_id, operation="edit"):
    form = get_object_or_404(model_admin.get_queryset(request), pk=object_id)
    if not model_admin.has_change_permission(request, form):
        raise PermissionDenied
    if operation in {"save", "publish", "pause", "resume", "unpublish", "image"}:
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if form.status == "ARCHIVED":
            return JsonResponse({"error": "El formulario está archivado."}, status=400)
        try:
            if operation == "image":
                return upload_image(request, form)
            if operation in {"pause", "resume", "unpublish"}:
                from .publication import set_form_access

                form = set_form_access(form.pk, operation)
                model_admin.log_change(
                    request,
                    form,
                    {
                        "pause": "Pausó la recepción de respuestas",
                        "resume": "Activó la recepción de respuestas",
                        "unpublish": "Desactivó el acceso público",
                    }[operation],
                )
                return JsonResponse(document(current_version(form)))
            if len(request.body) > 8 * 1024 * 1024:
                raise ValidationError("El formulario supera el tamaño permitido (8 MB).")
            data = json.loads(request.body)
            if not isinstance(data, dict):
                raise ValidationError("Formato de formulario inválido.")
            saved = save_document(form.pk, data, publish=operation == "publish")
            model_admin.log_change(
                request, form, "Publicó versión" if operation == "publish" else "Guardó constructor"
            )
            return JsonResponse(saved)
        except StaleDraft as error:
            return JsonResponse({"error": " ".join(error.messages)}, status=409)
        except IntegrityError:
            return JsonResponse(
                {
                    "error": (
                        "No se pudo guardar por un conflicto con los datos actuales. "
                        "Recarga la página e inténtalo de nuevo."
                    )
                },
                status=409,
            )
        except (ValidationError, json.JSONDecodeError, TypeError, ValueError) as error:
            message = (
                " ".join(error.messages)
                if isinstance(error, ValidationError)
                else "Revisa el formato de las preguntas y condiciones."
            )
            return JsonResponse({"error": message}, status=400)
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    if operation == "responses":
        from .builder_responses import responses_view

        return responses_view(model_admin, request, form)
    version = current_version(form)
    if not version:
        raise Http404
    if operation == "preview":
        try:
            schema = FormSchema(version)
        except ValidationError as error:
            return JsonResponse({"error": " ".join(error.messages)}, status=400)
        response_form = PublicResponseForm(schema)
        return render(
            request,
            "public/form.html",
            {
                "form": form,
                "form_title": version.title or form.name,
                "form_description": version.description if version.title else form.description,
                "response_form": response_form,
                "sections": response_form.section_rows(),
                "schema": schema.browser_spec(),
                "preview": True,
                "welcome": welcome_data(version),
                "appearance": version.appearance,
            },
        )
    context = {
        **model_admin.admin_site.each_context(request),
        "opts": model_admin.model._meta,
        "title": "Constructor de formularios",
        **theme_context(),
        "form": form,
        "builder_data": document(version),
        "field_types": editor_field_types(),
        "share_url": form.get_public_url(request),
        "responses_url": reverse("admin:forms_form_builder_responses", args=[form.pk])
        if request.user.has_perm("submissions.view_submission")
        else "",
    }
    return render(request, "admin/forms/builder.html", context)


def upload_image(request, form):
    upload = request.FILES.get("image")
    if not upload or upload.size > 5 * 1024 * 1024:
        raise ValidationError("Selecciona una imagen PNG, JPG o WebP de hasta 5 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(upload) as original:
                if (
                    original.format not in {"PNG", "JPEG", "WEBP"}
                    or original.width * original.height > 20_000_000
                ):
                    raise ValidationError("Usa PNG, JPG o WebP con un máximo de 20 megapíxeles.")
                original.load()
                normalized = ImageOps.exif_transpose(original).convert("RGBA")
                normalized.thumbnail((2400, 2400))
                # Fresh pixels strip EXIF/text metadata and any non-image payload.
                clean = Image.new("RGBA", normalized.size)
                clean.paste(normalized)
                buffer = io.BytesIO()
                clean.save(buffer, format="PNG")
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise ValidationError(
            "No se pudo leer la imagen. Usa un archivo PNG, JPG o WebP válido."
        ) from None
    asset = FormImage(form=form)
    asset.file.save(f"{uuid.uuid4().hex}.png", ContentFile(buffer.getvalue()), save=False)
    try:
        asset.save()
    except Exception:
        asset.file.delete(save=False)
        raise
    return JsonResponse({"id": str(asset.pk), "url": asset.get_absolute_url()})


@never_cache
@require_GET
def form_image(request, image_id):
    asset = get_object_or_404(FormImage.objects.select_related("form__workspace"), pk=image_id)
    form = asset.form
    public = (
        form.status in {"PUBLISHED", "PAUSED"}
        and not form.deleted_at
        and form.active_version_id
        and (
            form.active_version.welcome_image_id == asset.pk
            or form.active_version.appearance.get("header_image") == str(asset.pk)
            or form.active_version.fields.filter(image=asset).exists()
            or form.active_version.fields.filter(
                options__image=asset, options__is_active=True
            ).exists()
        )
    )
    user = request.user
    private = user.is_active and user.is_staff and user.has_perm("forms.change_form")
    if not public and not private:
        raise Http404
    try:
        response = FileResponse(asset.file.open("rb"), content_type="image/png")
    except FileNotFoundError:
        raise Http404 from None
    response["X-Content-Type-Options"] = "nosniff"
    return response
