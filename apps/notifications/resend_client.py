"""The only module allowed to communicate with Resend."""

import resend
from django.conf import settings


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
