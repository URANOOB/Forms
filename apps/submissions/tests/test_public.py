import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User, Workspace
from apps.forms.conditions import FormSchema
from apps.forms.models import (
    ConditionalRule,
    FieldOption,
    Form,
    FormField,
    FormSection,
    FormVersion,
)
from apps.forms.publication import publish_form, set_form_status
from apps.submissions.models import Submission, SubmissionAnswer
from apps.submissions.runtime import PublicResponseForm, new_token, save_response


def fixture(workspace_slug="demo", form_slug="registro"):
    workspace = Workspace.objects.create(name="Institución", slug=workspace_slug)
    user = User.objects.create_user(username=workspace_slug, workspace=workspace, is_staff=True)
    form = Form.objects.create(
        workspace=workspace,
        created_by=user,
        name="Registro",
        slug=form_slug,
        description="Información de contacto",
    )
    version = FormVersion.objects.create(form=form, version_number=1)
    section = FormSection.objects.create(form_version=version, title="Datos personales")
    name = FormField.objects.create(
        form_version=version,
        section=section,
        label="Nombre",
        stable_key="nombre",
        field_type="SHORT_TEXT",
        required=True,
    )
    choice = FormField.objects.create(
        form_version=version,
        section=section,
        label="¿Te contactamos?",
        stable_key="contactar",
        field_type="SINGLE_CHOICE",
        order=1,
    )
    FieldOption.objects.create(field=choice, label="Sí", value="si")
    FieldOption.objects.create(field=choice, label="No", value="no", order=1)
    email = FormField.objects.create(
        form_version=version,
        section=section,
        label="Correo",
        stable_key="correo",
        field_type="EMAIL",
        required=True,
        order=2,
    )
    ConditionalRule.objects.create(
        form_version=version,
        source_field=choice,
        target_field=email,
        operator="EQUALS",
        expected_value="si",
        action="SHOW",
    )
    return form, version, name, choice, email


