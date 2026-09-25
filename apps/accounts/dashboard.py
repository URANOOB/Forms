"""Operational dashboard: submission cohorts, current states and recorded events."""

from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Count, Max, Q
from django.db.models.functions import TruncDate
from django.urls import reverse
from django.utils import timezone

from apps.submissions.models import Submission, SubmissionFile, SubmissionReview

from .infrastructure import infrastructure_info

PERIODS = {"today": ("Hoy", 1), "7d": ("7 días", 7), "30d": ("30 días", 30), "all": ("Todo", None)}
MAX_TREND_DAYS = 366
MIN_TREND_DATE = date(1900, 1, 1)
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


def trend_context(responses, today, now, days, custom_range=None):
    first, last = custom_range if custom_range else (today - timedelta(days=days - 1), today)
    days = (last - first).days + 1
    start = midnight(first)
    totals = dict(
        responses.filter(
            submitted_at__gte=start,
            submitted_at__lt=midnight(last + timedelta(days=1)),
            submitted_at__lte=now,
        )
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
    chart_points = points
    if days > 31:
        chart_points = []
        for index in range(0, days, 7):
            group = points[index : index + 7]
            chart_points.append(
                {
                    "date": group[0]["date"],
                    "count": sum(point["count"] for point in group),
                    "label": f"{date.fromisoformat(group[0]['date']):%d/%m}–{date.fromisoformat(group[-1]['date']):%d/%m}",
                }
            )
    active_days = [point for point in points if point["count"]]
    if not active_days:
        insight = "No se registraron respuestas durante este período."
    else:
        busiest = max(active_days, key=lambda point: point["count"])
        weekday = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")[
            datetime.fromisoformat(busiest["date"]).weekday()
        ]
        response_word = "respuesta" if busiest["count"] == 1 else "respuestas"
        if len(active_days) == 1:
            verb = "Se recibió" if busiest["count"] == 1 else "Se recibieron"
            insight = f"{verb} {busiest['count']} {response_word} el {weekday}."
        else:
            insight = f"El mayor volumen se registró el {weekday} con {busiest['count']} {response_word}."
    label = (
        f"{first:%d/%m/%Y} – {last:%d/%m/%Y}"
        if custom_range
        else "Hoy" if days == 1 else f"Últimos {days} días"
    )
    return {
        "points": points,
        "chart_points": chart_points,
        "chart_grouped": days > 31,
        "total": current,
        "previous": previous,
        "change": change,
        "label": label,
        "days": days,
        "insight": insight,
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


def daily_summary(current_counts, received_today, recent_form):
    pending = current_counts.get("SUBMITTED", 0)
    reviewing = current_counts.get("UNDER_REVIEW", 0)
    title = (
        f"Hoy tienes {pending} respuesta{'s' if pending != 1 else ''} pendiente{'s' if pending != 1 else ''} por revisar."
        if pending
        else "Todo está al día."
    )
    received_message = (
        f"Has recibido {received_today} respuesta{'s' if received_today != 1 else ''} nueva{'s' if received_today != 1 else ''} hoy."
        if received_today
        else "No has recibido nuevas respuestas hoy."
    )
    return {
        "title": title,
        "state": "attention" if pending else "clear",
        "received": received_message,
        "reviewing": f"Hay {reviewing} respuesta{'s' if reviewing != 1 else ''} en revisión." if reviewing else "",
        "recent_form": recent_form,
        "pending_url": response_url(status__exact="SUBMITTED", view="list"),
        "responses_url": reverse("admin:submissions_submission_changelist"),
    }


def selected_trend_range(params, today, default_days):
    default_start = today - timedelta(days=(default_days or 30) - 1)
    raw_start = (params.get("trend_start") or "").strip()[:32]
    raw_end = (params.get("trend_end") or "").strip()[:32]
    values = {
        "start": raw_start or default_start.isoformat(),
        "end": raw_end or today.isoformat(),
        "max": today.isoformat(),
        "min": MIN_TREND_DATE.isoformat(),
        "active": False,
        "error": "",
    }
    if not raw_start and not raw_end:
        return None, values
    if not raw_start or not raw_end:
        values["error"] = "Selecciona ambas fechas."
        return None, values
    try:
        first, last = date.fromisoformat(raw_start), date.fromisoformat(raw_end)
    except ValueError:
        values["error"] = "Ingresa fechas válidas."
        return None, values
    if first.isoformat() != raw_start or last.isoformat() != raw_end:
        values["error"] = "Ingresa fechas válidas."
    elif first < MIN_TREND_DATE:
        values["error"] = "Selecciona una fecha a partir del año 1900."
    elif first > last:
        values["error"] = "La fecha inicial debe ser anterior a la final."
    elif last > today:
        values["error"] = "La fecha final no puede ser posterior a hoy."
    elif (last - first).days + 1 > MAX_TREND_DAYS:
        values["error"] = f"Selecciona un máximo de {MAX_TREND_DAYS} días."
    if values["error"]:
        return None, values
    values["active"] = True
    return (first, last), values


def dashboard_callback(request, context):
    period = request.GET.get("period", "7d")
    if period not in PERIODS:
        period = "7d"
    days = PERIODS[period][1]
    now = timezone.now()
    today = timezone.localdate(now)
    start = midnight(today - timedelta(days=days - 1)) if days else None
    trend_range, trend_filter = selected_trend_range(request.GET, today, days)
    trend_params = (
        {"trend_start": trend_filter["start"], "trend_end": trend_filter["end"]}
        if trend_filter["active"]
        else {}
    )
    can_responses = request.user.has_perm("submissions.view_submission")
    context.update(
        {
            "dashboard_period": period,
            "dashboard_periods": [
                {
                    "key": key,
                    "label": value[0],
                    "url": "?" + urlencode({"period": key, **trend_params}),
                }
                for key, value in PERIODS.items()
            ],
            "dashboard_updated": now,
            "dashboard_can_responses": can_responses,
            "dashboard_can_forms": request.user.has_perm("forms.view_form"),
            "dashboard_trend_filter": trend_filter,
            "dashboard_trend_clear_url": "?" + urlencode({"period": period}) + "#trend-title",
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
    current_counts = dict(
        responses.order_by()
        .values("status")
        .annotate(total=Count("pk"))
        .values_list("status", "total")
    )
    received_today = responses.filter(submitted_at__gte=midnight(today), submitted_at__lte=now).count()
    recent_form = (
        responses.order_by("-submitted_at", "-pk")
        .values_list("form__name", flat=True)
        .first()
    )
    cards = [
        {
            "label": "Pendientes",
            "value": counts.get("SUBMITTED", 0),
            "note": "Por revisar en el período" if days else "Por revisar en total",
            "status": "SUBMITTED",
            "url": response_url(start, now, status__exact="SUBMITTED", view="list"),
        },
        {
            "label": "Recibidas hoy",
            "value": received_today,
            "note": "Nuevas respuestas",
            "status": "received_today",
            "url": response_url(midnight(today), now, view="list"),
        },
    ]
    for status, label in STATUS_LABELS.items():
        if status == "SUBMITTED":
            continue
        value = counts.get(status, 0)
        note = (
            "En proceso de revisión"
            if status == "UNDER_REVIEW"
            else f"{value / total * 100:.1f} % del total".replace(".", ",")
            if total
            else "0,0 % del total"
        )
        cards.append(
            {
                "label": label,
                "value": value,
                "note": note,
                "status": status,
                "url": response_url(start, now, status__exact=status, view="list"),
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
        .order_by("-pending", "-latest", "form_id")
    )
    page = Paginator(activity, 10).get_page(request.GET.get("page"))
    rows = [
        {
            **row,
            "url": response_url(start, now, form=row["form_id"]),
            "pending_url": response_url(start, now, form=row["form_id"], status__exact="SUBMITTED", view="list"),
            "relative": relative_time(row["latest"], now),
        }
        for row in page
    ]
    context.update(
        {
            "dashboard_cards": cards,
            "dashboard_summary": daily_summary(current_counts, received_today, recent_form),
            "dashboard_all_forms_url": reverse("admin:forms_form_changelist"),
            "dashboard_reports_url": reverse("admin:submissions_submission_reports"),
            "dashboard_forms": rows,
            "dashboard_page": page,
            "dashboard_previous": "?" + urlencode({"period": period, "page": page.previous_page_number(), **trend_params})
            if page.has_previous()
            else "",
            "dashboard_next": "?" + urlencode({"period": period, "page": page.next_page_number(), **trend_params})
            if page.has_next()
            else "",
            "dashboard_trend": trend_context(responses, today, now, days or 30, trend_range),
            "dashboard_events": recent_activity(start, now),
        }
    )
    return context
