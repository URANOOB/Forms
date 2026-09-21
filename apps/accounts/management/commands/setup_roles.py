from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Crea grupos Django y añade permisos base sin eliminar asignaciones personalizadas."

    @transaction.atomic
    def handle(self, *args, **options):
        for name in ("Administrator", "Manager", "Reviewer", "Viewer"):
            group, _ = Group.objects.get_or_create(name=name)
            actions = ["view"]
            if name in {"Administrator", "Manager"}:
                actions += ["add", "change"]
            permissions = Permission.objects.filter(content_type__app_label="forms")
            group.permissions.add(
                *[
                    permission
                    for permission in permissions
                    if permission.codename.split("_", 1)[0] in actions
                ]
            )
            codenames = ["view_submission"]
            if name in {"Administrator", "Manager", "Reviewer"}:
                codenames.append("change_submission")
            if name in {"Administrator", "Manager"}:
                codenames.append("delete_submission")
            group.permissions.add(
                *Permission.objects.filter(
                    content_type__app_label="submissions", codename__in=codenames
                )
            )
        self.stdout.write(self.style.SUCCESS("Grupos y permisos base disponibles."))
