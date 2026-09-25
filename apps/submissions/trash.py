"""Recoverable deletion; permanent purging is limited to administrators."""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render

from .file_cleanup import delete_pending_file
from .models import PendingFileDeletion, Submission, SubmissionActivity, SubmissionFile


def deleted_queryset():
    return Submission.all_objects.filter(deleted_at__isnull=False).select_related(
        "form", "deleted_by"
    )


def response_trash(model_admin, request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    if not model_admin.has_view_permission(request):
        raise PermissionDenied
    page = Paginator(deleted_queryset().order_by("-deleted_at", "-pk"), 25).get_page(
        request.GET.get("page")
    )
    for submission in page:
        submission.can_restore = model_admin.has_delete_permission(request, submission)
    return render(
        request,
        "admin/submissions/trash.html",
        {
            **model_admin.admin_site.each_context(request),
            "title": "Papelera de respuestas",
            "opts": model_admin.model._meta,
            "page": page,
        },
    )


def response_restore(model_admin, request, object_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    with transaction.atomic():
        submission = get_object_or_404(
            deleted_queryset().select_for_update(of=("self",)), pk=object_id
        )
        if not model_admin.has_delete_permission(request, submission):
            raise PermissionDenied
        submission.deleted_at = None
        submission.deleted_by = None
        submission.review_revision += 1
        submission.save(update_fields=["deleted_at", "deleted_by", "review_revision"])
        SubmissionActivity.objects.create(
            submission=submission, actor=request.user, event_type="restored"
        )
        model_admin.log_change(request, submission, "Restauró la respuesta de la papelera.")
    messages.success(request, "Respuesta restaurada con sus archivos e historial.")
    return redirect("admin:submissions_submission_trash")


def response_purge(model_admin, request, object_id):
    if request.method not in {"GET", "POST"}:
        return HttpResponseNotAllowed(["GET", "POST"])
    if not request.user.is_superuser:
        raise PermissionDenied
    with transaction.atomic():
        queryset = deleted_queryset()
        if request.method == "POST":
            queryset = queryset.select_for_update(of=("self",))
        submission = get_object_or_404(queryset, pk=object_id)
        if request.method == "POST" and request.POST.get("confirm_purge") == str(submission.pk):
            filenames = SubmissionFile.objects.filter(answer__submission=submission).values_list(
                "file", flat=True
            )
            for filename in filenames:
                task, _ = PendingFileDeletion.objects.get_or_create(name=filename)
                transaction.on_commit(lambda pk=task.pk: delete_pending_file(pk), robust=True)
            model_admin.log_deletions(request, [submission])
            SubmissionFile.objects.filter(answer__submission=submission).delete()
            submission.answers.all().delete()
            submission.delete()
            messages.success(
                request,
                "Datos de la respuesta eliminados definitivamente. "
                "La eliminación de archivos se reintentará "
                "si el almacenamiento no está disponible.",
            )
            return redirect("admin:submissions_submission_trash")
        return render(
            request,
            "admin/submissions/confirm_purge.html",
            {
                **model_admin.admin_site.each_context(request),
                "title": "Eliminar definitivamente",
                "opts": model_admin.model._meta,
                "original": submission,
            },
        )
