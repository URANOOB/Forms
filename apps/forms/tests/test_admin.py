from io import StringIO

from django.contrib import admin
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User, Workspace, legacy_form_container
from apps.forms.models import (
    ConditionalRule,
    FieldOption,
    Form,
    FormField,
    FormSection,
    FormVersion,
)


class AdminAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Institución", slug="institucion")
        cls.other = Workspace.objects.create(name="Otra", slug="otra")
        cls.manager = User.objects.create_user(
            username="manager", is_staff=True, workspace=cls.workspace
        )
        cls.manager.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="forms",
                codename__in=["view_form", "add_form", "change_form"],
            )
        )
        cls.form = Form.objects.create(
            workspace=cls.workspace,
            name="Formulario propio",
            slug="registro",
            created_by=cls.manager,
        )
        cls.foreign = Form.objects.create(
            workspace=cls.other, name="Formulario ajeno", slug="registro", created_by=cls.manager
        )
        cls.admin = User.objects.create_superuser(username="admin", password=None)

    def setUp(self):
        self.client.force_login(self.manager)

    def test_changelist_shares_forms_across_legacy_workspaces(self):
        response = self.client.get(reverse("admin:forms_form_changelist"))
        self.assertContains(response, "Formulario propio")
        self.assertContains(response, "Formulario ajeno")

    def test_editor_can_open_forms_from_legacy_workspaces(self):
        response = self.client.get(reverse("admin:forms_form_change", args=[self.foreign.pk]))
        self.assertContains(response, "Formulario ajeno")

    def test_legacy_create_ignores_supplied_workspace_and_slug(self):
        response = self.client.post(
            reverse("admin:forms_form_add"),
            {
                "name": "Ataque",
                "slug": "ataque",
                "workspace": self.other.pk,
                "versions-TOTAL_FORMS": "0",
                "versions-INITIAL_FORMS": "0",
            },
        )
        self.assertEqual(response.status_code, 302)
        created = Form.objects.get(name="Ataque")
        self.assertEqual(created.workspace, legacy_form_container())
        self.assertNotEqual(created.slug, "ataque")

    def test_create_form_creates_initial_draft(self):
        response = self.client.post(
            reverse("admin:forms_form_add"),
            {
                "name": "Nuevo",
                "slug": "nuevo",
                "workspace": self.workspace.pk,
                "versions-TOTAL_FORMS": "0",
                "versions-INITIAL_FORMS": "0",
            },
        )
        self.assertEqual(response.status_code, 302)
        form = Form.objects.get(name="Nuevo")
        self.assertEqual(form.created_by, self.manager)
        self.assertEqual(form.versions.get().version_number, 1)

    def test_archive_action_applies_to_selected_shared_forms(self):
        self.client.post(
            reverse("admin:forms_form_changelist"),
            {
                "action": "archive_forms",
                "_selected_action": [self.form.pk, self.foreign.pk],
            },
        )
        self.form.refresh_from_db()
        self.foreign.refresh_from_db()
        self.assertEqual(self.form.status, "ARCHIVED")
        self.assertEqual(self.foreign.status, "ARCHIVED")

    def test_no_normal_hard_delete_even_for_superuser(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("admin:forms_form_delete", args=[self.form.pk]), {"post": "yes"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Form.objects.filter(pk=self.form.pk).exists())

    def test_no_privilege_escalation_through_user_or_group_admin(self):
        self.manager.user_permissions.set(Permission.objects.all())
        self.assertEqual(
            self.client.get(reverse("admin:accounts_user_changelist")).status_code, 403
        )
        self.assertFalse(admin.site.is_registered(Workspace))
        self.assertFalse(admin.site.is_registered(Group))

    def test_legacy_workspace_activity_does_not_control_access(self):
        self.workspace.is_active = False
        self.workspace.save()
        response = self.client.get(reverse("admin:forms_form_change", args=[self.form.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:forms_form_add")).status_code, 200)

    def test_authorized_staff_without_workspace_sees_shared_forms(self):
        self.manager.workspace = None
        self.manager.save()
        response = self.client.get(reverse("admin:forms_form_changelist"))
        self.assertContains(response, "Formulario propio")
        self.assertContains(response, "Formulario ajeno")

    def test_viewer_cannot_change_or_archive(self):
        self.manager.user_permissions.set(
            Permission.objects.filter(content_type__app_label="forms", codename="view_form")
        )
        response = self.client.get(reverse("admin:forms_form_change", args=[self.form.pk]))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse("admin:forms_form_change", args=[self.form.pk]), {"name": "Modificado"}
        )
        self.assertEqual(response.status_code, 403)
        self.client.post(
            reverse("admin:forms_form_changelist"),
            {
                "action": "archive_forms",
                "_selected_action": [self.form.pk],
            },
        )
        self.form.refresh_from_db()
        self.assertEqual(self.form.status, "DRAFT")

    def test_admin_pages_render_with_unfold(self):
        self.client.force_login(self.admin)
        for name in (
            "index",
            "accounts_user_add",
            "accounts_user_changelist",
            "forms_form_add",
        ):
            with self.subTest(page=name):
                response = self.client.get(reverse(f"admin:{name}"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "unfold/")

    def test_public_and_anonymous_access(self):
        self.client.logout()
        self.assertEqual(self.client.get("/admin/").status_code, 302)
        self.assertEqual(self.client.get("/f/registro/").status_code, 404)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_schema_admin_shares_legacy_workspaces_and_allows_draft_relations(self):
        self.manager.user_permissions.set(
            Permission.objects.filter(content_type__app_label="forms")
        )
        version = FormVersion.objects.create(form=self.foreign, version_number=1)
        section = FormSection.objects.create(form_version=version, title="Sección ajena")
        field = FormField.objects.create(
            form_version=version,
            section=section,
            label="Campo ajeno",
            stable_key="ajeno",
            field_type="SINGLE_CHOICE",
        )
        option = FieldOption.objects.create(field=field, label="Opción ajena", value="a")
        target = FormSection.objects.create(form_version=version, title="Destino ajeno")
        rule = ConditionalRule.objects.create(
            form_version=version,
            source_field=field,
            target_section=target,
            operator="IS_EMPTY",
            action="SHOW",
        )
        for obj in (version, section, field, option, rule):
            model = obj._meta.model_name
            with self.subTest(model=model):
                response = self.client.get(reverse(f"admin:forms_{model}_changelist"))
                self.assertEqual(response.status_code, 200)
                self.assertIn(obj, response.context["cl"].queryset)
                response = self.client.get(reverse(f"admin:forms_{model}_change", args=[obj.pk]))
                self.assertEqual(response.status_code, 200)
                if model != "formversion":
                    response = self.client.get(reverse(f"admin:forms_{model}_add"))
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, "ajeno")
        response = self.client.post(
            reverse("admin:forms_formsection_add"),
            {
                "form_version": version.pk,
                "title": "Intrusión",
                "order": "0",
                "configuration": "{}",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(FormSection.objects.get(title="Intrusión").form_version, version)

    def test_schema_admin_can_create_draft_content_and_protects_published_content(self):
        self.manager.user_permissions.set(
            Permission.objects.filter(content_type__app_label="forms")
        )
        version = FormVersion.objects.create(form=self.form, version_number=1)
        response = self.client.post(
            reverse("admin:forms_formsection_add"),
            {
                "form_version": version.pk,
                "title": "Información",
                "order": "0",
                "configuration": "{}",
            },
        )
        self.assertEqual(response.status_code, 302)
        section = version.sections.get()
        response = self.client.post(
            reverse("admin:forms_formfield_add"),
            {
                "form_version": version.pk,
                "section": section.pk,
                "stable_key": "opcion",
                "label": "Opción",
                "field_type": "SINGLE_CHOICE",
                "order": "0",
                "configuration": "{}",
                "validation": "{}",
            },
        )
        self.assertEqual(response.status_code, 302)
        field = version.fields.get()
        response = self.client.post(
            reverse("admin:forms_fieldoption_add"),
            {
                "field": field.pk,
                "label": "Sí",
                "value": "si",
                "order": "0",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(field.options.get().value, "si")
        target = FormSection.objects.create(form_version=version, title="Destino")
        response = self.client.post(
            reverse("admin:forms_conditionalrule_add"),
            {
                "form_version": version.pk,
                "source_field": field.pk,
                "operator": "EQUALS",
                "expected_value": '"si"',
                "action": "SHOW",
                "target_section": target.pk,
                "group_operator": "AND",
                "order": "0",
            },
        )
        self.assertEqual(response.status_code, 302)
        rule = version.rules.get()
        version.status = "PUBLISHED"
        version.published_at = timezone.now()
        version.save()
        for obj in (version, section, field, field.options.get(), rule):
            url = reverse(f"admin:forms_{obj._meta.model_name}_change", args=[obj.pk])
            with self.subTest(model=obj._meta.model_name):
                self.assertEqual(self.client.get(url).status_code, 200)
                self.assertEqual(self.client.post(url, {}).status_code, 403)


class SeedTests(TestCase):
    @override_settings(ENABLE_DEMO_SEED=False)
    def test_seed_is_disabled_outside_development(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo", stdout=StringIO())
        self.assertEqual(Workspace.objects.count(), 0)

    def test_seed_is_idempotent_and_never_creates_login_credentials(self):
        for _ in range(2):
            call_command("seed_demo", stdout=StringIO())
        self.assertEqual(Form.objects.count(), 1)
        self.assertEqual(FormVersion.objects.count(), 1)
        user = User.objects.get(username="seed-system-demo")
        self.assertFalse(user.is_active)
        self.assertFalse(user.has_usable_password())
        form = Form.objects.get()
        self.assertEqual(form.status, "DRAFT")
        self.assertEqual(form.versions.get().fields.count(), 4)
