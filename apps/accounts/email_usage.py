"""Account-wide email quotas read from Resend, independent of dashboard filters."""

import hashlib

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.notifications import resend_client


def _period_usage(data, key, label):
    values = data[key]
    counts = {name: values[name] for name in ("used", "sent", "received", "limit")}
    for name, value in counts.items():
        if name == "limit" and value is None and key == "daily":
            continue
        if type(value) is not int or value < 0:
            raise ValueError("Invalid quota count")
    reset_value = values.get("resets_at")
    resets_at = parse_datetime(reset_value) if reset_value else None
    if reset_value and (resets_at is None or timezone.is_naive(resets_at)):
        raise ValueError("Invalid quota reset")
    limit, used = counts["limit"], counts["used"]
    remaining = max(limit - used, 0) if limit is not None else None
    percent = round(used * 100 / limit, 1) if limit else None
    exhausted = remaining == 0
    warning = exhausted or (limit is not None and used >= limit * 0.8)
    return {
        **counts,
        "key": key,
        "label": label,
        "remaining": remaining,
        "percent": percent,
        "progress": min(percent, 100) if percent is not None else None,
        "resets_at": resets_at,
        "warning": warning,
        "state": "Cuota consumida" if exhausted else "Cerca del límite" if warning else "",
    }


def email_usage_info():
    api_key = settings.RESEND_USAGE_API_KEY or settings.EMAIL_API_KEY
    info = {
        "kind": "email",
        "label": "Correos",
        "provider": "Resend",
        "available": False,
        "scope": "Consumo y límites de correo de la cuenta conectada",
        "periods": [{"key": "daily", "label": "Diario"}, {"key": "monthly", "label": "Mensual"}],
        "checked_at": timezone.now(),
    }
    if settings.EMAIL_PROVIDER != "resend" or not api_key:
        info["state"] = "Configura la conexión con Resend para consultar el consumo y los límites."
        return info

    fingerprint = hashlib.sha256(api_key.encode()).hexdigest()
    key = f"dashboard-email-usage-v1:{fingerprint}"
    cached = cache.get(key)
    if cached is not None:
        # Never show yesterday's remaining quota after Resend's reset instant.
        if all(
            not period.get("resets_at") or period["resets_at"] > timezone.now()
            for period in cached["periods"]
        ):
            return cached

    try:
        data = resend_client.usage(api_key)
        periods = [
            _period_usage(data, "daily", "Diario"),
            _period_usage(data, "monthly", "Mensual"),
        ]
        remaining = [period["remaining"] for period in periods if period["remaining"] is not None]
        info.update(
            available=True,
            periods=periods,
            remaining_today=min(remaining),
            over_capacity=any(period["warning"] for period in periods),
            state="Consumo real consultado en Resend",
        )
    except resend_client.UsageUnavailable as error:
        info["state"] = str(error)
    except (KeyError, TypeError, ValueError, OverflowError):
        info["state"] = "Resend devolvió datos de consumo incompletos. Intenta más tarde."
    info["checked_at"] = timezone.now()
    ttl = 300 if info["available"] else 30
    for period in info["periods"]:
        if period.get("resets_at"):
            ttl = min(ttl, max(1, int((period["resets_at"] - info["checked_at"]).total_seconds())))
    cache.set(key, info, ttl)
    return info
