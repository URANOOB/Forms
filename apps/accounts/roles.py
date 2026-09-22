from django.contrib.auth.models import Group, Permission

ADMINISTRATOR = "Administrador"
VIEWER = "Visor"
ROLE_CHOICES = ((ADMINISTRATOR, ADMINISTRATOR), (VIEWER, VIEWER))
LEGACY_ROLES = (
    "ADMIN",
    "MANAGER",
    "REVIEWER",
    "VIEWER",
    "Administrator",
    "Manager",
    "Reviewer",
    "Viewer",
)
SYSTEM_USERNAMES = ("seed-system", "seed-system-demo")


def setup_role_groups():
    administrator, _ = Group.objects.get_or_create(name=ADMINISTRATOR)
    viewer, _ = Group.objects.get_or_create(name=VIEWER)
    administrator.permissions.set(Permission.objects.all())
    viewer.permissions.set(
        Permission.objects.filter(content_type__app_label__in=("forms", "submissions"))
    )
    return administrator, viewer


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
