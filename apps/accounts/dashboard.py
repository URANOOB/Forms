import shutil
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage, default_storage
from django.db.models import Count, Q, Sum
from django.template.defaultfilters import filesizeformat
from django.utils import timezone

from apps.forms.models import Form, FormImage
from apps.submissions.models import Submission, SubmissionFile

from .models import User
from .roles import visible_users


def dashboard_callback(request, context):
    can_forms = request.user.has_perm("forms.view_form")
    can_responses = request.user.has_perm("submissions.view_submission")
    can_users = request.user.is_superuser
    forms = (
        Form.objects.filter(deleted_at__isnull=True).aggregate(
            total=Count("id"),
            published=Count("id", filter=Q(status="PUBLISHED")),
        )
        if can_forms
        else {}
    )
    responses = (
        Submission.objects.aggregate(
            total=Count("id"),
            recent=Count("id", filter=Q(submitted_at__gte=timezone.now() - timedelta(days=7))),
            pending=Count("id", filter=Q(status__in=["SUBMITTED", "UNDER_REVIEW"])),
        )
        if can_responses
        else {}
    )
    users = (
        visible_users(User.objects.all()).aggregate(
            total=Count("id"),
            active=Count("id", filter=Q(is_active=True)),
        )
        if can_users
        else {}
    )
    size = 0
    complete = True
    if can_forms:
        for asset in FormImage.objects.all().iterator():
            try:
                size += asset.file.size
            except (OSError, NotImplementedError):
                complete = False
    if can_responses:
        size += SubmissionFile.objects.aggregate(total=Sum("size"))["total"] or 0
    used = filesizeformat(size) if complete else "No disponible"
    storage_value = used if can_forms else "—"
    storage_title = "Almacenamiento utilizado"
    storage_note = "Imágenes y adjuntos recibidos · sin cuota asignada"
    storage_percent = None
    if request.user.is_superuser and isinstance(default_storage, FileSystemStorage):
        try:
            location = Path(default_storage.location)
            disk = shutil.disk_usage(location if location.exists() else settings.BASE_DIR)
            storage_value = filesizeformat(disk.free)
            storage_title = "Almacenamiento disponible"
            storage_note = f"Disco del servidor · imágenes y adjuntos: {used}"
            storage_percent = (
                round((disk.total - disk.free) / disk.total * 100) if disk.total else 0
            )
        except OSError:
            pass
    context.update(
        {
            "dashboard_cards": [
                {
                    "label": "Respuestas recibidas",
                    "value": responses.get("total", "—"),
                    "note": f"{responses.get('recent', 0)} en los últimos 7 días"
                    if can_responses
                    else "Sin permiso para consultar respuestas",
                    "icon": "inbox",
                    "color": "purple",
                },
                {
                    "label": "Formularios publicados",
                    "value": forms.get("published", "—"),
                    "note": f"De {forms.get('total', 0)} formularios en total"
                    if can_forms
                    else "Sin permiso para consultar formularios",
                    "icon": "description",
                    "color": "blue",
                },
                {
                    "label": "Usuarios registrados",
                    "value": users.get("total", "—"),
                    "note": f"{users.get('active', 0)} cuentas activas en la plataforma"
                    if can_users
                    else "Solo visible para administradores de usuarios",
                    "icon": "group",
                    "color": "green",
                },
                {
                    "label": storage_title,
                    "value": storage_value,
                    "note": storage_note,
                    "icon": "cloud",
                    "color": "orange",
                    "percent": storage_percent,
                },
            ],
            "dashboard_forms": list(
                Form.objects.filter(deleted_at__isnull=True)
                .annotate(response_count=Count("submissions"))
                .order_by("-updated_at")[:6]
            )
            if can_forms and can_responses
            else [],
            "dashboard_pending": responses.get("pending"),
            "dashboard_updated": timezone.now(),
        }
    )
    return context
