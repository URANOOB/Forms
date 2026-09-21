import hashlib
import json

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.forms.conditions import FormSchema
from apps.forms.question_fields import FILE_TYPES

from .models import Submission, SubmissionAnswer, SubmissionFile
from .runtime import PublicResponseForm


def fingerprint(submission):
    data = {"status": submission.status, "answers": list(
        submission.answers.order_by("field_id").values("field_id", "value")
    )}
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def page_context(model_admin, request, submission, title):
    return {
        **model_admin.admin_site.each_context(request),
        "opts": model_admin.model._meta, "original": submission, "title": title,
        "can_edit": model_admin.has_change_permission(request, submission),
        "can_delete": model_admin.has_delete_permission(request, submission),
        "details": model_admin.answer_details(submission),
    }


def response_detail(model_admin, request, object_id):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    submission = get_object_or_404(model_admin.get_queryset(request), pk=object_id)
    if not model_admin.has_view_permission(request, submission):
        raise PermissionDenied
    return render(request, "admin/submissions/detail.html", page_context(
        model_admin, request, submission, "Ver respuesta"
    ))


class EditResponseForm(PublicResponseForm):
    response_status = forms.ChoiceField(label="Estado", choices=Submission.Status.choices)

    def __init__(self, schema, submission, *args, **kwargs):
        answers = list(submission.answers.prefetch_related("files").select_related("field"))
        initial = {"response_status": submission.status}
        self.attachments = {}
        for answer in answers:
            name = f"answer_{answer.field.stable_key}"
            if answer.field.field_type in FILE_TYPES:
                self.attachments[name] = list(answer.files.all())
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
                    self.add_error(name, f"Se permiten hasta {self.fields[name].max_files} archivo(s), contando los existentes.")
        return super().clean()

    def section_rows(self):
        sections = super().section_rows()
        removed = set(self.data.getlist("remove_files")) if self.is_bound else set()
        for section in sections:
            for row in section["rows"]:
                row["attachments"] = [
                    {"id": str(file.pk), "name": file.original_name,
                     "url": file.get_absolute_url(), "remove": str(file.pk) in removed}
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
                schema, submission, data=request.POST if request.method == "POST" else None,
                files=request.FILES if request.method == "POST" else None,
            )
            revision = fingerprint(submission)
            if request.method == "POST":
                valid = response_form.is_valid()
                if request.POST.get("revision") != revision:
                    response_form.add_error(None, "Otra persona modificó esta respuesta. Recarga la página antes de guardar.")
                elif valid:
                    # Preserve the original form version and submission date.
                    for field in schema.fields:
                        if schema.inputs[str(field.pk)] is None:
                            continue
                        value = response_form.answers.get(field.pk)
                        answer, _ = SubmissionAnswer.objects.get_or_create(submission=submission, field=field)
                        if field.field_type in FILE_TYPES:
                            keep = {item.pk for item in value or [] if isinstance(item, SubmissionFile)}
                            for attachment in answer.files.exclude(pk__in=keep):
                                removed.append(attachment.file)
                                attachment.delete()
                            metadata = []
                            for item in value or []:
                                if isinstance(item, SubmissionFile):
                                    attachment = item
                                else:
                                    attachment = SubmissionFile(answer=answer, original_name=item.name, size=item.size)
                                    attachment.file.save(item.name, item, save=False)
                                    stored.append(attachment.file)
                                    attachment.save()
                                metadata.append({"id": str(attachment.pk), "name": attachment.original_name, "size": attachment.size})
                            value = {"files": metadata}
                        answer.value = value
                        answer.save(update_fields=["value"])
                    submission.status = response_form.cleaned_data["response_status"]
                    submission.save(update_fields=["status"])
                    model_admin.log_change(request, submission, "Editó los datos de la respuesta.")
                    for file in removed:
                        transaction.on_commit(lambda file=file: file.delete(save=False), robust=True)
                    messages.success(request, "Respuesta actualizada.")
                    return redirect("admin:submissions_submission_detail", object_id=submission.pk)
                if request.FILES:
                    response_form.add_error(None, "Vuelve a seleccionar los archivos antes de guardar.")
            return render(request, "public/form.html", {
                "form": submission.form, "form_title": f"Editar respuesta · {submission.form.name}",
                "response_form": response_form, "sections": response_form.section_rows(),
                "schema": schema.browser_spec(), "staff_edit": True,
                "appearance": submission.form_version.appearance,
                "back_url": reverse("admin:submissions_submission_detail", args=[submission.pk]),
                "revision": request.POST.get("revision", revision),
            }, status=422 if response_form.errors else 200)
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
                transaction.on_commit(lambda file=attachment.file: file.delete(save=False), robust=True)
            messages.success(request, "Respuesta eliminada.")
            return redirect("admin:submissions_submission_changelist")
        return render(request, "admin/submissions/confirm_delete.html", page_context(
            model_admin, request, submission, "Eliminar respuesta"
        ))
