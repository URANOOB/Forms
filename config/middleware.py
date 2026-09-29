from django.conf import settings
from django.core.exceptions import RequestDataTooBig, TooManyFieldsSent, TooManyFilesSent
from django.http import HttpResponseBadRequest, JsonResponse
from django.utils.deprecation import MiddlewareMixin

from .views import page_not_found


class PublicUploadLimitsMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.method != "POST" or request.resolver_match.url_name not in {
            "public_form",
            "legacy_public_form",
        }:
            return None
        try:
            # Parse before CSRF middleware accesses POST so the error is recoverable.
            request.POST
            request.FILES
        except (RequestDataTooBig, TooManyFieldsSent, TooManyFilesSent):
            message = (
                "El envío supera el límite de datos o archivos. Reduce las selecciones "
                "o los adjuntos y vuelve a intentar; tus datos siguen en esta página."
            )
            if request.headers.get("Accept") == "application/json":
                response = JsonResponse({"message": message}, status=400)
            else:
                response = HttpResponseBadRequest(message, content_type="text/plain; charset=utf-8")
            response["Cache-Control"] = "no-store"
            return response
        return None


class DevelopmentNotFoundMiddleware:
    """Show the designed HTML 404 locally without disabling other debug pages."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            settings.DEBUG
            and response.status_code == 404
            and response.get("Content-Type", "").startswith("text/html")
            and not response.streaming
        ):
            return page_not_found(request)
        return response
