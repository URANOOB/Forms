import uuid
from types import SimpleNamespace

from django.contrib.auth.models import Permission
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.forms.models import FieldOption, FormField, FormSection
from apps.submissions.models import Submission, SubmissionAnswer, SubmissionFile
from apps.submissions.presentation import display_value, render_response_details, response_sections
from apps.submissions.tests.test_public import fixture


class ValuePresentationTests(SimpleTestCase):
    def test_display_formats_preserve_significant_characters_and_unknown_values(self):
        cases = [
            ("DATE", "Fecha", "2026-09-19", "19 sep 2026"),
            ("DATE", "Fecha", "fecha inválida", "fecha inválida"),
            ("NUMBER", "Número de documento", 1312441240.0, "1.312.441.240"),
            ("SHORT_TEXT", "Documento", "0012345", "0.012.345"),
            ("SHORT_TEXT", "Documento", "AB-12345", "AB-12345"),
            ("SHORT_TEXT", "Teléfono actualizado", "3101234567", "310 123 4567"),
            ("PHONE", "Contacto", "+573101234567", "+573 101 234 567"),
            ("PHONE", "Contacto", "6011234567 ext. 21", "6011234567 ext. 21"),
            ("NUMBER", "Cantidad", 0, "0"),
            ("NUMBER", "Medición", 1.25, "1.25"),
        ]
        for kind, label, raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(
                    display_value(SimpleNamespace(field_type=kind, label=label), raw, str(raw)),
                    expected,
                )

    def test_option_labels_are_not_replaced_by_identifier_values(self):
        field = SimpleNamespace(field_type="SINGLE_CHOICE", label="Documento")
        self.assertEqual(display_value(field, "123456", "Pasaporte"), "Pasaporte")


