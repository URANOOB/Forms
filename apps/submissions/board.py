import uuid
from datetime import date

from django.contrib.auth import get_user_model
from django.db.models import Count, Exists, OuterRef
from django.template.loader import render_to_string
from unfold.views import ChangeList

from .models import Submission, SubmissionFile
from .panel import panel_context
from .review import TRANSITIONS
from .summary import load_summary_data, summary_for

BOARD_LIMIT = 12
WORK_PARAMS = {
    "view",
    "response_status",
    "response_form",
    "response_from",
    "response_to",
    "response_assignee",
    "response_documents",
    "response_order",
    "selected",
}


def apply_work_filters(queryset, request, *, include_status=True):
    params = request.GET
    status = params.get("response_status") or params.get("status__exact")
    if include_status and status in Submission.Status.values:
        queryset = queryset.filter(status=status)
    try:
        form_id = uuid.UUID(params.get("response_form") or params.get("form") or "")
    except ValueError:
        form_id = None
    if form_id:
        queryset = queryset.filter(form_id=form_id)
    for keys, lookup in (
        (("response_from", "submitted_at__gte"), "submitted_at__date__gte"),
        (("response_to", "submitted_at__lte"), "submitted_at__date__lte"),
    ):
        try:
            value = date.fromisoformat(params.get(keys[0]) or params.get(keys[1]) or "")
        except ValueError:
            continue
        queryset = queryset.filter(**{lookup: value})
    assignee = params.get("response_assignee", "")
    if assignee == "unassigned":
        queryset = queryset.filter(assigned_to__isnull=True)
    else:
        try:
            assignee_id = uuid.UUID(assignee)
        except ValueError:
            assignee_id = None
        if assignee_id:
            queryset = queryset.filter(assigned_to_id=assignee_id)
    if params.get("response_documents") == "1":
        files = SubmissionFile.objects.filter(answer__submission_id=OuterRef("pk"))
        queryset = queryset.filter(Exists(files))
    return queryset


class ResponseChangeList(ChangeList):
    def get_filters_params(self, params=None):
        filters = super().get_filters_params(params)
        for key in WORK_PARAMS:
            filters.pop(key, None)
        return filters

    def get_queryset(self, request, exclude_parameters=None):
        queryset = apply_work_filters(super().get_queryset(request, exclude_parameters), request)
        order = request.GET.get("response_order")
        if order == "oldest":
            return queryset.order_by("submitted_at", "pk")
        return queryset


