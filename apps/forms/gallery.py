from datetime import datetime, time, timedelta

from django.db.models import Count, Prefetch, prefetch_related_objects
from django.urls import reverse
from django.utils import timezone
from django.utils.timesince import timesince
from unfold.views import ChangeList

from apps.submissions.models import Submission

from .models import FormField, FormVersion


def filter_updated(queryset, period):
    days = {"today": 1, "week": 7, "month": 30}.get(period)
    if not days:
        return queryset
    today = timezone.localdate()
    start = timezone.make_aware(datetime.combine(today - timedelta(days=days - 1), time.min))
    end = timezone.make_aware(datetime.combine(today + timedelta(days=1), time.min))
    return queryset.filter(updated_at__gte=start, updated_at__lt=end)


class GalleryChangeList(ChangeList):
    def get_filters_params(self, params=None):
        filters = super().get_filters_params(params)
        for name in ("owner", "sort", "updated"):
            filters.pop(name, None)
        if filters.get("status__exact") in ("", [""]):
            filters.pop("status__exact")
        return filters


def gallery_context(request, changelist):
    forms = list(changelist.result_list)
    response_counts = dict(
        Submission.objects.filter(form_id__in=[form.pk for form in forms])
        .values("form_id")
        .annotate(total=Count("pk"))
        .values_list("form_id", "total")
    )
    fields = FormField.objects.order_by("section__order", "section_id", "order", "id")[:4]
    versions = FormVersion.objects.order_by("-version_number").prefetch_related(
        Prefetch("fields", queryset=fields, to_attr="preview_fields")
    )[:1]
    prefetch_related_objects(
        forms, Prefetch("versions", queryset=versions, to_attr="preview_versions")
    )
    themes = ["lavender", "mint", "sand", "blue", "peach", "rose"]
    cards = []
    now = timezone.now()
    for form in forms:
        version = next(iter(form.preview_versions), None)
        cards.append(
            {
                "form": form,
                "fields": version.preview_fields if version else [],
                "theme": themes[form.pk.int % len(themes)],
                "response_count": response_counts.get(form.pk, 0),
                "owner_name": form.created_by.get_full_name() or form.created_by.get_username(),
                "updated_label": "Actualizado hace unos instantes"
                if (now - form.updated_at).total_seconds() < 60
                else f"Actualizado hace {timesince(form.updated_at, now).split(',')[0]}",
                "edit_url": reverse(
                    "admin:forms_form_builder_edit"
                    if request.user.has_perm("forms.change_form")
                    else "admin:forms_form_change",
                    args=[form.pk],
                ),
                "public_url": request.build_absolute_uri(form.get_absolute_url()),
                "responses_url": reverse("admin:submissions_submission_changelist")
                + f"?form={form.pk}",
            }
        )
    filter_count = sum(
        (
            request.GET.get("owner") == "mine",
            request.GET.get("status__exact", "") != "",
            request.GET.get("updated") in {"today", "week", "month"},
            request.GET.get("sort", "recent") in {"name", "oldest"},
        )
    )
    page = changelist.page_num
    return {
        "cards": cards,
        "gallery_owner": request.GET.get("owner", ""),
        "gallery_sort": request.GET.get("sort", "recent"),
        "gallery_status": request.GET.get("status__exact", ""),
        "gallery_updated": request.GET.get("updated", ""),
        "gallery_filter_count": filter_count,
        "gallery_clear_url": changelist.get_query_string(
            remove=["owner", "status__exact", "updated", "sort", "p"]
        ),
        "gallery_previous_url": changelist.get_query_string({"p": page - 1}) if page > 1 else "",
        "gallery_next_url": changelist.get_query_string({"p": page + 1})
        if page < changelist.paginator.num_pages
        else "",
        "can_view_responses": request.user.has_perm("submissions.view_submission"),
    }
