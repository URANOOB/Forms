"""Atomic, shared throttles. Never persist raw addresses or account names."""

import math
import unicodedata
from ipaddress import ip_address, ip_network

from django.conf import settings
from django.db import DatabaseError, connection
from django.http import HttpResponse
from django.utils.crypto import salted_hmac
from django.utils.deprecation import MiddlewareMixin


def client_identity(request):
    # Only platform-owned settings select a trusted header; arbitrary XFF is ignored.
    header = settings.RATE_LIMIT_IP_HEADER
    raw = request.META.get(header if header else "REMOTE_ADDR", "")
    try:
        address = ip_address(raw.strip())
        if address.version == 6 and address.ipv4_mapped:
            address = address.ipv4_mapped
        # IPv6 privacy addresses must not provide an unlimited supply of identities.
        return (
            str(ip_network(f"{address}/64", strict=False)) if address.version == 6 else str(address)
        )
    except ValueError:
        return "unknown"  # Missing/malformed metadata shares a bucket; never bypass.


def consume(scope, identity):
    limit, seconds = settings.RATE_LIMITS[scope]
    key = salted_hmac("forms-rate-limit", f"{scope}:{identity}", algorithm="sha256").hexdigest()
    # One row per scope/identity. PostgreSQL serializes concurrent conflicts, including
    # the first request. Denied requests do not extend the fixed cooldown.
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO accounts_ratelimitbucket AS bucket (key, count, expires_at)
            VALUES (%s, 1, statement_timestamp() + %s * interval '1 second')
            ON CONFLICT (key) DO UPDATE SET
                count = CASE WHEN bucket.expires_at <= statement_timestamp() THEN 1
                             ELSE LEAST(bucket.count + 1, %s) END,
                expires_at = CASE WHEN bucket.expires_at <= statement_timestamp()
                    THEN EXCLUDED.expires_at ELSE bucket.expires_at END
            RETURNING count, EXTRACT(EPOCH FROM expires_at - statement_timestamp())
            """,
            [key, seconds, limit + 1],
        )
        count, remaining = cursor.fetchone()
    return max(1, math.ceil(remaining)) if count > limit else 0


def rejection(seconds, unavailable=False):
    message = (
        "No podemos procesar la solicitud en este momento."
        if unavailable
        else "Has realizado demasiados intentos."
    )
    response = HttpResponse(
        f"{message} Espera {seconds} segundos y vuelve a intentarlo. "
        "Si estabas completando un formulario, vuelve atrás para conservar tus datos.",
        status=503 if unavailable else 429,
        content_type="text/plain; charset=utf-8",
    )
    response["Retry-After"] = str(seconds)
    response["Cache-Control"] = "private, no-store"
    return response


class RateLimitMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        match = request.resolver_match
        public = match.url_name in {"public_form", "legacy_public_form"}
        login = match.url_name == "login" and "admin" in match.app_names
        if not public and not (login and request.method == "POST"):
            return None
        identity = client_identity(request)
        scopes = (
            (("public_post", "public_hour") if request.method == "POST" else ("public_read",))
            if public
            else ("login_ip",)
        )
        try:
            for scope in scopes:
                retry = consume(scope, identity)
                if retry:
                    return rejection(retry)
            if login:
                username = (
                    unicodedata.normalize("NFKC", request.POST.get("username", ""))
                    .strip()
                    .casefold()
                )
                retry = consume("login_account", username)
                if retry:
                    return rejection(retry)
        except DatabaseError:
            # If the shared limiter is unavailable, do not allow unthrottled writes.
            return rejection(60, unavailable=True)
        return None
