from django.contrib import admin
from django.db.models import Exists, OuterRef, Q
from django.urls import path, reverse
from django.utils.html import format_html_join

from apps.forms.admin import PlatformAdmin
from apps.forms.models import FieldOption

from .models import Submission, SubmissionAnswer, SubmissionFile, SubmissionReview


def selected_option_matches(queryset, search_term):
    """Find responses whose selected choice has a matching display label."""
    options_by_field = {}
    for field_id, value in FieldOption.objects.filter(label__icontains=search_term).values_list(
        "field_id", "value"
    ):
        options_by_field.setdefault(field_id, set()).add(value)
    if not options_by_field:
        return set()

    matches = set()
    answers = SubmissionAnswer.objects.filter(
        submission_id__in=queryset.values("pk"), field_id__in=options_by_field
    ).values_list("submission_id", "field_id", "value")
    for submission_id, field_id, value in answers.iterator():
        selected = value.get("selected") if isinstance(value, dict) else value
        selected = selected if isinstance(selected, list) else [selected]
        if any(item in options_by_field[field_id] for item in selected if isinstance(item, str)):
            matches.add(submission_id)
    return matches


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
    search_help_text = "Buscar en respuestas, preguntas, opciones, archivos o formularios"
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
        return request.user.has_perm("submissions.delete_submission") and (
            obj is None or obj.can_mutate(request.user)
        )

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and (
            obj is None or obj.can_mutate(request.user)
        )

    def get_urls(self):
        from .admin_views import (
            response_attention,
            response_delete,
            response_detail,
            response_edit,
            response_note,
            response_panel,
            response_review,
        )
        from .export import response_download, responses_download
        from .reports import report_documents, report_excel, report_preview
        from .trash import response_purge, response_restore, response_trash

        urls = [
            path(
                "trash/",
                self.admin_site.admin_view(lambda request: response_trash(self, request)),
                name="submissions_submission_trash",
            ),
            path(
                "reports/",
                self.admin_site.admin_view(lambda request: report_preview(self, request)),
                name="submissions_submission_reports",
            ),
            path(
                "report/excel/",
                self.admin_site.admin_view(lambda request: report_excel(self, request)),
                name="submissions_submission_report_excel",
            ),
            path(
                "report/documents/",
                self.admin_site.admin_view(lambda request: report_documents(self, request)),
                name="submissions_submission_report_documents",
            ),
            path(
                "download/",
                self.admin_site.admin_view(lambda request: responses_download(self, request)),
                name="submissions_submission_download_selected",
            ),
            path(
                "<uuid:object_id>/panel/",
                self.admin_site.admin_view(
                    lambda request, object_id: response_panel(self, request, object_id)
                ),
                name="submissions_submission_panel",
            ),
            path(
                "<uuid:object_id>/note/",
                self.admin_site.admin_view(
                    lambda request, object_id: response_note(self, request, object_id)
                ),
                name="submissions_submission_note",
            ),
        ]
        for operation, handler in (
            ("detail", response_detail),
            ("edit", response_edit),
            ("remove", response_delete),
            ("review", response_review),
            ("attention", response_attention),
            ("download", response_download),
            ("documents", report_documents),
            ("restore", response_restore),
            ("purge", response_purge),
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
        search_term = search_term.strip()
        if search_term:
            matches = SubmissionAnswer.objects.filter(submission_id=OuterRef("pk")).filter(
                Q(value__icontains=search_term)
                | Q(field__label__icontains=search_term)
                | Q(field__section__title__icontains=search_term)
            )
            files = SubmissionFile.objects.filter(
                answer__submission_id=OuterRef("pk"), original_name__icontains=search_term
            )
            reviews = SubmissionReview.objects.filter(
                submission_id=OuterRef("pk"), note__icontains=search_term
            )
            option_matches = selected_option_matches(queryset, search_term)
            queryset = queryset.filter(
                Q(form__name__icontains=search_term)
                | Q(attention_note__icontains=search_term)
                | Q(pk__in=option_matches)
                | Exists(matches)
                | Exists(files)
                | Exists(reviews)
            )
        return queryset, False

    @admin.display(description="Datos recibidos")
    def answer_details(self, obj):
        from .presentation import render_response_details, response_sections

        return render_response_details(response_sections(obj))
