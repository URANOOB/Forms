from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User, Workspace
from apps.forms.models import (
    ConditionalRule,
    FieldOption,
    Form,
    FormField,
    FormSection,
    FormVersion,
)


class SchemaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Institución", slug="institucion")
        cls.user = User.objects.create_user(username="manager", workspace=cls.workspace)
        cls.form = Form.objects.create(
            workspace=cls.workspace, name="Registro", slug="registro", created_by=cls.user
        )
        cls.version = FormVersion.objects.create(form=cls.form, version_number=1)
        cls.section = FormSection.objects.create(form_version=cls.version, title="Contacto")
        cls.field = FormField.objects.create(
            form_version=cls.version,
            section=cls.section,
            stable_key="nombre",
            label="Nombre",
            field_type="SHORT_TEXT",
        )

    def other_version(self):
        form = Form.objects.create(
            workspace=self.workspace, name="Otro", slug="otro", created_by=self.user
        )
        return FormVersion.objects.create(form=form, version_number=1)

    def publish_fixture(self):
        self.version.status = "PUBLISHED"
        self.version.published_at = timezone.now()
        self.version.save()

    def test_slug_is_unique_within_workspace(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Form.objects.create(
                workspace=self.workspace, name="Duplicado", slug="registro", created_by=self.user
            )
        workspace = Workspace.objects.create(name="Otro", slug="otro")
        Form.objects.create(
            workspace=workspace, name="Registro", slug="registro", created_by=self.user
        )

    def test_only_one_draft_per_form(self):
        with self.assertRaises(ValidationError):
            FormVersion.objects.create(form=self.form, version_number=2)

    def test_version_number_stays_unique_after_publication(self):
        self.publish_fixture()
        with self.assertRaises(ValidationError):
            FormVersion.objects.create(form=self.form, version_number=1)

    def test_publication_requires_timestamp(self):
        self.version.status = "PUBLISHED"
        with self.assertRaises(ValidationError):
            self.version.save()

    def test_published_version_and_content_are_frozen(self):
        self.publish_fixture()
        self.field.refresh_from_db()
        self.section.refresh_from_db()
        for obj in (self.version, self.section, self.field):
            with self.subTest(model=type(obj).__name__), self.assertRaises(ValidationError):
                obj.save()
            with self.subTest(delete=type(obj).__name__), self.assertRaises(ValidationError):
                obj.delete()
        FormVersion.objects.create(form=self.form, version_number=2)

    def test_cannot_move_published_field_to_draft(self):
        self.publish_fixture()
        version = FormVersion.objects.create(form=self.form, version_number=2)
        section = FormSection.objects.create(form_version=version, title="Nueva")
        self.field.form_version = version
        self.field.section = section
        with self.assertRaises(ValidationError):
            self.field.save()

    def test_stable_key_unique_across_sections(self):
        section = FormSection.objects.create(form_version=self.version, title="Otra")
        with self.assertRaises(ValidationError):
            FormField.objects.create(
                form_version=self.version,
                section=section,
                stable_key="nombre",
                label="Duplicado",
                field_type="SHORT_TEXT",
            )

    def test_field_cannot_reference_foreign_section(self):
        self.field.form_version = self.other_version()
        with self.assertRaises(ValidationError):
            self.field.save()

    def test_configuration_must_be_json_object(self):
        for value in (["invalid"], [], "", None, False):
            self.field.configuration = value
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.field.save()

    def test_cached_draft_cannot_add_content_after_publication(self):
        stale_version = FormVersion.objects.get(pk=self.version.pk)
        self.publish_fixture()
        with self.assertRaises(ValidationError):
            FormSection.objects.create(form_version=stale_version, title="Tardía")
        with self.assertRaises(ValidationError):
            stale_version.delete()

    def test_section_cannot_move_between_drafts(self):
        self.section.form_version = self.other_version()
        with self.assertRaises(ValidationError):
            self.section.save()

    def test_information_cannot_be_required(self):
        self.field.field_type = "INFORMATION"
        self.field.required = True
        with self.assertRaises(ValidationError):
            self.field.save()

    def test_options_only_for_choice_fields(self):
        with self.assertRaises(ValidationError):
            FieldOption.objects.create(field=self.field, label="Opción", value="option")
        self.field.field_type = "SINGLE_CHOICE"
        self.field.save()
        FieldOption.objects.create(field=self.field, label="Opción", value="option")
        with self.assertRaises(ValidationError):
            FieldOption.objects.create(field=self.field, label="Duplicada", value="option")

    def test_active_version_must_belong_to_form(self):
        self.form.active_version = self.other_version()
        with self.assertRaises(ValidationError):
            self.form.full_clean()

    def test_published_form_needs_active_version_at_database_level(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Form.objects.filter(pk=self.form.pk).update(status="PUBLISHED")

    def rule(self, **overrides):
        section = FormSection.objects.create(form_version=self.version, title="Destino")
        data = dict(
            form_version=self.version,
            source_field=self.field,
            operator="IS_NOT_EMPTY",
            action="SHOW",
            target_section=section,
        )
        data.update(overrides)
        return ConditionalRule(**data)

    def test_conditional_rule_rejects_foreign_version(self):
        with self.assertRaises(ValidationError):
            self.rule(form_version=self.other_version()).save()

    def test_conditional_rule_requires_exactly_one_target(self):
        for overrides in ({"target_section": None}, {"target_field": self.field}):
            with self.subTest(overrides=overrides), self.assertRaises(ValidationError):
                self.rule(**overrides).save()

    def test_rule_group_has_consistent_action_and_target(self):
        first = self.rule(group_key="contacto")
        first.save()
        second = self.rule(action="HIDE", target_section=first.target_section, group_key="contacto")
        with self.assertRaises(ValidationError):
            second.save()

    def test_rule_cannot_control_own_section(self):
        with self.assertRaises(ValidationError):
            self.rule(target_section=self.section).save()

    def test_ungrouped_rules_can_have_different_targets(self):
        self.rule().save()
        self.rule().save()
        self.assertEqual(self.version.rules.count(), 2)

    def test_rule_rejects_unknown_operator(self):
        with self.assertRaises(ValidationError):
            self.rule(operator="EXECUTE_PYTHON").save()
