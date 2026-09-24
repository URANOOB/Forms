from django.db.models import Count
from unfold.views import ChangeList

from .models import Submission
from .review import TRANSITIONS
from .summary import load_summary_data, summary_for

BOARD_LIMIT = 12


class ResponseChangeList(ChangeList):
    def get_filters_params(self, params=None):
        filters = super().get_filters_params(params)
        filters.pop("view", None)
        return filters


def board_context(request, changelist, model_admin):
    layout = "list" if request.GET.get("view") == "list" else "board"
    columns = []
    rows = []
    if layout == "board":
        counts = dict(
            changelist.queryset.order_by()
            .values("status")
            .annotate(total=Count("pk"))
            .values_list("status", "total")
        )
        for status, label in Submission.Status.choices:
            cards = list(changelist.queryset.filter(status=status)[:BOARD_LIMIT])
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
                        {"view": "list", "status__exact": status}, ["p", "status"]
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
            "can_review": model_admin.has_change_permission(request, submission),
            "transitions": TRANSITIONS[submission.status],
        }

    if layout == "board":
        for column in columns:
            column["cards"] = [card(item) for item in column["cards"]]
    else:
        rows = [card(item) for item in submissions]
    return {
        "response_layout": layout,
        "response_columns": columns,
        "board_url": changelist.get_query_string({"view": "board"}, ["p"]),
        "list_url": changelist.get_query_string({"view": "list"}, ["p"]),
        "review_transitions": TRANSITIONS,
        "response_rows": rows,
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
