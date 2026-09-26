"""The only module allowed to communicate with Resend."""

import json

import resend
from django.conf import settings


class UsageUnavailable(Exception):
    """Only safe, user-facing diagnostics may leave the usage client."""


def usage(api_key):
    # Use a separate client so a monitoring key never replaces the sending key
    # in the SDK's process-wide configuration while another request sends mail.
    try:
        body, status, _ = resend.RequestsClient(timeout=5).request(
            method="get",
            url="https://api.resend.com/usage",
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        )
    except (RuntimeError, OSError):
        raise UsageUnavailable("No se pudo conectar con Resend. Intenta más tarde.") from None
    if status in {401, 403}:
        raise UsageUnavailable(
            "Resend no autorizó la consulta de consumo. Revisa la clave y sus permisos."
        )
    if status == 429:
        raise UsageUnavailable("Resend limitó las consultas. Intenta más tarde.")
    if status != 200:
        raise UsageUnavailable("No se pudo consultar el consumo en Resend.")
    try:
        data = json.loads(body)
        if not isinstance(data, dict) or not isinstance(data.get("emails"), dict):
            raise ValueError
        return data["emails"]
    except (ValueError, UnicodeError):
        raise UsageUnavailable("Resend devolvió datos de consumo no disponibles.") from None


def send(payload, key):
    resend.api_key = settings.EMAIL_API_KEY
    resend.default_http_client = resend.RequestsClient(timeout=10)
    return resend.Emails.send(payload, {"idempotency_key": key})["id"]


def verify(body, headers):
    return resend.Webhooks.verify(
        {
            "payload": body.decode("utf-8"),
            "headers": {
                name: headers.get(f"svix-{name}", "") for name in ("id", "timestamp", "signature")
            },
            "webhook_secret": settings.RESEND_WEBHOOK_SECRET,
        }
    )


def safe_error(error):
    # Provider messages may echo recipients, payloads or credentials. Persist only
    # allowlisted diagnostics; never str(error), response bodies or tracebacks.
    code = getattr(error, "code", None)
    try:
        code = int(code)
    except (ValueError, TypeError):
        code = None
    if code in {401, 403}:
        return "Resend rechazó la autenticación o los permisos. Revisa la configuración."
    if code == 429:
        return "Resend limitó temporalmente los envíos. Reintenta más tarde."
    if code in {400, 422}:
        return "Resend rechazó los datos del envío. Revisa remitente y destinatario."
    return (
        "No se pudo confirmar el envío con Resend. Puedes reintentar dentro de la ventana segura."
    )
