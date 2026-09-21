from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User, Workspace
from apps.forms.models import (
    ConditionalRule,
    FieldOption,
    Form,
    FormField,
    FormSection,
    FormVersion,
)


class Command(BaseCommand):
    help = (
        "Crea un workspace y formulario ficticio en borrador, sin credenciales ni datos sensibles."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.ENABLE_DEMO_SEED:
            raise CommandError("seed_demo sólo está habilitado en settings.local.")
        call_command("setup_roles", stdout=self.stdout)
        workspace, _ = Workspace.objects.get_or_create(
            slug="demo-workspace", defaults={"name": "Demo Workspace"}
        )
        author, created = User.objects.get_or_create(
            username="seed-system-demo", defaults={"workspace": workspace, "is_active": False}
        )
        if created:
            author.set_unusable_password()
            author.save(update_fields=["password"])
        form, created = Form.objects.get_or_create(
            workspace=workspace,
            slug="registro-pacientes",
            defaults={
                "name": "Registro de pacientes",
                "created_by": author,
                "description": "Formulario de ejemplo para configurar la plataforma.",
            },
        )
        if created:
            version = FormVersion.objects.create(form=form, version_number=1)
            section = FormSection.objects.create(form_version=version, title="Información personal")
            FormField.objects.create(
                form_version=version,
                section=section,
                stable_key="nombre",
                label="Nombre",
                field_type="SHORT_TEXT",
                required=True,
            )
            FormField.objects.create(
                form_version=version,
                section=section,
                stable_key="documento",
                label="Documento",
                field_type="SHORT_TEXT",
                required=True,
                order=1,
            )
            choice = FormField.objects.create(
                form_version=version,
                section=section,
                stable_key="contactar",
                label="¿Deseas que te contactemos?",
                field_type="SINGLE_CHOICE",
                order=2,
            )
            FieldOption.objects.create(field=choice, label="Sí", value="si")
            FieldOption.objects.create(field=choice, label="No", value="no", order=1)
            email = FormField.objects.create(
                form_version=version,
                section=section,
                stable_key="correo",
                label="Correo",
                field_type="EMAIL",
                order=3,
            )
            ConditionalRule.objects.create(
                form_version=version,
                source_field=choice,
                operator="EQUALS",
                expected_value="si",
                action="SHOW",
                target_field=email,
            )
        self.stdout.write(
            self.style.SUCCESS("Datos de ejemplo disponibles. No se crean contraseñas.")
        )