def board_context(request, changelist, model_admin):
    layout = request.GET.get("view", "work")
    if layout not in {"work", "list", "board"}:
        layout = "work"
    base = model_admin.get_queryset(request)
    if changelist.query:
        base, _ = model_admin.get_search_results(request, base, changelist.query)
    base = apply_work_filters(base, request, include_status=False)
    counts = dict(
        base.order_by().values("status").annotate(total=Count("pk")).values_list("status", "total")
    )
    columns = []
    rows = []
    if layout == "board":
        for status, label in Submission.Status.choices:
            cards = list(base.filter(status=status)[:BOARD_LIMIT])
            columns.append(
                {
                    "status": status,
                    "label": label,
                    "help": {
                        "SUBMITTED": "Pendientes",
                        "UNDER_REVIEW": "En proceso",
                        "VALIDATED": "Aceptadas",
                        "REJECTED": "No aceptadas",
                    }[status],
                    "total": counts.get(status, 0),
                    "cards": cards,
                    "has_more": counts.get(status, 0) > len(cards),
                    "all_url": changelist.get_query_string(
                        {"view": "work", "response_status": status},
                        ["p", "selected", "status__exact"],
                    ),
                }
            )
        submissions = [item for column in columns for item in column["cards"]]
    else:
        submissions = list(changelist.result_list)
    load_summary_data(submissions)

    def card(submission):
        return {
            "submission": submission,
            **summary_for(submission),
            "can_review": model_admin.has_change_permission(request, submission)
            and (
                submission.status != Submission.Status.UNDER_REVIEW
                or not submission.assigned_to_id
                or submission.assigned_to_id == request.user.pk
                or request.user.is_superuser
            ),
            "transitions": TRANSITIONS[submission.status],
        }

    if layout == "board":
        for column in columns:
            column["cards"] = [card(item) for item in column["cards"]]
    else:
        rows = [card(item) for item in submissions]
    selected_card = next(
        (item for item in rows if str(item["submission"].pk) == request.GET.get("selected")),
        rows[0] if rows else None,
    )
    form_choices = list(
        model_admin.get_queryset(request)
        .order_by("form__name")
        .values_list("form_id", "form__name")
        .distinct()
    )
    assignee_choices = list(
        get_user_model().objects.filter(is_staff=True).order_by("first_name", "last_name", "pk")
    )
    filter_values = {
        "response_status": request.GET.get("response_status")
        or request.GET.get("status__exact")
        or "",
        "response_form": request.GET.get("response_form") or request.GET.get("form") or "",
        "response_from": request.GET.get("response_from")
        or request.GET.get("submitted_at__gte")
        or "",
        "response_to": request.GET.get("response_to") or request.GET.get("submitted_at__lte") or "",
        "response_assignee": request.GET.get("response_assignee", ""),
        "response_documents": request.GET.get("response_documents", ""),
        "response_order": request.GET.get("response_order", ""),
    }
    selected_panel_html = ""
    if selected_card and layout == "work":
        selected_panel_html = render_to_string(
            "admin/submissions/responses/_detail_panel.html",
            panel_context(selected_card["submission"], request, model_admin),
            request=request,
        )
    return {
        "response_layout": layout,
        "response_columns": columns,
        "board_can_drag": any(
            card["can_review"] and card["transitions"]
            for column in columns
            for card in column["cards"]
        ),
        "board_url": changelist.get_query_string(
            {"view": "board"}, ["p", "response_status", "status__exact", "selected"]
        ),
        "list_url": changelist.get_query_string({"view": "list"}, ["p"]),
        "review_transitions": TRANSITIONS,
        "response_rows": rows,
        "selected_card": selected_card,
        "selected_panel_html": selected_panel_html,
        "status_cards": [
            {
                "value": status,
                "label": {
                    "SUBMITTED": "Pendientes",
                    "UNDER_REVIEW": "En revisión",
                    "VALIDATED": "Validadas",
                    "REJECTED": "Rechazadas",
                }[status],
                "help": {
                    "SUBMITTED": "Requieren tu revisión",
                    "UNDER_REVIEW": "En proceso",
                    "VALIDATED": "Aceptadas",
                    "REJECTED": "No aceptadas",
                }[status],
                "count": counts.get(status, 0),
                "url": changelist.get_query_string(
                    {"response_status": status, "view": "work"}, ["p", "selected", "status__exact"]
                ),
                "active": filter_values["response_status"] == status,
            }
            for status, _ in Submission.Status.choices
        ],
        "total_matching_count": sum(counts.values()),
        "work_url": changelist.get_query_string({"view": "work"}, ["p"]),
        "filter_form_choices": [{"id": str(pk), "name": name} for pk, name in form_choices],
        "filter_assignee_choices": [
            {"id": str(user.pk), "name": user.get_full_name() or user.get_username()}
            for user in assignee_choices
        ],
        "work_filter_values": filter_values,
        "response_filters": [
            {"title": spec.title, "choices": list(spec.choices(changelist))}
            for spec in changelist.filter_specs
        ],
        "search_params": [
            (key, value)
            for key, values in request.GET.lists()
            for value in values
            if key not in {"q", "p"}
        ],
        "clear_url": changelist.get_query_string(
            remove=[key for key in request.GET if key != "view"]
        ),
    }
