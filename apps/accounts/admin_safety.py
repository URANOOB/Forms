from django.db import connection

from .models import User

LAST_ADMIN_MESSAGE = "Debe quedar al menos un administrador activo con acceso al panel."


def lock_user_administration():
    """Serialize panel account mutations before validation, including bulk deletion."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [742901830])


def has_other_administrator(excluded):
    return (
        User.objects.filter(is_active=True, is_staff=True, is_superuser=True)
        .exclude(pk__in=excluded)
        .exists()
    )
