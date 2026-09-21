import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse_lazy
from dotenv import load_dotenv

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
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"
ENABLE_DEMO_SEED = False

UNFOLD = {
    "DASHBOARD_CALLBACK": "apps.accounts.dashboard.dashboard_callback",
    "SITE_TITLE": "Formularios institucionales",
    "SITE_HEADER": "Formularios",
    "SITE_SUBHEADER": "Gestión institucional",
    "SITE_SYMBOL": "assignment",
    "SHOW_HISTORY": True,
    "SIDEBAR": {
        "show_search": False,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Administración",
                "items": [
                    {"title": "Inicio", "icon": "dashboard", "link": reverse_lazy("admin:index")},
                    {
                        "title": "Formularios",
                        "icon": "description",
                        "link": reverse_lazy("admin:forms_form_changelist"),
                        "permission": lambda r: r.user.has_perm("forms.view_form"),
                    },
                    {
                        "title": "Respuestas",
                        "icon": "inbox",
                        "link": reverse_lazy("admin:submissions_submission_changelist"),
                        "permission": lambda r: r.user.has_perm("submissions.view_submission"),
                    },
                    {
                        "title": "Usuarios",
                        "icon": "group",
                        "link": reverse_lazy("admin:accounts_user_changelist"),
                        "permission": lambda r: r.user.is_superuser,
                    },
                    {
                        "title": "Grupos y permisos",
                        "icon": "admin_panel_settings",
                        "link": reverse_lazy("admin:auth_group_changelist"),
                        "permission": lambda r: r.user.is_superuser,
                    },
                ],
            }
        ],
    },
}
