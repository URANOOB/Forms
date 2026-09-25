import os
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from django.templatetags.static import static
from django.urls import reverse
from dotenv import load_dotenv

from config.storage import storage_settings

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in {"true", "1", "yes"}


def env_list(name, default=""):
    return [value.strip() for value in os.environ.get(name, default).split(",") if value.strip()]


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
if PUBLIC_BASE_URL:
    origin = urlsplit(PUBLIC_BASE_URL)
    if (
        origin.scheme not in {"http", "https"}
        or not origin.hostname
        or origin.username is not None
        or origin.password is not None
        or origin.path
        or origin.query
        or origin.fragment
    ):
        raise ImproperlyConfigured("PUBLIC_BASE_URL debe ser un origen sin ruta ni credenciales.")
INSTALLED_APPS = [
    "unfold",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.accounts",
    "apps.forms",
    "apps.submissions",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "config.middleware.DevelopmentNotFoundMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.accounts.platform.shell_context",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
database_url = os.environ.get("DATABASE_URL", "")
if not database_url:
    raise ImproperlyConfigured("DATABASE_URL es obligatoria; consulta .env.example.")
DATABASES = {"default": dj_database_url.parse(database_url, conn_max_age=0)}
if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise ImproperlyConfigured("Esta aplicación requiere PostgreSQL.")
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": f"django.contrib.auth.password_validation.{name}"}
    for name in [
        "UserAttributeSimilarityValidator",
        "MinimumLengthValidator",
        "CommonPasswordValidator",
        "NumericPasswordValidator",
    ]
]
LANGUAGE_CODE = "es-co"
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "America/Bogota")
try:
    ZoneInfo(TIME_ZONE)
except (ZoneInfoNotFoundError, ValueError):
    raise ImproperlyConfigured("DJANGO_TIME_ZONE debe ser una zona horaria válida.") from None
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = storage_settings(BASE_DIR, os.environ)


def env_capacity(name):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        raise ImproperlyConfigured(f"{name} debe ser una capacidad positiva en bytes.") from None
    if value <= 0:
        raise ImproperlyConfigured(f"{name} debe ser una capacidad positiva en bytes.")
    return value


DATABASE_CAPACITY_BYTES = env_capacity("DATABASE_CAPACITY_BYTES")
R2_FREE_STORAGE_REFERENCE_BYTES = env_capacity("R2_FREE_STORAGE_REFERENCE_BYTES")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
# JSON drafts can include imported catalogs; multipart files retain their own 5 MB limit.
DATA_UPLOAD_MAX_MEMORY_SIZE = 8 * 1024 * 1024
# Leave room for multipart headers below Vercel's 4.5 MB request limit.
SUBMISSION_MAX_BYTES = 4_000_000 if os.environ.get("VERCEL") == "1" else None
EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"
ENABLE_DEMO_SEED = False

UNFOLD = {
    "DASHBOARD_CALLBACK": "apps.accounts.dashboard.dashboard_callback",
    "SITE_TITLE": "Formularios institucionales",
    "SITE_HEADER": "LogicForms",
    "SITE_LOGO": lambda request: static("forms/brand/logicforms-logo.png") + "?v=2",
    "SITE_SUBHEADER": "Gestión institucional",
    "SITE_SYMBOL": "assignment",
    "SHOW_HISTORY": True,
    "SIDEBAR": {
        "show_search": False,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "",
                "items": [
                    {
                        "title": "Panel general",
                        "icon": "space_dashboard",
                        "icon_template": "unfold/helpers/platform_nav_icon.html",
                        "link": lambda request: reverse("admin:index"),
                    },
                    {
                        "title": "Formularios",
                        "icon": "dynamic_form",
                        "icon_template": "unfold/helpers/platform_nav_icon.html",
                        "link": lambda request: reverse("admin:forms_form_changelist"),
                        "permission": lambda r: r.user.has_perm("forms.view_form"),
                    },
                    {
                        "title": "Respuestas recibidas",
                        "icon": "inbox",
                        "icon_template": "unfold/helpers/platform_nav_icon.html",
                        "link": lambda request: reverse("admin:submissions_submission_changelist"),
                        "permission": lambda r: r.user.has_perm("submissions.view_submission"),
                    },
                    {
                        "title": "Reportes y descargas",
                        "icon": "analytics",
                        "icon_template": "unfold/helpers/platform_nav_icon.html",
                        "link": lambda request: reverse("admin:submissions_submission_reports"),
                        "permission": lambda r: r.user.has_perm("submissions.view_submission"),
                    },
                    {
                        "title": "Usuarios y permisos",
                        "icon": "manage_accounts",
                        "icon_template": "unfold/helpers/platform_nav_icon.html",
                        "link": lambda request: reverse("admin:accounts_user_changelist"),
                        "permission": lambda r: (
                            r.user.is_active and r.user.is_staff and r.user.is_superuser
                        ),
                    },
                ],
            }
        ],
    },
}
