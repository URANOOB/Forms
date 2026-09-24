"""Operational dashboard: submission cohorts, current states and recorded events."""

from datetime import datetime, time, timedelta
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Count, Max, Q
from django.db.models.functions import TruncDate
from django.urls import reverse
from django.utils import timezone

from apps.submissions.models import Submission, SubmissionFile, SubmissionReview

from .infrastructure import infrastructure_info

PERIODS = {"today": ("Hoy", 1), "7d": ("7 días", 7), "30d": ("30 días", 30), "all": ("Todo", None)}
STATUS_LABELS = {
    "SUBMITTED": "Pendientes",
    "UNDER_REVIEW": "En revisión",
    "VALIDATED": "Validadas",
    "REJECTED": "Rechazadas",
}
EVENT_LABELS = {
    "SUBMITTED": "Respuesta recibida",
    "UNDER_REVIEW": "Respuesta en revisión",
    "VALIDATED": "Respuesta validada",
    "REJECTED": "Respuesta rechazada",
}


def midnight(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def within(queryset, field, start, end):
    queryset = queryset.filter(**{f"{field}__lte": end})
    return queryset.filter(**{f"{field}__gte": start}) if start else queryset


def response_url(start=None, end=None, **params):
    if start:
        params["submitted_at__gte"] = start.isoformat()
    if end:
        params["submitted_at__lte"] = end.isoformat()
    return reverse("admin:submissions_submission_changelist") + "?" + urlencode(params)


def relative_time(value, now):
    minutes = max(0, int((now - value).total_seconds() / 60))
    if minutes < 1:
        return "Hace un momento"
    if minutes < 60:
        return f"Hace {minutes} min"
    if minutes < 1440:
        return f"Hace {minutes // 60} h"
    return f"Hace {minutes // 1440} días"


def trend_context(responses, today, now, days):
    first = today - timedelta(days=days - 1)
    start = midnight(first)
    totals = dict(
        within(responses, "submitted_at", start, now)
        .order_by()
        .annotate(day=TruncDate("submitted_at"))
        .values("day")
        .annotate(total=Count("pk"))
        .values_list("day", "total")
    )
    points = [
        {
            "date": (first + timedelta(days=index)).isoformat(),
            "count": totals.get(first + timedelta(days=index), 0),
        }
        for index in range(days)
    ]
    current = sum(point["count"] for point in points)
    previous = responses.filter(
        submitted_at__gte=midnight(first - timedelta(days=days)), submitted_at__lt=start
    ).count()
    change = round((current - previous) / previous * 100, 1) if previous else None
    return {
        "points": points,
        "total": current,
        "previous": previous,
        "change": change,
        "label": "Hoy" if days == 1 else f"Últimos {days} días",
        "days": days,
    }


def recent_activity(start, now):
    events = []
    for item in within(
        Submission.objects.select_related("form"), "submitted_at", start, now
    ).order_by("-submitted_at", "-pk")[:12]:
        events.append(
            {
                "at": item.submitted_at,
                "label": "Nueva respuesta",
                "detail": item.form.name,
                "id": str(item.pk),
                "icon": "inbox",
                "url": reverse("admin:submissions_submission_detail", args=[item.pk]),
            }
        )
    for item in within(
        SubmissionReview.objects.select_related("submission__form"), "created_at", start, now
    ).order_by("-created_at", "-pk")[:12]:
        events.append(
            {
                "at": item.created_at,
                "label": "Señal de revisión actualizada"
                if item.previous_status == item.status
                else EVENT_LABELS[item.status],
                "detail": f"#{str(item.submission_id)[:8]} · {item.submission.form.name}",
                "id": str(item.pk),
                "icon": "fact_check",
                "url": reverse("admin:submissions_submission_detail", args=[item.submission_id])
                + "#response-history",
            }
        )
    for item in within(
        SubmissionFile.objects.select_related("answer__submission__form"), "uploaded_at", start, now
    ).order_by("-uploaded_at", "-pk")[:12]:
        events.append(
            {
                "at": item.uploaded_at,
                "label": "Documento recibido",
                "detail": item.original_name,
                "id": str(item.pk),
                "icon": "attach_file",
                "url": reverse(
                    "admin:submissions_submission_detail", args=[item.answer.submission_id]
                ),
            }
        )
    return sorted(events, key=lambda item: (item["at"], item["id"]), reverse=True)[:12]


def dashboard_callback(request, context):
    period = request.GET.get("period", "7d")
    if period not in PERIODS:
        period = "7d"
    days = PERIODS[period][1]
    now = timezone.now()
    today = timezone.localdate(now)
    start = midnight(today - timedelta(days=days - 1)) if days else None
    can_responses = request.user.has_perm("submissions.view_submission")
    context.update(
        {
            "dashboard_period": period,
            "dashboard_periods": [
                {"key": key, "label": value[0]} for key, value in PERIODS.items()
            ],
            "dashboard_updated": now,
            "dashboard_can_responses": can_responses,
            "dashboard_infrastructure": infrastructure_info() if request.user.is_superuser else [],
            "is_fullwidth": "1",
        }
    )
    if not can_responses:
        return context
    responses = Submission.objects.all()
    selected = within(responses, "submitted_at", start, now)
    counts = dict(
        selected.order_by()
        .values("status")
        .annotate(total=Count("pk"))
        .values_list("status", "total")
    )
    total = sum(counts.values())
    pending_today = selected.filter(status="SUBMITTED", submitted_at__gte=midnight(today)).count()
    reviewing_recently = (
        selected.filter(
            status="UNDER_REVIEW",
            reviews__status="UNDER_REVIEW",
            reviews__created_at__gte=midnight(today - timedelta(days=1)),
            reviews__created_at__lte=now,
        )
        .distinct()
        .count()
    )
    cards = [
        {
            "label": "Respuestas totales",
            "value": total,
            "note": "Recibidas en este período",
            "status": "total",
            "url": response_url(start, now),
        }
    ]
    for status, label in STATUS_LABELS.items():
        value = counts.get(status, 0)
        note = (
            f"{pending_today} nuevas hoy"
            if status == "SUBMITTED"
            else f"{reviewing_recently} desde ayer"
            if status == "UNDER_REVIEW"
            else f"{value / total * 100:.1f} % del total".replace(".", ",")
            if total
            else "Sin respuestas en el período"
        )
        cards.append(
            {
                "label": label,
                "value": value,
                "note": note,
                "status": status,
                "url": response_url(start, now, status__exact=status),
            }
        )
    activity = (
        selected.order_by()
        .values("form_id", "form__name", "form__deleted_at")
        .annotate(
            total=Count("pk"),
            pending=Count("pk", filter=Q(status="SUBMITTED")),
            reviewing=Count("pk", filter=Q(status="UNDER_REVIEW")),
            validated=Count("pk", filter=Q(status="VALIDATED")),
            rejected=Count("pk", filter=Q(status="REJECTED")),
            latest=Max("submitted_at"),
        )
        .order_by("-pending", "-reviewing", "-latest", "form_id")
    )
    page = Paginator(activity, 10).get_page(request.GET.get("page"))
    rows = [
        {
            **row,
            "url": response_url(start, now, form=row["form_id"]),
            "relative": relative_time(row["latest"], now),
        }
        for row in page
    ]
    context.update(
        {
            "dashboard_cards": cards,
            "dashboard_forms": rows,
            "dashboard_page": page,
            "dashboard_previous": f"?period={period}&page={page.previous_page_number()}"
            if page.has_previous()
            else "",
            "dashboard_next": f"?period={period}&page={page.next_page_number()}"
            if page.has_next()
            else "",
            "dashboard_trend": trend_context(responses, today, now, days or 30),
            "dashboard_events": recent_activity(start, now),
        }
    )
    return context