class PublicTests(TestCase):
    def setUp(self):
        self.form, self.version, self.name, self.choice, self.email = fixture()
        self.form = publish_form(self.form.pk)
        self.url = self.form.get_absolute_url()

    def payload(self, **kwargs):
        return {
            "submission_token": new_token(self.form),
            "answer_nombre": "Persona de prueba",
            "answer_contactar": "no",
            **kwargs,
        }

    def test_anonymous_open_and_submit_records_version_and_answers(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Registro")
        self.assertNotContains(response, "/admin/")
        self.assertIn("no-store", response.headers["Cache-Control"])
        response = self.client.post(self.url, self.payload(), follow=True)
        self.assertContains(response, "Respuesta registrada")
        submission = Submission.objects.get()
        self.assertEqual(submission.form_version_id, self.version.pk)
        self.assertEqual(submission.answers.get(field=self.name).value, "Persona de prueba")
        self.assertFalse(submission.answers.filter(field=self.email).exists())
        self.assertNotContains(response, "Persona de prueba")

    def test_required_fields_and_conditional_validation_preserve_input(self):
        response = self.client.post(self.url, self.payload(answer_nombre="", answer_contactar="si"))
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "Este campo es obligatorio", status_code=422)
        self.assertEqual(Submission.objects.count(), 0)
        response = self.client.post(
            self.url, self.payload(answer_contactar="si", answer_correo="inválido")
        )
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "Persona de prueba", status_code=422)
        self.assertFalse(Submission.objects.exists())

    def test_hidden_values_are_discarded_and_invalid_choices_are_rejected(self):
        response = self.client.post(self.url, self.payload(answer_correo="invalid@example.org"))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SubmissionAnswer.objects.filter(field=self.email).exists())
        response = self.client.post(self.url, self.payload(answer_contactar="forged"))
        self.assertEqual(response.status_code, 422)
        self.assertEqual(Submission.objects.count(), 1)

    def test_signed_token_and_csrf_are_required(self):
        response = self.client.post(self.url, self.payload(submission_token="forged"))
        self.assertEqual(response.status_code, 409)
        self.assertFalse(Submission.objects.exists())
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.get(self.url)
        response = csrf_client.post(self.url, self.payload())
        self.assertEqual(response.status_code, 403)
        response = csrf_client.post(
            self.url, self.payload(), HTTP_X_CSRFTOKEN=csrf_client.cookies["csrftoken"].value
        )
        self.assertEqual(response.status_code, 302)

    def test_expired_token_is_rejected(self):
        with patch(
            "django.core.signing.time.time",
            return_value=(timezone.now() - timedelta(days=2)).timestamp(),
        ):
            data = self.payload()
        self.assertEqual(self.client.post(self.url, data).status_code, 409)
        self.assertFalse(Submission.objects.exists())

    def test_duplicate_post_stores_once(self):
        data = self.payload()
        for _ in range(2):
            self.assertEqual(self.client.post(self.url, data).status_code, 302)
        self.assertEqual(Submission.objects.count(), 1)

    def test_closed_forms_block_submissions_and_legacy_workspace_is_not_an_access_boundary(self):
        Form.objects.filter(pk=self.form.pk).update(status="PAUSED")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "public/closed.html")
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 409)
        for status in ("ARCHIVED", "DRAFT"):
            Form.objects.filter(pk=self.form.pk).update(status=status)
            with self.subTest(status=status):
                self.assertEqual(self.client.get(self.url).status_code, 404)
                self.assertEqual(self.client.post(self.url, self.payload()).status_code, 404)
        Form.objects.filter(pk=self.form.pk).update(status="PUBLISHED")
        Workspace.objects.filter(pk=self.form.workspace_id).update(is_active=False)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertFalse(Submission.objects.exists())

    def test_two_workspaces_same_slug_and_token_cannot_cross_forms(self):
        other, *_ = fixture("other")
        other = publish_form(other.pk)
        self.assertNotEqual(self.url, other.get_absolute_url())
        response = self.client.post(other.get_absolute_url(), self.payload())
        self.assertEqual(response.status_code, 409)
        self.assertFalse(Submission.objects.exists())

    def test_stale_version_rejected_and_old_answers_remain_unchanged(self):
        self.client.post(self.url, self.payload())
        old_data = self.payload()
        version2 = FormVersion.objects.create(form=self.form, version_number=2)
        section = FormSection.objects.create(form_version=version2, title="Nueva sección")
        FormField.objects.create(
            form_version=version2,
            section=section,
            stable_key="nombre",
            label="Nombre actualizado",
            field_type="SHORT_TEXT",
            required=True,
        )
        publish_form(self.form.pk)
        self.assertEqual(self.client.post(self.url, old_data).status_code, 409)
        submission = Submission.objects.get()
        self.assertEqual(submission.form_version_id, self.version.pk)
        self.assertEqual(submission.answers.get(field=self.name).field.label, "Nombre")

    def test_publication_freezes_content_and_can_resume_after_pause(self):
        self.name.label = "Cambio no permitido"
        with self.assertRaises(ValidationError):
            self.name.save()
        set_form_status(self.form.pk, "PAUSED")
        self.assertTemplateUsed(self.client.get(self.url), "public/closed.html")
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 409)
        publish_form(self.form.pk)
        self.assertEqual(self.client.get(self.url).status_code, 200)


