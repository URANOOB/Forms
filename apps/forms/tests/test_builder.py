import copy
import io
import tempfile
import uuid

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.accounts.models import User, Workspace
from apps.forms.builder import StaleDraft, current_version, document, save_document
from apps.forms.conditions import FormSchema
from apps.forms.models import Form, FormImage, FormVersion
from apps.forms.presets import create_preset_fields
from apps.forms.publication import publish_form
from apps.submissions.runtime import PublicResponseForm, save_response


class BuilderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Institución", slug="builder-tests")
        cls.user = User.objects.create_user(
            username="editor", is_staff=True, workspace=cls.workspace
        )
        cls.user.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="forms", codename__in=["view_form", "change_form"]
            )
        )
        cls.form = Form.objects.create(
            name="Contacto original", slug="contacto", workspace=cls.workspace, created_by=cls.user
        )
        cls.version = FormVersion.objects.create(form=cls.form, version_number=1)
        create_preset_fields(cls.version, "contact")

    def setUp(self):
        self.client.force_login(self.user)

    def url(self, operation="edit", form=None):
        return reverse(f"admin:forms_form_builder_{operation}", args=[(form or self.form).pk])

    def test_get_is_read_only_and_preview_does_not_accept_submissions(self):
        publish_form(self.form.pk)
        self.assertContains(self.client.get(self.url()), "Constructor de formularios")
        self.assertEqual(self.form.versions.count(), 1)
        self.assertContains(self.client.get(self.url("preview")), "Las respuestas no se guardarán")
        self.assertEqual(self.client.post(self.url("preview"), {}).status_code, 405)
        self.assertEqual(self.client.get(self.url("save")).status_code, 405)

    def test_edit_published_creates_draft_and_preserves_answers_and_public_schema(self):
        form = publish_form(self.form.pk)
        old_field = form.active_version.fields.get(stable_key="nombre")
        submission = save_response(
            form.pk, form.active_version_id, uuid.uuid4(), {old_field.pk: "Ana"}
        )
        data = document(form.active_version)
        data["title"] = "Nuevo título"
        data["sections"][0]["fields"][0]["label"] = "Nuevo nombre"
        result = save_document(form.pk, data)
        form.refresh_from_db()
        self.assertEqual(form.active_version_id, self.version.pk)
        self.assertEqual(form.name, "Contacto original")
        self.assertEqual(result["number"], 2)
        self.assertEqual(submission.answers.get().field.label, old_field.label)
        self.assertEqual(submission.answers.get().value, "Ana")
        self.assertContains(self.client.get(form.get_absolute_url()), "Contacto original")
        self.assertNotContains(self.client.get(form.get_absolute_url()), "Nuevo título")
        result = save_document(form.pk, result, publish=True)
        form.refresh_from_db()
        self.assertEqual(form.active_version.version_number, 2)
        self.assertEqual(form.name, "Nuevo título")
        self.assertEqual(result["status"], "PUBLISHED")
        self.assertEqual(submission.answers.get().value, "Ana")

    def test_stale_save_and_technical_edits_are_rejected(self):
        data = document(self.version)
        save_document(self.form.pk, data)
        with self.assertRaises(StaleDraft):
            save_document(self.form.pk, data)
        response = self.client.post(self.url("save"), data, content_type="application/json")
        self.assertEqual(response.status_code, 409)
        fresh = document(current_version(self.form))
        field = self.version.fields.first()
        field.label = "Edición desde administración"
        field.save()
        with self.assertRaises(StaleDraft):
            save_document(self.form.pk, fresh)

    def test_chained_conditions_across_sections_and_hidden_required_answers(self):
        data = document(self.version)
        fields = data["sections"][0]["fields"]
        fields[0].update(field_type="BOOLEAN", configuration={})
        fields[1].update(
            field_type="SINGLE_CHOICE",
            configuration={"widget": "radio"},
            options=[{"label": "Equipo A", "value": "a"}, {"label": "Equipo B", "value": "b"}],
        )
        second = {"id": "second", "title": "Detalles del equipo A", "fields": fields[2:]}
        fields[2]["required"] = True
        data["sections"][0]["fields"] = fields[:2]
        data["sections"].append(second)
        data["rules"] = [
            {
                "source": fields[0]["id"],
                "operator": "EQUALS",
                "expected": True,
                "action": "SHOW",
                "target_field": fields[1]["id"],
            },
            {
                "source": fields[1]["id"],
                "operator": "EQUALS",
                "expected": "a",
                "action": "SHOW",
                "target_section": "second",
            },
        ]
        result = save_document(self.form.pk, data, publish=True)
        version = FormVersion.objects.get(pk=result["version"])
        schema = FormSchema(version)
        hidden = PublicResponseForm(
            schema,
            data={"answer_nombre": "false", "answer_correo": "a", "answer_telefono": "invalid"},
        )
        self.assertTrue(hidden.is_valid(), hidden.errors)
        self.assertEqual(len(hidden.answers), 1)
        visible = PublicResponseForm(schema, data={"answer_nombre": "true", "answer_correo": "a"})
        self.assertFalse(visible.is_valid())
        self.assertIn("answer_telefono", visible.errors)

    def test_nested_answer_branches_require_both_section_and_question_conditions(self):
        data = document(self.version)
        a, b, c, d = data["sections"][0]["fields"]
        a.update(field_type="BOOLEAN", configuration={})
        b.update(field_type="BOOLEAN", configuration={})
        data["sections"][0]["fields"] = [a, b]
        data["sections"].append({"id": "details", "title": "Detalles", "fields": [c, d]})
        data["rules"] = [
            {
                "source": a["id"],
                "operator": "EQUALS",
                "expected": True,
                "action": "SHOW",
                "target_section": "details",
            },
            {
                "source": b["id"],
                "operator": "EQUALS",
                "expected": False,
                "action": "SHOW",
                "target_field": c["id"],
            },
        ]
        result = save_document(self.form.pk, data)
        schema = FormSchema(FormVersion.objects.get(pk=result["version"]))
        keys = {field.stable_key: str(field.pk) for field in schema.fields}
        for show_section, answer, expected_visible in [
            (False, False, False),
            (True, True, False),
            (True, False, True),
        ]:
            with self.subTest(show_section=show_section, answer=answer):
                states = schema.states(
                    {keys[a["stable_key"]]: show_section, keys[b["stable_key"]]: answer}
                )
                self.assertEqual(states[keys[c["stable_key"]]]["visible"], expected_visible)

    def test_invalid_cycle_rolls_back_entire_draft(self):
        data = document(self.version)
        original = copy.deepcopy(data)
        a, b = data["sections"][0]["fields"][:2]
        data["title"] = "No debe guardarse"
        data["rules"] = [
            {
                "source": a["id"],
                "operator": "IS_NOT_EMPTY",
                "action": "SHOW",
                "target_field": b["id"],
            },
            {
                "source": b["id"],
                "operator": "IS_NOT_EMPTY",
                "action": "SHOW",
                "target_field": a["id"],
            },
        ]
        with self.assertRaisesMessage(ValidationError, "ciclo"):
            save_document(self.form.pk, data)
        self.version.refresh_from_db()
        self.assertEqual(document(self.version), original)

    def test_editor_requires_workspace_change_permission_and_csrf(self):
        other = Workspace.objects.create(name="Otro", slug="otro")
        foreign = Form.objects.create(
            name="Ajeno", slug="ajeno", workspace=other, created_by=self.user
        )
        self.assertEqual(self.client.get(self.url(form=foreign)).status_code, 404)
        self.assertEqual(
            self.client.post(
                self.url("save", foreign), {}, content_type="application/json"
            ).status_code,
            404,
        )
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(
            csrf_client.post(self.url("save"), {}, content_type="application/json").status_code, 403
        )
        self.user.user_permissions.remove(
            Permission.objects.get(content_type__app_label="forms", codename="change_form")
        )
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.assertEqual(self.client.post(self.url("image"), {}).status_code, 403)

    def test_images_are_checked_and_private_until_referenced_in_published_version(self):
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            invalid = SimpleUploadedFile(
                "bad.png", b"<svg onload='alert(1)'/>", content_type="image/png"
            )
            self.assertEqual(
                self.client.post(self.url("image"), {"image": invalid}).status_code, 400
            )
            buffer = io.BytesIO()
            Image.new("RGB", (32, 32), "blue").save(buffer, format="PNG")
            upload = SimpleUploadedFile("image.png", buffer.getvalue(), content_type="image/png")
            response = self.client.post(self.url("image"), {"image": upload})
            self.assertEqual(response.status_code, 200)
            image = response.json()
            anon = Client()
            self.assertEqual(anon.get(image["url"]).status_code, 404)
            private = self.client.get(image["url"])
            self.assertEqual(private.status_code, 200)
            self.assertTrue(b"".join(private.streaming_content))
            data = document(self.version)
            data["sections"][0]["fields"][0]["image"] = image["id"]
            save_document(self.form.pk, data, publish=True)
            public = anon.get(image["url"])
            self.assertEqual(public.status_code, 200)
            self.assertEqual(public["Content-Type"], "image/png")
            self.assertTrue(b"".join(public.streaming_content))
            other = Form.objects.create(
                name="Otro", slug="otro", workspace=self.workspace, created_by=self.user
            )
            foreign_image = FormImage.objects.create(form=other, file="irrelevant.png")
            self.form.refresh_from_db()
            data = document(current_version(self.form))
            data["sections"][0]["fields"][0]["image"] = str(foreign_image.pk)
            with self.assertRaisesMessage(ValidationError, "no pertenece"):
                save_document(self.form.pk, data)
            self.assertEqual(self.form.versions.count(), 1)
