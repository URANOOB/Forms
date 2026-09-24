from django.contrib import admin
from django.db.models import Exists, OuterRef, Q
from django.urls import path, reverse
from django.utils.html import format_html_join

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
    change_list_template = "admin/submissions/board.html"
    list_fullwidth = True
    list_display = ["__str__", "form", "form_version", "submitted_at", "status"]
    list_filter = [FormFilter, "status", ("submitted_at", admin.DateFieldListFilter)]
    list_select_related = ["form", "form_version__form", "form__workspace"]
    search_fields = ["form__name"]
    search_help_text = "Buscar en los datos recibidos o en el nombre del formulario"
    readonly_fields = ["id", "form", "form_version", "submitted_at", "answer_details"]
    fields = ["id", "form", "form_version", "submitted_at", "status", "answer_details"]
    actions = None

    def get_changelist(self, request, **kwargs):
        from .board import ResponseChangeList

        return ResponseChangeList

    def changelist_view(self, request, extra_context=None):
        from .board import board_context

        response = super().changelist_view(request, extra_context)
        if getattr(response, "context_data", None) and "cl" in response.context_data:
            response.context_data.update(board_context(request, response.context_data["cl"], self))
        return response

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm("submissions.delete_submission")

    def get_urls(self):
        from .admin_views import (
            response_attention,
            response_delete,
            response_detail,
            response_edit,
            response_review,
        )
        from .export import response_download, responses_download

        urls = [
            path(
                "download/",
                self.admin_site.admin_view(lambda request: responses_download(self, request)),
                name="submissions_submission_download_selected",
            )
        ]
        for operation, handler in (
            ("detail", response_detail),
            ("edit", response_edit),
            ("remove", response_delete),
            ("review", response_review),
            ("attention", response_attention),
            ("download", response_download),
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
        from .presentation import render_response_details, response_sections

        return render_response_details(response_sections(obj))
