import csv
import io
import uuid

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.forms.builder import document, save_document
from apps.forms.models import FieldOption, FormField
from apps.forms.publication import publish_form
from apps.forms.response_summary import validate_response_summary
from apps.submissions.models import Submission, SubmissionAnswer, SubmissionFile
from apps.submissions.summary import load_summary_data, summary_for
from apps.submissions.tests.test_public import fixture


class ResponseSummaryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.form, cls.version, cls.name, *_ = fixture()
        cls.user = cls.form.created_by
        cls.user.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="submissions",
                codename__in=["view_submission", "change_submission"],
            )
        )
        cls.doc = FormField.objects.create(
            form_version=cls.version,
            section=cls.name.section,
            label="Número de documento",
            stable_key="documento",
            field_type="SHORT_TEXT",
            order=3,
        )
        cls.eps = FormField.objects.create(
            form_version=cls.version,
            section=cls.name.section,
            label="EPS",
            stable_key="eps",
            field_type="SINGLE_CHOICE",
            order=4,
        )
        FieldOption.objects.create(field=cls.eps, label="Salud de prueba", value="eps_1")
        cls.file_field = FormField.objects.create(
            form_version=cls.version,
            section=cls.name.section,
            label="Soportes",
            stable_key="soportes",
            field_type="FILE",
            order=5,
        )
        cls.submission = Submission.objects.create(
            form=cls.form,
            form_version=cls.version,
            idempotency_key=uuid.uuid4(),
        )
        for field, value in [
            (cls.name, "María Rodríguez"),
            (cls.doc, "1023984521"),
            (cls.eps, "eps_1"),
        ]:
            SubmissionAnswer.objects.create(submission=cls.submission, field=field, value=value)
        answer = SubmissionAnswer.objects.create(submission=cls.submission, field=cls.file_field)
        for i in range(2):
            SubmissionFile.objects.create(
                answer=answer,
                file=f"test/{i}.pdf",
                original_name=f"Soporte {i}.pdf",
                size=10,
            )

    def setUp(self):
        self.client.force_login(self.user)
        self.list_url = reverse("admin:submissions_submission_changelist")

    def summary(self):
        submission = Submission.objects.select_related("form").get(pk=self.submission.pk)
        load_summary_data([submission])
        return summary_for(submission)

    def test_auto_summary_name_masked_document_choice_labels_and_real_files(self):
        summary = self.summary()
        self.assertEqual(summary["title"], "María Rodríguez")
        self.assertEqual(summary["document"], "•••• 4521")
        self.assertEqual(summary["files"], 2)
        self.assertIn("Salud de prueba", [entry["value"] for entry in summary["details"]])
        for view in ("board", "list"):
            response = self.client.get(self.list_url, {"view": view})
            self.assertContains(response, "María Rodríguez")
            self.assertContains(response, "•••• 4521")
            self.assertNotContains(response, "1023984521")
            self.assertContains(response, "2 archivos")

    def test_configured_summary_applies_to_existing_versions_after_save(self):
        publish_form(self.form.pk)
        self.version.refresh_from_db()
        data = document(self.version)
        data["response_summary"] = {
            "title": "eps",
            "fields": [{"key": "documento", "masked": True}],
        }
        saved = save_document(self.form.pk, data)
        self.assertEqual(saved["response_summary"]["title"], "eps")
        self.assertEqual(self.summary()["title"], "Salud de prueba")
        self.assertEqual(len(self.summary()["details"]), 1)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.form_version_id, self.version.pk)
        self.assertEqual(self.submission.answers.get(field=self.doc).value, "1023984521")

    def test_summary_configuration_rejects_duplicates_unknowns_and_too_many_fields(self):
        fields = list(self.version.fields.all())
        invalid = [
            {"title": "missing"},
            {"title": "soportes"},
            {"title": "nombre", "fields": [{"key": "nombre"}]},
            {"fields": [{"key": "documento"}] * 4},
            {"fields": [{"key": "documento", "masked": "false"}]},
            {"fields": [{"key": "missing"}]},
            {"fields": "bad"},
        ]
        for config in invalid:
            with self.subTest(config=config), self.assertRaises(ValidationError):
                validate_response_summary(config, fields)

    def test_missing_identifiers_do_not_use_arbitrary_answers_as_names(self):
        self.submission.answers.filter(field=self.name).delete()
        summary = self.summary()
        self.assertEqual(summary["title"], "Respuesta sin identificación")
        self.assertNotEqual(summary["title"], "Salud de prueba")
        self.form.response_summary = {
            "title": "not_in_old_version",
            "fields": [{"key": "absent", "label": "Orden", "masked": False}],
        }
        self.form.save()
        self.assertEqual(self.summary()["details"][0]["value"], "Sin dato")

    def test_mask_short_document_and_escape_name(self):
        self.submission.answers.filter(field=self.doc).update(value="123")
        self.submission.answers.filter(field=self.name).update(value="<script>test</script>")
        response = self.client.get(self.list_url)
        self.assertContains(response, "&lt;script&gt;test&lt;/script&gt;")
        self.assertNotContains(response, "<script>test</script>")
        self.assertEqual(self.summary()["document"], "•••")

    def test_summary_query_count_does_not_grow_per_card(self):
        for _ in range(8):
            item = Submission.objects.create(
                form=self.form, form_version=self.version, idempotency_key=uuid.uuid4()
            )
            SubmissionAnswer.objects.create(submission=item, field=self.name, value="Otra persona")
        submissions = list(Submission.objects.select_related("form"))
        with self.assertNumQueries(3):
            load_summary_data(submissions)
            summaries = [summary_for(item) for item in submissions]
        self.assertEqual(len(summaries), 9)

    def test_flags_require_detail_and_permission_and_are_audited(self):
        url = reverse("admin:submissions_submission_attention", args=[self.submission.pk])
        self.assertEqual(
            self.client.post(url, {"attention": "ILLEGIBLE", "revision": 0}).status_code, 422
        )
        response = self.client.post(
            url, {"attention": "ILLEGIBLE", "attention_note": "No se lee el soporte", "revision": 0}
        )
        self.assertEqual(response.status_code, 302)
        self.assertContains(self.client.get(self.list_url), "Documento ilegible")
        self.assertEqual(self.submission.reviews.count(), 1)
        self.assertEqual(self.client.post(url, {"attention": "", "revision": 0}).status_code, 409)
        self.assertEqual(self.client.post(url, {"attention": "", "revision": 1}).status_code, 302)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.attention_note, "")
        self.assertEqual(self.submission.status, "SUBMITTED")
        self.user.user_permissions.remove(Permission.objects.get(codename="change_submission"))
        self.assertEqual(self.client.post(url, {"attention": "", "revision": 2}).status_code, 403)

    def test_download_contains_answers_and_protects_csv_formulas(self):
        self.submission.answers.filter(field=self.name).update(value="=HYPERLINK(1)")
        url = reverse("admin:submissions_submission_download", args=[self.submission.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(rows[1][-1], "'=HYPERLINK(1)")
        self.assertTrue(any(row[-1] == "1023984521" for row in rows))
        self.assertTrue(any("Soporte 0.pdf" in row[-1] for row in rows))
        self.user.user_permissions.clear()
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_selection_export_does_not_expand_to_other_responses(self):
        other = Submission.objects.create(
            form=self.form, form_version=self.version, idempotency_key=uuid.uuid4()
        )
        url = reverse("admin:submissions_submission_download_selected")
        response = self.client.post(url, {"selected": [self.submission.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(str(other.pk), response.content.decode("utf-8"))
        for selected in ([], ["bad"], [uuid.uuid4()]):
            self.assertEqual(self.client.post(url, {"selected": selected}).status_code, 400)
