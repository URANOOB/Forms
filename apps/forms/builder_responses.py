from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string

from apps.submissions.models import Submission


def responses_view(model_admin, request, form):
    submission_admin = model_admin.admin_site._registry[Submission]
    if not submission_admin.has_view_permission(request):
        raise PermissionDenied
    queryset = submission_admin.get_queryset(request).filter(form=form)
    if response_id := request.GET.get("response"):
        try:
            submission = get_object_or_404(queryset, pk=response_id)
        except (ValidationError, ValueError):
            raise Http404
        if not submission_admin.has_view_permission(request, submission):
            raise PermissionDenied
        return JsonResponse({"html": str(submission_admin.answer_details(submission))})

    total = queryset.count()
    queryset, duplicates = submission_admin.get_search_results(
        request, queryset, request.GET.get("q", "").strip()[:200]
    )
    if duplicates:
        queryset = queryset.distinct()
    page = Paginator(queryset.select_related("form_version").order_by("-submitted_at", "-pk"), 25).get_page(request.GET.get("page", 1))
    rows = [
        {
            "submission": submission,
            "can_edit": submission_admin.has_change_permission(request, submission),
            "can_delete": submission_admin.has_delete_permission(request, submission),
        }
        for submission in page
        if submission_admin.has_view_permission(request, submission)
    ]
    return JsonResponse({
        "html": render_to_string("admin/forms/responses.html", {"rows": rows, "page": page}, request=request),
        "total": total,
        "count": page.paginator.count,
    })
