from django.db.models import Prefetch, prefetch_related_objects
from django.urls import reverse
from unfold.views import ChangeList

from .models import FormField, FormVersion


class GalleryChangeList(ChangeList):
    def get_filters_params(self, params=None):
        filters = super().get_filters_params(params)
        for name in ("owner", "sort"):
            filters.pop(name, None)
        if filters.get("status__exact") in ("", [""]):
            filters.pop("status__exact")
        return filters


def gallery_context(request, changelist):
    forms = list(changelist.result_list)
    fields = FormField.objects.order_by("section__order", "section_id", "order", "id")[:4]
    versions = FormVersion.objects.order_by("-version_number").prefetch_related(
        Prefetch("fields", queryset=fields, to_attr="preview_fields")
    )[:1]
    prefetch_related_objects(
        forms, Prefetch("versions", queryset=versions, to_attr="preview_versions")
    )
    themes = ["lavender", "mint", "sand", "blue", "peach", "rose"]
    cards = []
    for form in forms:
        version = next(iter(form.preview_versions), None)
        cards.append(
            {
                "form": form,
                "fields": version.preview_fields if version else [],
                "theme": themes[form.pk.int % len(themes)],
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
    return {
        "cards": cards,
        "gallery_owner": request.GET.get("owner", ""),
        "gallery_sort": request.GET.get("sort", "recent"),
        "gallery_status": request.GET.get("status__exact", ""),
        "can_view_responses": request.user.has_perm("submissions.view_submission"),
    }
