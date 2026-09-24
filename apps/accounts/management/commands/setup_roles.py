from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.roles import (
    ADMINISTRATOR,
    LEGACY_ROLES,
    VIEWER,
    assign_role,
    setup_role_groups,
    visible_users,
)


class Command(BaseCommand):
    help = "Configura los roles Administrador y Visor y sustituye los roles anteriores."

    @transaction.atomic
    def handle(self, *args, **options):
        setup_role_groups()
        for user in visible_users(get_user_model().objects.all()).iterator():
            user.is_superuser = (
                user.is_superuser
                or user.groups.filter(name__in=(ADMINISTRATOR, "ADMIN", "Administrator")).exists()
            )
            user.is_staff = True
            user.save(update_fields=("is_superuser", "is_staff"))
            assign_role(user, ADMINISTRATOR if user.is_superuser else VIEWER)
        Group.objects.filter(name__in=LEGACY_ROLES).delete()
        self.stdout.write(self.style.SUCCESS("Roles Administrador y Visor configurados."))