class PublicationValidationTests(TestCase):
    def setUp(self):
        self.form, self.version, self.name, self.choice, self.email = fixture()

    def test_cycles_unsupported_types_and_invalid_validation_block_publication(self):
        ConditionalRule.objects.create(
            form_version=self.version,
            source_field=self.email,
            target_field=self.choice,
            operator="IS_NOT_EMPTY",
            action="SHOW",
        )
        with self.assertRaises(ValidationError):
            publish_form(self.form.pk)
        self.version.rules.all().delete()
        FormField.objects.filter(pk=self.name.pk).update(field_type="UNSUPPORTED")
        with self.assertRaises(ValidationError):
            publish_form(self.form.pk)
        self.name.field_type = "SHORT_TEXT"
        self.name.validation = {"arbitrary_python": "print('no')"}
        self.name.save()
        with self.assertRaises(ValidationError):
            publish_form(self.form.pk)
        self.form.refresh_from_db()
        self.assertEqual(self.form.status, "DRAFT")

    def test_typed_answers_and_constraints(self):
        section = self.name.section
        for key, kind in [
            ("numero", "NUMBER"),
            ("fecha", "DATE"),
            ("booleano", "BOOLEAN"),
            ("multiple", "MULTIPLE_CHOICE"),
        ]:
            field = FormField.objects.create(
                form_version=self.version,
                section=section,
                label=key,
                stable_key=key,
                field_type=kind,
                required=True,
                validation={"min_value": 1} if kind == "NUMBER" else {},
            )
            if kind == "MULTIPLE_CHOICE":
                FieldOption.objects.create(field=field, label="Uno", value="uno")
        schema = FormSchema(self.version)
        data = {
            "answer_nombre": "Ejemplo",
            "answer_contactar": "no",
            "answer_numero": "25",
            "answer_fecha": "2000-02-29",
            "answer_booleano": "false",
            "answer_multiple": ["uno"],
        }
        runtime = PublicResponseForm(schema, data=data)
        self.assertTrue(runtime.is_valid(), runtime.errors)
        by_key = {field.stable_key: runtime.answers.get(field.pk) for field in schema.fields}
        self.assertEqual(by_key["numero"], 25)
        self.assertIs(by_key["booleano"], False)
        self.assertEqual(by_key["fecha"], "2000-02-29")
        self.assertEqual(by_key["multiple"], ["uno"])
        for key, value in [
            ("numero", "NaN"),
            ("numero", "2.5"),
            ("numero", "-1"),
            ("numero", "0"),
            ("fecha", "2001-02-29"),
            ("booleano", "perhaps"),
            ("multiple", ["forged"]),
        ]:
            with self.subTest(key=key, value=value):
                runtime = PublicResponseForm(
                    FormSchema(self.version), data={**data, f"answer_{key}": value}
                )
                self.assertFalse(runtime.is_valid())

    def test_condition_operators_control_required_fields_on_server(self):
        self.version.rules.all().delete()
        source = FormField.objects.create(
            form_version=self.version,
            section=self.name.section,
            label="Origen",
            stable_key="origen",
            field_type="SHORT_TEXT",
        )
        cases = [
            ("EQUALS", "SHORT_TEXT", "abc", "abc", True),
            ("NOT_EQUALS", "SHORT_TEXT", "abc", "xyz", True),
            ("CONTAINS", "SHORT_TEXT", "b", "abc", True),
            ("GREATER_THAN", "NUMBER", 2, "3", True),
            ("LESS_THAN", "NUMBER", 2, "3", False),
            ("IS_EMPTY", "SHORT_TEXT", None, "", True),
            ("IS_NOT_EMPTY", "SHORT_TEXT", None, "", False),
        ]
        for operator, kind, expected, value, visible in cases:
            with self.subTest(operator=operator):
                self.version.rules.all().delete()
                source.field_type = kind
                source.save()
                ConditionalRule.objects.create(
                    form_version=self.version,
                    source_field=source,
                    target_field=self.email,
                    operator=operator,
                    expected_value=expected,
                    action="SHOW",
                )
                runtime = PublicResponseForm(
                    FormSchema(self.version),
                    data={
                        "answer_nombre": "Ejemplo",
                        "answer_origen": value,
                    },
                )
                self.assertEqual(runtime.is_valid(), not visible)
                self.assertEqual("answer_correo" in runtime.errors, visible)

    def test_groups_optional_and_hidden_sources(self):
        for group_operator, expects_email in [("AND", False), ("OR", True)]:
            with self.subTest(group=group_operator):
                self.version.rules.all().delete()
                for source, expected in [(self.name, "Ejemplo"), (self.choice, "si")]:
                    ConditionalRule.objects.create(
                        form_version=self.version,
                        source_field=source,
                        target_field=self.email,
                        operator="EQUALS",
                        expected_value=expected,
                        action="SHOW",
                        group_key="contacto",
                        group_operator=group_operator,
                    )
                runtime = PublicResponseForm(
                    FormSchema(self.version),
                    data={
                        "answer_nombre": "Ejemplo",
                        "answer_contactar": "no",
                    },
                )
                self.assertEqual(runtime.is_valid(), not expects_email)
        ConditionalRule.objects.create(
            form_version=self.version,
            source_field=self.choice,
            target_field=self.email,
            operator="EQUALS",
            expected_value="no",
            action="OPTIONAL",
            order=10,
        )
        runtime = PublicResponseForm(
            FormSchema(self.version),
            data={
                "answer_nombre": "Ejemplo",
                "answer_contactar": "no",
            },
        )
        self.assertTrue(runtime.is_valid())
        self.version.rules.all().delete()
        self.email.required = False
        self.email.save()
        ConditionalRule.objects.create(
            form_version=self.version,
            source_field=self.choice,
            target_field=self.email,
            operator="EQUALS",
            expected_value="si",
            action="REQUIRE",
        )
        runtime = PublicResponseForm(
            FormSchema(self.version),
            data={
                "answer_nombre": "Ejemplo",
                "answer_contactar": "si",
            },
        )
        self.assertFalse(runtime.is_valid())
        ConditionalRule.objects.create(
            form_version=self.version,
            source_field=self.name,
            target_field=self.choice,
            operator="IS_NOT_EMPTY",
            action="HIDE",
        )
        runtime = PublicResponseForm(
            FormSchema(self.version),
            data={
                "answer_nombre": "Ejemplo",
                "answer_contactar": "si",
            },
        )
        self.assertTrue(runtime.is_valid())
        self.assertNotIn(self.choice.pk, runtime.answers)


