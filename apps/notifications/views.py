import uuid
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import EmailNotification as Email
from .services import can_retry, send_notification


class Filters(forms.Form):
    q = forms.CharField(
        required=False,
        max_length=150,
        label="Buscar",
        widget=forms.TextInput(attrs={"placeholder": "Destinatario, formulario, evento…"}),
    )
    status = forms.ChoiceField(
        required=False, label="Estado", choices=[("", "Todos los estados"), *Email.Status.choices]
    )
    event = forms.ChoiceField(
        required=False, label="Evento", choices=[("", "Todos los eventos"), *Email.Event.choices]
    )
    form = forms.UUIDField(required=False, label="Formulario", widget=forms.Select)
    kind = forms.ChoiceField(
        required=False,
        label="Destinatario",
        choices=[("", "Todos los destinatarios"), *Email.Recipient.choices],
    )
    period = forms.ChoiceField(
        required=False,
        label="Periodo",
        choices=[
            ("30", "Últimos 30 días"),
            ("7", "Últimos 7 días"),
            ("1", "Hoy"),
            ("all", "Todo el periodo"),
        ],
    )
    size = forms.ChoiceField(
        required=False,
        label="Por página",
        choices=[("10", "10 por página"), ("25", "25 por página"), ("50", "50 por página")],
    )


def emails(model_admin, request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    if not model_admin.has_view_permission(request):
        raise PermissionDenied
    params = request.GET.copy()
    params.setdefault("period", "30")
    params.setdefault("size", "10")
    filters = Filters(params)
    filters.fields["form"].widget.choices = [
        ("", "Todos los formularios"),
        *Email.objects.exclude(form_id=None)
        .order_by("form_name")
        .values_list("form_id", "form_name")
        .distinct(),
    ]
    queryset = Email.objects.select_related("submission").all()
    valid = filters.is_valid()
    if not valid:
        queryset = queryset.none()
    else:
        data = filters.cleaned_data
        for key, column in (
            ("status", "status"),
            ("event", "event_type"),
            ("form", "form_id"),
            ("kind", "recipient_kind"),
        ):
            if data[key]:
                queryset = queryset.filter(**{column: data[key]})
        if data["q"]:
            query = data["q"]
            events = [
                value
                for value, label in Email.Event.choices
                if query.casefold() in label.casefold()
            ]
            queryset = queryset.filter(
                Q(recipient_email__icontains=query)
                | Q(form_name__icontains=query)
                | Q(event_type__in=events)
            )
        if data["period"] != "all":
            start = timezone.localtime().replace(
                hour=0, minute=0, second=0, microsecond=0
            ) - timedelta(days=int(data["period"] or 30) - 1)
            queryset = queryset.filter(created_at__gte=start)
    today = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    metrics = queryset.aggregate(
        sent=Count("pk", filter=Q(sent_at__gte=today)),
        delivered=Count("pk", filter=Q(status="DELIVERED")),
        pending=Count("pk", filter=Q(status__in=["PENDING", "SENDING", "DELIVERY_DELAYED"])),
        failed=Count("pk", filter=Q(status__in=["FAILED", "BOUNCED", "COMPLAINED", "SUPPRESSED"])),
    )
    page = Paginator(
        queryset, int(filters.cleaned_data.get("size") or 10) if valid else 10
    ).get_page(request.GET.get("page"))
    selected = None
    try:
        selected_id = uuid.UUID(request.GET.get("selected", ""))
    except ValueError:
        selected_id = None
    if selected_id:
        selected = queryset.filter(pk=selected_id).first()
    query = params.copy()
    query.pop("selected", None)
    close_url = "?" + query.urlencode()
    for item in page:
        selected_params = query.copy()
        selected_params["selected"] = str(item.pk)
        item.select_url = "?" + selected_params.urlencode() + "#email-detail"
    timeline = []
    if selected:
        timeline.append({"at": selected.created_at, "title": "Notificación creada", "detail": ""})
        attempts = list(selected.send_attempts.all()[:100])
        sent_ids = {attempt.provider_message_id for attempt in attempts if attempt.status == "SENT"}
        for attempt in attempts:
            timeline.append(
                {
                    "at": attempt.started_at,
                    "title": "Intento de envío",
                    "detail": f"Intento {attempt.number}",
                }
            )
            if attempt.finished_at:
                timeline.append(
                    {
                        "at": attempt.finished_at,
                        "title": "Correo enviado"
                        if attempt.status == "SENT"
                        else "Error de Resend",
                        "detail": attempt.error,
                    }
                )
        for event in selected.delivery_events.order_by("-occurred_at", "-pk")[:100]:
            if event.event_type == "email.sent" and event.provider_message_id in sent_ids:
                continue
            timeline.append(
                {
                    "at": event.occurred_at,
                    "title": {
                        "email.sent": "Correo enviado",
                        "email.delivered": "Correo entregado",
                        "email.delivery_delayed": "Entrega demorada",
                        "email.bounced": "Correo rebotado",
                        "email.complained": "Marcado como spam",
                        "email.failed": "Entrega fallida",
                        "email.suppressed": "Envío suprimido",
                    }.get(event.event_type, event.event_type),
                    "detail": "",
                }
            )
        timeline.sort(key=lambda event: event["at"])
    query.pop("page", None)
    return render(
        request,
        "admin/notifications/emails.html",
        {
            **model_admin.admin_site.each_context(request),
            "title": "Correos",
            "opts": Email._meta,
            "filters": filters,
            "metrics": metrics,
            "page": page,
            "selected": selected,
            "timeline": timeline,
            "close_url": close_url,
            "page_query": query.urlencode(),
            "can_retry": selected and request.user.is_superuser and can_retry(selected),
        },
        status=200 if valid else 400,
    )


@require_POST
def retry_email(request, notification_id):
    if not request.user.is_superuser:
        raise PermissionDenied
    notification = get_object_or_404(Email, pk=notification_id)
    if not can_retry(notification):
        messages.error(request, "Este correo no admite un reintento automático seguro.")
    elif send_notification(notification.pk, retry=True):
        messages.success(request, "Correo enviado a Resend.")
    else:
        messages.warning(request, "El envío no se completó. Consulta su estado y último error.")
    return redirect(
        reverse("admin:notifications_emailnotification_changelist")
        + f"?period=all&selected={notification.pk}"
    )
