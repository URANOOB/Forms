from pathlib import PurePath

from django.contrib import admin
from django.db.models import Exists, OuterRef, Q
from django.template.loader import render_to_string
from django.urls import path, reverse
from django.utils.html import format_html_join
from django.utils.safestring import mark_safe

from apps.forms.admin import PlatformAdmin

from .models import Submission, SubmissionAnswer


class FormFilter(admin.SimpleListFilter):
    title = "formulario"
    parameter_name = "form"

    def lookups(self, request, model_admin):
        return list(
            model_admin.get_queryset(request)
            .order_by("form__name")
            .values_list("form_id", "form__name")
            .distinct()
        )

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(form_id=self.value())
        return queryset


@admin.register(Submission)
class SubmissionAdmin(PlatformAdmin):
    list_display = ["__str__", "form", "form_version", "submitted_at", "status"]
    list_filter = [FormFilter, "status", ("submitted_at", admin.DateFieldListFilter)]
    list_select_related = ["form", "form_version__form", "form__workspace"]
    search_fields = ["form__name"]
    search_help_text = "Buscar en los datos recibidos o en el nombre del formulario"
    readonly_fields = ["id", "form", "form_version", "submitted_at", "answer_details"]
    fields = ["id", "form", "form_version", "submitted_at", "status", "answer_details"]
    actions = None

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm("submissions.delete_submission")

    def get_urls(self):
        from .admin_views import response_delete, response_detail, response_edit

        urls = []
        for operation, handler in (
            ("detail", response_detail),
            ("edit", response_edit),
            ("remove", response_delete),
        ):

            def view(request, object_id, handler=handler):
                return handler(self, request, object_id)

            urls.append(
                path(
                    f"<uuid:object_id>/{operation}/",
                    self.admin_site.admin_view(view),
                    name=f"submissions_submission_{operation}",
                )
            )
        return urls + super().get_urls()

    def get_list_display(self, request):
        @admin.display(description="Acciones")
        def response_actions(obj):
            actions = [("detail", "visibility", "Ver respuesta", "#52647a")]
            if self.has_change_permission(request, obj):
                actions.append(("edit", "edit", "Editar respuesta", "#6941c6"))
            if self.has_delete_permission(request, obj):
                actions.append(("remove", "delete", "Eliminar respuesta", "#b42318"))
            return format_html_join(
                " ",
                '<a href="{}" title="{}" aria-label="{}" '
                'style="display:inline-flex;align-items:center;justify-content:center;'
                'width:36px;height:36px;border-radius:6px;color:{}">'
                '<span class="material-symbols-outlined" aria-hidden="true">{}</span></a>',
                [
                    (
                        reverse(f"admin:submissions_submission_{operation}", args=[obj.pk]),
                        label,
                        label,
                        color,
                        icon,
                    )
                    for operation, icon, label, color in actions
                ],
            )

        return [*self.list_display, response_actions]

    def change_view(self, request, object_id, form_url="", extra_context=None):
        from .admin_views import response_detail

        return response_detail(self, request, object_id)

    def delete_view(self, request, object_id, extra_context=None):
        from .admin_views import response_delete

        return response_delete(self, request, object_id)

    def get_search_results(self, request, queryset, search_term):
        if search_term:
            matches = SubmissionAnswer.objects.filter(
                submission_id=OuterRef("pk"), value__icontains=search_term
            )
            queryset = queryset.filter(Exists(matches) | Q(form__name__icontains=search_term))
        return queryset, False

    @admin.display(description="Datos recibidos")
    def answer_details(self, obj):
        sections = {}
        answers = (
            obj.answers.select_related("field__section")
            .prefetch_related("field__options", "files")
            .order_by("field__section__order", "field__section_id", "field__order", "field_id")
        )
        for answer in answers:
            section = answer.field.section
            bucket = sections.setdefault(section.pk, {"title": section.title, "answers": []})
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
                text = "" if attachments else "Sin archivos"
            elif answer.field.field_type in {"GRID_SINGLE", "GRID_MULTIPLE"}:
                config = answer.field.configuration
                columns = {column["id"]: column["label"] for column in config.get("columns", [])}
                value = value if isinstance(value, dict) else {}
                lines = []
                for row in config.get("rows", []):
                    selected = value.get(row["id"], [])
                    selected = selected if isinstance(selected, list) else [selected]
                    result = (
                        ", ".join(columns.get(item, item) for item in selected) or "Sin respuesta"
                    )
                    lines.append(f"{row['label']}: {result}")
                text = "\n".join(lines)
            elif answer.field.field_type in {"LINEAR_SCALE", "RATING"} and value is not None:
                text = f"{value} de {answer.field.configuration.get('max', 5)}"
            elif answer.field.field_type == "SINGLE_CHOICE" and isinstance(value, dict):
                selected = value.get("selected", "")
                label = options.get(selected, selected) or "Sin respuesta"
                detail = value.get("text", "")
                text = f"{label}: {detail}" if detail else label
            elif isinstance(value, bool):
                text = "Sí" if value else "No"
            elif isinstance(value, list):
                text = ", ".join(options.get(item, item) for item in value) or "Sin respuesta"
            elif value is None or value == "":
                text = "Sin respuesta"
            else:
                text = options.get(str(value), str(value))
            bucket["answers"].append(
                {
                    "label": answer.field.label,
                    "value": text,
                    "files": attachments,
                    "wide": answer.field.field_type
                    in {"FILE", "DOCUMENT", "LONG_TEXT", "GRID_SINGLE", "GRID_MULTIPLE"},
                    "empty": not attachments and (value is None or value == "" or value == []),
                }
            )
        return mark_safe(
            render_to_string("admin/submissions/answers.html", {"sections": sections.values()})
        )