class ResponseAdminTests(TestCase):
    def setUp(self):
        self.form, self.version, name, *_ = fixture()
        self.form = publish_form(self.form.pk)
        self.submission = save_response(
            self.form.pk,
            self.version.pk,
            uuid.uuid4(),
            {name.pk: "<script>alert('sensitive')</script>"},
        )
        self.user = self.form.created_by
        self.user.user_permissions.add(Permission.objects.get(codename="view_submission"))
        self.url = reverse("admin:submissions_submission_change", args=[self.submission.pk])

    def test_responses_require_permission_and_share_legacy_workspaces(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert")
        listing = reverse("admin:submissions_submission_changelist")
        self.assertContains(
            self.client.get(listing, {"q": "sensitive"}), str(self.submission.pk)[:8]
        )
        foreign, *_ = fixture("foreign")
        self.user.workspace = foreign.workspace
        self.user.save()
        self.assertEqual(self.client.get(self.url).status_code, 200)
        response = self.client.get(listing, {"q": "sensitive"})
        self.assertEqual(list(response.context["cl"].queryset), [self.submission])
        response = self.client.get(listing, {"form": self.form.pk})
        self.assertEqual(list(response.context["cl"].queryset), [self.submission])

    def test_read_only_user_cannot_review_and_editor_cannot_forge_response_metadata(self):
        self.client.force_login(self.user)
        review_url = reverse("admin:submissions_submission_review", args=[self.submission.pk])
        data = {"status": "UNDER_REVIEW", "revision": 0}
        self.assertEqual(self.client.post(review_url, data).status_code, 403)
        self.user.user_permissions.add(Permission.objects.get(codename="change_submission"))
        response = self.client.post(review_url, {**data, "form": uuid.uuid4()})
        self.assertEqual(response.status_code, 302)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, "UNDER_REVIEW")
        self.assertEqual(self.submission.form_id, self.form.pk)
        self.assertEqual(self.submission.answers.count(), 1)
        self.assertEqual(self.submission.reviews.get().actor, self.user)
        self.assertEqual(
            self.client.post(
                reverse("admin:submissions_submission_delete", args=[self.submission.pk]),
                {"post": "yes"},
            ).status_code,
            403,
        )


class ConcurrentResponseTests(TransactionTestCase):
    def test_simultaneous_retries_create_one_submission(self):
        form, version, field, *_ = fixture()
        publish_form(form.pk)
        nonce = uuid.uuid4()

        def send(_):
            close_old_connections()
            try:
                return save_response(form.pk, version.pk, nonce, {field.pk: "Concurrente"}).pk
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            ids = list(executor.map(send, range(2)))
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(Submission.objects.count(), 1)
