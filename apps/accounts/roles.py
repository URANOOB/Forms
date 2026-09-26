from django.contrib.auth.models import Group, Permission

ADMINISTRATOR = "Administrador"
OPERATOR = "Operador"
ROLE_CHOICES = ((ADMINISTRATOR, ADMINISTRATOR), (OPERATOR, OPERATOR))
LEGACY_ROLES = (
    "ADMIN",
    "MANAGER",
    "REVIEWER",
    "VIEWER",
    "Visor",
    "Administrator",
    "Manager",
    "Reviewer",
    "Viewer",
)
SYSTEM_USERNAMES = ("seed-system", "seed-system-demo")


def setup_role_groups():
    administrator, _ = Group.objects.get_or_create(name=ADMINISTRATOR)
    operator, _ = Group.objects.get_or_create(name=OPERATOR)
    administrator.permissions.set(Permission.objects.all())
    operator.permissions.set(
        Permission.objects.filter(content_type__app_label__in=("forms", "submissions"))
    )
    return administrator, operator


def assign_role(user, role):
    user.groups.set([Group.objects.get(name=role)])
    user.user_permissions.clear()


def visible_users(queryset):
    return queryset.exclude(
        username__in=SYSTEM_USERNAMES,
        is_active=False,
        is_staff=False,
        is_superuser=False,
    )
