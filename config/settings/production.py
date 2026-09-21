from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

if len(SECRET_KEY) < 50:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_SECRET_KEY debe contener al menos 50 caracteres.")
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("Define DJANGO_ALLOWED_HOSTS con dominios explícitos.")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
# Sólo habilitar SECURE_PROXY_SSL_HEADER cuando el proxy elimine headers entrantes.
