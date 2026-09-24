import csv
import uuid

from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .summary import answer_text, load_summary_data, summary_for


def csv_value(value):
    value = str(value)
    # Keep spreadsheet applications from treating received text as formulas.
    return (
        "'" + value
        if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r"))
        else value
    )


def export_responses(model_admin, request, submissions):
    if not model_admin.has_view_permission(request):
        raise PermissionDenied
    for submission in submissions:
        if not model_admin.has_view_permission(request, submission):
            raise PermissionDenied
    load_summary_data(submissions)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="respuestas.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(
        [
            "Respuesta",
            "Respondiente",
            "Formulario",
            "Versión",
            "Recibida",
            "Estado",
            "Señal",
            "Campo",
            "Valor",
        ]
    )
    for submission in submissions:
        base = [
            str(submission.pk),
            summary_for(submission)["title"],
            submission.form.name,
            submission.form_version.version_number,
            timezone.localtime(submission.submitted_at).isoformat(),
            submission.get_status_display(),
            submission.get_attention_display(),
        ]
        answers = submission.summary_answers
        for answer in answers:
            writer.writerow(
                [csv_value(v) for v in [*base, answer.field.label, answer_text(answer)]]
            )
        if not answers:
            writer.writerow([csv_value(v) for v in [*base, "", ""]])
    return response


def response_download(model_admin, request, object_id):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    submission = get_object_or_404(
        model_admin.get_queryset(request).select_related("form", "form_version"), pk=object_id
    )
    return export_responses(model_admin, request, [submission])


def responses_download(model_admin, request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if not model_admin.has_view_permission(request):
        raise PermissionDenied
    ids = request.POST.getlist("selected")
    if not 1 <= len(ids) <= 100:
        return HttpResponseBadRequest("Selecciona de 1 a 100 respuestas.")
    try:
        ids = {uuid.UUID(value) for value in ids}
    except (ValueError, TypeError):
        return HttpResponseBadRequest("Selección de respuestas inválida.")
    submissions = list(
        model_admin.get_queryset(request).filter(pk__in=ids).select_related("form", "form_version")
    )
    if len(submissions) != len(ids):
        return HttpResponseBadRequest("Alguna respuesta ya no está disponible. Actualiza la tabla.")
    return export_responses(model_admin, request, submissions)
