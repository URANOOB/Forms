from django.conf import settings

from .views import page_not_found


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