class ResponsePresentationTests(TestCase):
    def setUp(self):
        self.form, self.version, self.name, self.choice, _ = fixture()
        self.response = Submission.objects.create(
            form=self.form, form_version=self.version, idempotency_key=uuid.uuid4()
        )
        self.name.section.title = "Sección 1"
        self.name.section.save()
        SubmissionAnswer.objects.create(submission=self.response, field=self.name, value="María")

    def add_answer(self, label, kind, value, section=None, **kwargs):
        field = FormField.objects.create(
            form_version=self.version,
            section=section or self.name.section,
            label=label,
            stable_key="field_" + uuid.uuid4().hex,
            field_type=kind,
            **kwargs,
        )
        return SubmissionAnswer.objects.create(submission=self.response, field=field, value=value)

    def test_layout_types_empty_false_zero_and_raw_values(self):
        self.add_answer("Fecha de nacimiento", "DATE", "2026-09-19")
        self.add_answer("Documento", "NUMBER", 1312441240.0)
        self.add_answer("Teléfono", "SHORT_TEXT", "3101234567")
        self.add_answer("Dirección actualizada", "SHORT_TEXT", "Carrera 123 # 45-67")
        self.add_answer("Observaciones", "LONG_TEXT", "Primera línea\nSegunda línea")
        self.add_answer("Disponible", "BOOLEAN", False)
        self.add_answer("Cantidad", "NUMBER", 0)
        self.add_answer("Correo alternativo", "EMAIL", None)
        before = list(self.response.answers.order_by("pk").values_list("pk", "value"))
        section = response_sections(self.response)[0]
        self.assertEqual(section["title"], "Datos del solicitante")
        answers = {answer["label"]: answer for answer in section["answers"]}
        self.assertEqual(answers["Fecha de nacimiento"]["value"], "19 sep 2026")
        self.assertEqual(answers["Documento"]["value"], "1.312.441.240")
        self.assertEqual(answers["Teléfono"]["value"], "310 123 4567")
        self.assertTrue(answers["Dirección actualizada"]["wide"])
        self.assertTrue(answers["Observaciones"]["wide"])
        self.assertEqual(answers["Disponible"]["value"], "No")
        self.assertFalse(answers["Disponible"]["empty"])
        self.assertFalse(answers["Cantidad"]["empty"])
        self.assertTrue(answers["Correo alternativo"]["empty"])
        self.assertEqual(
            before, list(self.response.answers.order_by("pk").values_list("pk", "value"))
        )
        self.name.section.refresh_from_db()
        self.assertEqual(self.name.section.title, "Sección 1")

    def test_choices_grids_attachments_and_html_escaping(self):
        SubmissionAnswer.objects.create(
            submission=self.response,
            field=self.choice,
            value={"selected": "si", "text": "Explicación"},
        )
        choice = self.add_answer("Diagnóstico", "SINGLE_CHOICE", "confirmed")
        FieldOption.objects.create(field=choice.field, value="confirmed", label="Confirmado")
        grid = self.add_answer(
            "Cuadrícula",
            "GRID_SINGLE",
            {"r": "c"},
            configuration={
                "rows": [{"id": "r", "label": "Fila"}],
                "columns": [{"id": "c", "label": "Columna"}],
            },
        )
        self.add_answer("Texto", "SHORT_TEXT", '<script>alert("x")</script>')
        docs = FormSection.objects.create(form_version=self.version, title="Sección 2", order=2)
        upload = self.add_answer("Adjuntos", "DOCUMENT", [], section=docs)
        file = SubmissionFile.objects.create(
            answer=upload, file="fake/report.pdf", original_name="Reporte.pdf", size=100
        )
        sections = response_sections(self.response)
        answers = {answer["label"]: answer for answer in sections[0]["answers"]}
        self.assertEqual(answers[self.choice.label]["value"], "Sí: Explicación")
        self.assertEqual(answers["Diagnóstico"]["kind"], "status")
        self.assertEqual(answers[grid.field.label]["value"], "Fila: Columna")
        self.assertEqual(sections[1]["title"], "Documentos")
        self.assertEqual(sections[1]["file_count"], 1)
        self.assertFalse(sections[1]["answers"][0]["empty"])
        html = render_response_details(sections)
        self.assertIn(file.get_absolute_url(), html)
        self.assertIn('data-document-kind="pdf"', html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)

    def test_section_titles_preserved_and_anchors_unique_between_responses(self):
        self.name.section.title = "Datos del representante"
        self.name.section.save()
        section = response_sections(self.response)[0]
        self.assertEqual(section["title"], "Datos del representante")
        another = Submission.objects.create(
            form=self.form, form_version=self.version, idempotency_key=uuid.uuid4()
        )
        SubmissionAnswer.objects.create(submission=another, field=self.name, value="Otra persona")
        self.assertNotEqual(section["id"], response_sections(another)[0]["id"])

    def test_detail_respects_permissions_and_uses_version_title(self):
        user = self.form.created_by
        user.user_permissions.add(Permission.objects.get(codename="view_submission"))
        self.version.title = "Título de la versión recibida"
        self.version.save()
        self.client.force_login(user)
        url = reverse("admin:submissions_submission_detail", args=[self.response.pk])
        detail = self.client.get(url)
        self.assertContains(detail, self.version.title)
        self.assertNotContains(detail, "data-review-form")
        self.assertNotContains(detail, "Eliminar respuesta")
        self.assertNotContains(detail, "Ver versión 1")
        self.assertContains(detail, "Descargar respuesta (CSV)")
        user.user_permissions.add(
            *Permission.objects.filter(
                codename__in=["change_submission", "delete_submission", "view_formversion"]
            )
        )
        detail = self.client.get(url)
        self.assertContains(detail, "Ver versión 1")
        self.assertContains(detail, "Eliminar respuesta")
        self.assertContains(detail, ">Iniciar revisión</button>")
        self.response.status = Submission.Status.UNDER_REVIEW
        self.response.save()
        invalid = self.client.post(
            reverse("admin:submissions_submission_review", args=[self.response.pk]),
            {"status": "REJECTED", "note": "", "revision": 0},
        )
        self.assertEqual(invalid.status_code, 422)
        self.assertContains(invalid, 'review-danger">Rechazar respuesta</button>', status_code=422)
        self.assertContains(invalid, "Indica el motivo del rechazo.", status_code=422)
