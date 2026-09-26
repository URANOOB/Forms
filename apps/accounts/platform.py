"""Shared admin search and recent platform activity."""

from datetime import timedelta

from django.contrib import admin
from django.db.models import Exists, OuterRef, Q
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from apps.forms.models import FieldOption, Form, FormField
from apps.submissions.models import Submission

from .models import ActivityReceipt, ReportDownload, User


def shell_context(request):
    name = getattr(request.resolver_match, "url_name", "") or ""
    if name.startswith("notifications_emailnotification"):
        section = "Correos"
    elif name == "index":
        section = "Panel general"
    elif name.startswith("forms_form_builder") or name == "forms_form_add":
        section = "Editor de formularios"
    elif name.startswith("forms_form"):
        section = "Formularios"
    elif name == "submissions_submission_reports" or name.startswith(
        "submissions_submission_report_"
    ):
        section = "Reportes y descargas"
    elif name.startswith("submissions_submission"):
        section = "Respuestas recibidas"
    elif name.startswith("accounts_user"):
        section = "Usuarios y permisos"
    elif name == "platform_search":
        section = "Búsqueda"
    else:
        section = "Panel de control"
    return {"platform_section": section}


def search_matches(request, query, limit):
    terms = query[:120].split()[:5]
    results = []
    if not terms:
        return results

    if request.user.has_perm("forms.view_form"):
        forms = Form.objects.filter(deleted_at__isnull=True)
        for term in terms:
            fields = FormField.objects.filter(
                form_version__form_id=OuterRef("pk"), label__icontains=term
            )
            options = FieldOption.objects.filter(
                field__form_version__form_id=OuterRef("pk"), label__icontains=term
            )
            forms = forms.filter(
                Q(name__icontains=term)
                | Q(description__icontains=term)
                | Q(slug__icontains=term)
                | Exists(fields)
                | Exists(options)
            )
        for form in forms.order_by("-updated_at")[:limit]:
            results.append(
                {
                    "type": "Formulario",
                    "title": form.name,
                    "detail": form.get_status_display(),
                    "icon": "description",
                    "url": reverse("admin:forms_form_change", args=[form.pk]),
                }
            )

    if request.user.has_perm("submissions.view_submission"):
        model_admin = admin.site._registry[Submission]
        responses = model_admin.get_queryset(request).select_related("form")
        for term in terms:
            responses, _ = model_admin.get_search_results(request, responses, term)
        for response in responses.order_by("-submitted_at")[:limit]:
            results.append(
                {
                    "type": "Respuesta",
                    "title": response.form.name,
                    "detail": timezone.localtime(response.submitted_at).strftime("%d/%m/%Y %H:%M"),
                    "icon": "inbox",
                    "url": reverse("admin:submissions_submission_detail", args=[response.pk]),
                }
            )
        if "reporte" in query.casefold() or "excel" in query.casefold():
            results.append(
                {
                    "type": "Sección",
                    "title": "Reportes de respuestas",
                    "detail": "Excel y documentos ZIP",
                    "icon": "table_view",
                    "url": reverse("admin:submissions_submission_reports"),
                }
            )

    user_admin = admin.site._registry[User]
    if user_admin.has_view_permission(request):
        users = user_admin.get_queryset(request)
        for term in terms:
            users = users.filter(
                Q(username__icontains=term)
                | Q(first_name__icontains=term)
                | Q(last_name__icontains=term)
                | Q(email__icontains=term)
            )
        for user in users.order_by("username")[:limit]:
            results.append(
                {
                    "type": "Usuario",
                    "title": user.get_full_name() or user.username,
                    "detail": user.email,
                    "icon": "person",
                    "url": reverse("admin:accounts_user_change", args=[user.pk]),
                }
            )
    return results


def platform_search(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    query = request.GET.get("q", "").strip()[:120]
    results = search_matches(request, query, 6 if request.GET.get("format") == "json" else 25)
    if request.GET.get("format") == "json":
        return JsonResponse({"results": results})
    return render(
        request,
        "admin/platform_search.html",
        {
            **admin.site.each_context(request),
            "title": "Búsqueda",
            "query": query,
            "results": results,
        },
    )


def activity_feed(request):
    now = timezone.now()
    receipt = ActivityReceipt.objects.filter(user=request.user).first()
    cutoff = receipt.last_seen_at if receipt and receipt.last_seen_at else now - timedelta(days=7)
    items = []
    unread = 0

    if request.user.has_perm("forms.view_form"):
        forms = Form.objects.filter(deleted_at__isnull=True)
        unread += forms.filter(created_at__gt=cutoff).count()
        for form in forms.order_by("-created_at")[:12]:
            items.append(
                {
                    "at": form.created_at,
                    "title": "Nuevo formulario",
                    "detail": form.name,
                    "icon": "description",
                    "url": reverse("admin:forms_form_change", args=[form.pk]),
                }
            )

    if request.user.has_perm("submissions.view_submission"):
        responses = Submission.objects.select_related("form")
        unread += responses.filter(submitted_at__gt=cutoff).count()
        for response in responses.order_by("-submitted_at")[:12]:
            items.append(
                {
                    "at": response.submitted_at,
                    "title": "Respuesta recibida",
                    "detail": response.form.name,
                    "icon": "inbox",
                    "url": reverse("admin:submissions_submission_detail", args=[response.pk]),
                }
            )

        downloads = ReportDownload.objects.select_related("actor")
        unread += downloads.filter(created_at__gt=cutoff).count()
        for download in downloads.order_by("-created_at")[:12]:
            items.append(
                {
                    "at": download.created_at,
                    "title": "Reporte descargado",
                    "detail": f"{download.get_kind_display()} · {download.actor.get_username()}",
                    "icon": "download",
                    "url": reverse("admin:submissions_submission_reports"),
                }
            )

    items.sort(key=lambda item: item["at"], reverse=True)
    return {
        "unread": min(unread, 99),
        "items": [
            {
                **item,
                "at": item["at"].isoformat(),
                "time": timezone.localtime(item["at"]).strftime("%d/%m/%Y %H:%M"),
                "unread": item["at"] > cutoff,
            }
            for item in items[:12]
        ],
    }


def platform_activity(request):
    if request.method == "GET":
        return JsonResponse(activity_feed(request))
    if request.method == "POST":
        ActivityReceipt.objects.update_or_create(
            user=request.user, defaults={"last_seen_at": timezone.now()}
        )
        return JsonResponse({"unread": 0})
    return HttpResponseNotAllowed(["GET", "POST"])
