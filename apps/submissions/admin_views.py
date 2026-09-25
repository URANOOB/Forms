import hashlib
import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from apps.forms.conditions import FormSchema
from apps.forms.question_fields import FILE_TYPES

from .models import Submission, SubmissionActivity, SubmissionAnswer, SubmissionFile, SubmissionNote
from .panel import panel_context
from .presentation import render_response_details, response_sections
from .review import STATUS_HELP, AttentionForm, ReviewForm, record_review
from .runtime import PublicResponseForm
from .summary import load_summary_data, summary_for


def fingerprint(submission):
    data = {
        "status": submission.status,
        "review_revision": submission.review_revision,
        "answers": list(submission.answers.order_by("field_id").values("field_id", "value")),
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def page_context(model_admin, request, submission, title):
    load_summary_data([submission])
    sections = response_sections(submission)
    version_admin = model_admin.admin_site._registry.get(type(submission.form_version))
    return {
        **model_admin.admin_site.each_context(request),
        "opts": model_admin.model._meta,
        "original": submission,
        "title": title,
        "can_edit": model_admin.has_change_permission(request, submission),
        "can_review_action": model_admin.has_change_permission(request, submission)
        and (
            submission.status != Submission.Status.UNDER_REVIEW
            or not submission.assigned_to_id
            or submission.assigned_to_id == request.user.pk
            or request.user.is_superuser
        ),
        "can_delete": model_admin.has_delete_permission(request, submission),
        "details": render_response_details(sections, compact_heading=True),
        "response_sections": sections,
        "version_url": reverse("admin:forms_formversion_change", args=[submission.form_version_id])
        if version_admin and version_admin.has_view_permission(request, submission.form_version)
        else "",
        "response_form_title": submission.form_version.title or submission.form.name,
        "review_form": ReviewForm(submission),
        "reviews": submission.reviews.select_related("actor"),
        "status_help": STATUS_HELP[submission.status],
        "response_summary": summary_for(submission),
        "attention_form": AttentionForm(
            initial={
                "attention": submission.attention,
                "attention_note": submission.attention_note,
                "revision": submission.review_revision,
            }
        ),
    }


def response_detail(model_admin, request, object_id):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    submission = get_object_or_404(model_admin.get_queryset(request), pk=object_id)
    if not model_admin.has_view_permission(request, submission):
        raise PermissionDenied
    return render(
        request,
        "admin/submissions/detail.html",
        page_context(model_admin, request, submission, "Ver respuesta"),
    )


def response_panel(model_admin, request, object_id):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    submission = get_object_or_404(model_admin.get_queryset(request), pk=object_id)
    if not model_admin.has_view_permission(request, submission):
        raise PermissionDenied
    return render(
        request,
        "admin/submissions/responses/_detail_panel.html",
        {**panel_context(submission, request, model_admin), "panel_only": True},
    )


def response_note(model_admin, request, object_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    content = request.POST.get("content", "").strip()
    with transaction.atomic():
        submission = get_object_or_404(
            model_admin.get_queryset(request).select_for_update(of=("self",)), pk=object_id
        )
        if not model_admin.has_change_permission(request, submission):
            raise PermissionDenied
        if not content or len(content) > 2000:
            messages.error(request, "La nota debe tener entre 1 y 2.000 caracteres.")
        else:
            SubmissionNote.objects.create(
                submission=submission, author=request.user, content=content
            )
            SubmissionActivity.objects.create(
                submission=submission, actor=request.user, event_type="note_added"
            )
            model_admin.log_change(request, submission, "Añadió una nota interna.")
            messages.success(request, "Nota interna guardada.")
    fallback = (
        f"{reverse('admin:submissions_submission_changelist')}"
        f"?view=work&selected={submission.pk}#response-notes"
    )
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect(fallback)


def response_review(model_admin, request, object_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    wants_json = request.headers.get("Accept") == "application/json"
    with transaction.atomic():
        submission = get_object_or_404(
            model_admin.get_queryset(request).select_for_update(of=("self",)), pk=object_id
        )
        if not model_admin.has_change_permission(request, submission):
            raise PermissionDenied
        if (
            submission.status == Submission.Status.UNDER_REVIEW
            and submission.assigned_to_id
            and submission.assigned_to_id != request.user.pk
            and not request.user.is_superuser
        ):
            if wants_json:
                return JsonResponse(
                    {
                        "errors": {
                            "__all__": [
                                {
                                    "message": (
                                        "Esta respuesta ya está asignada a otra persona. "
                                        "Actualiza la página."
                                    )
                                }
                            ]
                        }
                    },
                    status=409,
                )
            raise PermissionDenied
        form = ReviewForm(submission, request.POST)
        valid = form.is_valid()
        conflict = form.cleaned_data.get("revision") != submission.review_revision
        if conflict:
            form.add_error(
                None, "El estado cambió desde que abriste esta página. Recarga para continuar."
            )
        if valid and not conflict:
            review = record_review(
                submission, form.cleaned_data["status"], form.cleaned_data["note"], request.user
            )
            model_admin.log_change(
                request,
                submission,
                f"Estado: {review.get_previous_status_display()} → {review.get_status_display()}.",
            )
            if wants_json:
                return JsonResponse({"status": submission.status})
            messages.success(request, f"Respuesta: {submission.get_status_display().lower()}.")
            return redirect("admin:submissions_submission_detail", object_id=submission.pk)
        status_code = 409 if conflict else 422
        if wants_json:
            return JsonResponse({"errors": form.errors.get_json_data()}, status=status_code)
        context = page_context(model_admin, request, submission, "Revisar respuesta")
        context["review_form"] = form
        return render(request, "admin/submissions/detail.html", context, status=status_code)


def response_attention(model_admin, request, object_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    with transaction.atomic():
        submission = get_object_or_404(
            model_admin.get_queryset(request).select_for_update(of=("self",)), pk=object_id
        )
        if not model_admin.has_change_permission(request, submission):
            raise PermissionDenied
        form = AttentionForm(request.POST)
        valid = form.is_valid()
        conflict = form.cleaned_data.get("revision") != submission.review_revision
        if conflict:
            form.add_error(None, "La respuesta cambió. Recarga antes de guardar la incidencia.")
        if valid and not conflict:
            attention = form.cleaned_data["attention"]
            note = form.cleaned_data["attention_note"] if attention else ""
            if (attention, note) != (submission.attention, submission.attention_note):
                submission.attention, submission.attention_note = attention, note
                submission.review_revision += 1
                submission.save(update_fields=["attention", "attention_note", "review_revision"])
                description = f"Señal de revisión: {submission.get_attention_display()}."
                submission.reviews.create(
                    previous_status=submission.status,
                    status=submission.status,
                    actor=request.user,
                    note=f"{description} {note}".strip(),
                )
                model_admin.log_change(request, submission, description)
            messages.success(request, "Señal de revisión actualizada.")
            return redirect("admin:submissions_submission_detail", object_id=submission.pk)
        context = page_context(model_admin, request, submission, "Revisar incidencia")
        context["attention_form"] = form
        return render(
            request, "admin/submissions/detail.html", context, status=409 if conflict else 422
        )


class EditResponseForm(PublicResponseForm):
    def __init__(self, schema, submission, *args, **kwargs):
        answers = list(submission.answers.prefetch_related("files").select_related("field"))
        initial = {}
        self.attachments = {}
        for answer in answers:
            name = f"answer_{answer.field.stable_key}"
            if answer.field.field_type in FILE_TYPES:
                self.attachments[name] = list(answer.files.all())
            elif answer.field.field_type == "SINGLE_CHOICE" and isinstance(answer.value, dict):
                initial[name] = answer.value.get("selected", "")
                initial[f"{name}__extra"] = answer.value.get("text", "")
            else:
                initial[name] = (
                    str(answer.value).lower() if isinstance(answer.value, bool) else answer.value
                )
        super().__init__(schema, *args, initial=initial, **kwargs)

    def clean(self):
        removed = set(self.data.getlist("remove_files"))
        for name, files in self.attachments.items():
            kept = [file for file in files if str(file.pk) not in removed]
            added = self.cleaned_data.get(name, [])
            if name not in self._errors:
                self.cleaned_data[name] = kept + added
                if len(kept) + len(added) > self.fields[name].max_files:
                    self.add_error(
                        name,
                        f"Se permiten hasta {self.fields[name].max_files} archivo(s), "
                        "contando los existentes.",
                    )
        return super().clean()

    def section_rows(self):
        sections = super().section_rows()
        removed = set(self.data.getlist("remove_files")) if self.is_bound else set()
        for section in sections:
            for row in section["rows"]:
                row["attachments"] = [
                    {
                        "id": str(file.pk),
                        "name": file.original_name,
                        "url": file.get_absolute_url(),
                        "remove": str(file.pk) in removed,
                    }
                    for file in self.attachments.get(f"answer_{row['field'].stable_key}", [])
                ]
        return sections


def response_edit(model_admin, request, object_id):
    if request.method not in {"GET", "POST"}:
        return HttpResponseNotAllowed(["GET", "POST"])
    stored = []
    removed = []
    try:
        with transaction.atomic():
            queryset = model_admin.get_queryset(request)
            if request.method == "POST":
                queryset = queryset.select_for_update(of=("self",))
            submission = get_object_or_404(queryset, pk=object_id)
            if not model_admin.has_change_permission(request, submission):
                raise PermissionDenied
            schema = FormSchema(submission.form_version)
            response_form = EditResponseForm(
                schema,
                submission,
                data=request.POST if request.method == "POST" else None,
                files=request.FILES if request.method == "POST" else None,
            )
            revision = fingerprint(submission)
            if request.method == "POST":
                valid = response_form.is_valid()
                if request.POST.get("revision") != revision:
                    response_form.add_error(
                        None,
                        "Otra persona modificó esta respuesta. Recarga la página antes de guardar.",
                    )
                elif valid:
                    # Preserve the original form version and submission date.
                    answers_changed = False
                    for field in schema.fields:
                        if schema.inputs[str(field.pk)] is None:
                            continue
                        value = response_form.answers.get(field.pk)
                        answer, _ = SubmissionAnswer.objects.get_or_create(
                            submission=submission, field=field
                        )
                        if field.field_type in FILE_TYPES:
                            keep = {
                                item.pk for item in value or [] if isinstance(item, SubmissionFile)
                            }
                            for attachment in answer.files.exclude(pk__in=keep):
                                removed.append(attachment.file)
                                attachment.delete()
                            metadata = []
                            for item in value or []:
                                if isinstance(item, SubmissionFile):
                                    attachment = item
                                else:
                                    attachment = SubmissionFile(
                                        answer=answer, original_name=item.name, size=item.size
                                    )
                                    attachment.file.save(item.name, item, save=False)
                                    stored.append(attachment.file)
                                    attachment.save()
                                metadata.append(
                                    {
                                        "id": str(attachment.pk),
                                        "name": attachment.original_name,
                                        "size": attachment.size,
                                    }
                                )
                            value = {"files": metadata}
                        answers_changed = answers_changed or answer.value != value
                        answer.value = value
                        answer.save(update_fields=["value"])
                    if answers_changed:
                        if submission.status in {
                            Submission.Status.VALIDATED,
                            Submission.Status.REJECTED,
                        }:
                            record_review(
                                submission,
                                Submission.Status.UNDER_REVIEW,
                                "Revisión reabierta por cambios en los datos de la respuesta.",
                                request.user,
                            )
                        else:
                            submission.review_revision += 1
                            submission.save(update_fields=["review_revision"])
                    model_admin.log_change(request, submission, "Editó los datos de la respuesta.")
                    for file in removed:
                        transaction.on_commit(
                            lambda file=file: file.delete(save=False), robust=True
                        )
                    messages.success(request, "Respuesta actualizada.")
                    return redirect("admin:submissions_submission_detail", object_id=submission.pk)
                if request.FILES:
                    response_form.add_error(
                        None, "Vuelve a seleccionar los archivos antes de guardar."
                    )
            return render(
                request,
                "public/form.html",
                {
                    "form": submission.form,
                    "form_title": f"Editar respuesta · {submission.form.name}",
                    "response_form": response_form,
                    "sections": response_form.section_rows(),
                    "schema": schema.browser_spec(),
                    "staff_edit": True,
                    "appearance": submission.form_version.appearance,
                    "back_url": reverse(
                        "admin:submissions_submission_detail", args=[submission.pk]
                    ),
                    "revision": request.POST.get("revision", revision),
                    "response_status": submission.get_status_display(),
                },
                status=422 if response_form.errors else 200,
            )
    except Exception:
        for file in stored:
            file.delete(save=False)
        raise


def response_delete(model_admin, request, object_id):
    if request.method not in {"GET", "POST"}:
        return HttpResponseNotAllowed(["GET", "POST"])
    with transaction.atomic():
        queryset = model_admin.get_queryset(request)
        if request.method == "POST":
            queryset = queryset.select_for_update(of=("self",))
        submission = get_object_or_404(queryset, pk=object_id)
        if not model_admin.has_delete_permission(request, submission):
            raise PermissionDenied
        if request.method == "POST" and request.POST.get("confirm_delete") == "yes":
            files = list(SubmissionFile.objects.filter(answer__submission=submission))
            model_admin.log_deletions(request, [submission])
            SubmissionFile.objects.filter(answer__submission=submission).delete()
            submission.answers.all().delete()
            submission.delete()
            for attachment in files:
                transaction.on_commit(
                    lambda file=attachment.file: file.delete(save=False), robust=True
                )
            messages.success(request, "Respuesta eliminada.")
            return redirect("admin:submissions_submission_changelist")
        return render(
            request,
            "admin/submissions/confirm_delete.html",
            page_context(model_admin, request, submission, "Eliminar respuesta"),
        )
