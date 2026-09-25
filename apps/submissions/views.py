from uuid import UUID

from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_http_methods

from apps.forms.conditions import FormSchema
from apps.forms.models import Form, FormVersion
from apps.forms.welcome import welcome_data

from .models import SubmissionActivity, SubmissionFile
from .runtime import PublicResponseForm, new_token, read_token, save_response


@sensitive_post_parameters()
@never_cache
@require_http_methods(["GET", "POST"])
def public_form(request, form_id=None, workspace_slug=None, slug=None):
    lookup = {"pk": form_id} if form_id else {"workspace__slug": workspace_slug, "slug": slug}
    form = get_object_or_404(
        Form.objects.select_related("workspace", "active_version"),
        **lookup,
        status__in=[Form.Status.PUBLISHED, Form.Status.PAUSED],
        deleted_at__isnull=True,
        active_version__status="PUBLISHED",
    )
    if form.status == Form.Status.PAUSED:
        return render(
            request,
            "public/closed.html",
            {
                "form_title": form.active_version.title or form.name,
                "appearance": form.active_version.appearance,
            },
            status=409 if request.method == "POST" else 200,
        )
    schema = FormSchema(form.active_version)
    response_form = PublicResponseForm(
        schema,
        data=request.POST if request.method == "POST" else None,
        files=request.FILES if request.method == "POST" else None,
    )
    token = new_token(form)
    status = 200
    if request.method == "POST":
        valid = response_form.is_valid()
        try:
            token = request.POST.get("submission_token", "")
            nonce = read_token(token, form)
            if valid:
                submission = save_response(
                    form.pk, form.active_version_id, nonce, response_form.answers
                )
                query = urlencode({"version": str(submission.form_version_id)})
                return redirect(f"{reverse('submission_thanks')}?{query}")
            status = 422
            if request.FILES:
                response_form.add_error(
                    None, "Vuelve a seleccionar los archivos antes de reenviar."
                )
        except ValidationError as error:
            response_form.add_error(None, error)
            token = new_token(form)
            status = 409
    return render(
        request,
        "public/form.html",
        {
            "form": form,
            "form_title": form.active_version.title or form.name,
            "form_description": form.active_version.description
            if form.active_version.title
            else form.description,
            "response_form": response_form,
            "sections": response_form.section_rows(),
            "schema": schema.browser_spec(),
            "token": token,
            "welcome": welcome_data(form.active_version),
            "appearance": form.active_version.appearance,
        },
        status=status,
    )


@never_cache
@require_GET
def thanks(request):
    appearance = {}
    try:
        version_id = UUID(request.GET.get("version", ""))
    except (ValueError, TypeError, AttributeError):
        version_id = None
    if version_id:
        # Use the submitted version even if a newer theme is published afterwards.
        # This lookup exposes only appearance, never a response or a draft's data.
        appearance = (
            FormVersion.objects.filter(
                pk=version_id,
                published_at__isnull=False,
                form__deleted_at__isnull=True,
            )
            .values_list("appearance", flat=True)
            .first()
            or {}
        )
    return render(request, "public/thanks.html", {"appearance": appearance})


@never_cache
@staff_member_required
@require_GET
def response_file(request, file_id):
    if not request.user.has_perm("submissions.view_submission"):
        raise PermissionDenied
    attachment = get_object_or_404(SubmissionFile, pk=file_id)
    try:
        stream = attachment.file.open("rb")
    except FileNotFoundError:
        raise Http404 from None
    SubmissionActivity.objects.create(
        submission_id=attachment.answer.submission_id,
        actor=request.user,
        event_type="document_viewed" if request.GET.get("preview") == "1" else "document_downloaded",
        description=attachment.original_name,
    )
    response = FileResponse(
        stream,
        as_attachment=True,
        filename=attachment.original_name,
        content_type="application/octet-stream",
    )
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "sandbox"
    return response
