"""Server-enforced idle expiry, independent of notification polling."""

from datetime import UTC, datetime
from math import ceil
from time import time

from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.http import JsonResponse
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

ACTIVITY_KEY = "_idle_last_activity"


def touch_session(request, now):
    request.session[ACTIVITY_KEY] = now
    # Absolute expiry prevents unrelated session writes from extending the deadline.
    request.session.set_expiry(
        datetime.fromtimestamp(now + settings.SESSION_IDLE_TIMEOUT_SECONDS, UTC)
    )


@receiver(user_logged_in, dispatch_uid="accounts.start_idle_session")
def start_idle_session(sender, request, **kwargs):
    touch_session(request, time())


class IdleSessionMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated:
            return None
        now = time()
        last = request.session.get(ACTIVITY_KEY)
        if last is not None and now - last >= settings.SESSION_IDLE_TIMEOUT_SECONDS:
            logout(request)
            return None  # Protected views now see an anonymous user; public forms still work.
        # Existing sessions receive a deadline on their first request after rollout.
        if last is None:
            touch_session(request, now)
        name = request.resolver_match.url_name
        panel = request.path.startswith(reverse("admin:index"))
        background = name == "session_activity" or (
            name == "platform_activity" and request.method == "GET"
        )
        navigation = request.headers.get("Sec-Fetch-Mode", "navigate") == "navigate"
        if panel and not background and (request.method == "POST" or navigation):
            touch_session(request, now)
        return None


@never_cache
@ensure_csrf_cookie
@require_http_methods(["GET", "POST"])
def session_activity(request):
    if not request.user.is_authenticated or not request.user.is_active or not request.user.is_staff:
        return JsonResponse({"expired": True}, status=401)
    now = time()
    if request.method == "POST":
        touch_session(request, now)
    remaining = request.session[ACTIVITY_KEY] + settings.SESSION_IDLE_TIMEOUT_SECONDS - now
    return JsonResponse({"remaining_seconds": max(0, ceil(remaining))})
