import io
import uuid
from unittest.mock import patch

from django.conf import settings
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.files.storage import InMemoryStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from openpyxl import load_workbook

from apps.accounts.models import User
from apps.forms.builder import document, save_document
from apps.forms.conditions import FormSchema
from apps.forms.models import ConditionalRule, FormField, FormSection
from apps.forms.publication import publish_form, set_form_status, unarchive_form
from apps.submissions.admin_views import fingerprint
from apps.submissions.duplicates import duplicates_for, normalized_identity
from apps.submissions.models import (
    PendingFileDeletion,
    Submission,
    SubmissionAnswer,
    SubmissionFile,
)
from apps.submissions.runtime import new_token, read_token, save_response
from apps.submissions.tests.test_public import fixture


class SeptemberAuditTests(TestCase):
    def setUp(self):
        self.form, self.version, self.name, *_ = fixture()
        self.storage = InMemoryStorage()
        self.storage_patch = patch.object(
            SubmissionFile._meta.get_field("file"), "storage", self.storage
        )
        self.storage_patch.start()
        self.addCleanup(self.storage_patch.stop)

    def field(self, key, kind, **kwargs):
        return FormField.objects.create(
            form_version=self.version,
            section=self.name.section,
            stable_key=key,
            label=key,
            field_type=kind,
            **kwargs,
        )

    def publish(self):
        self.form = publish_form(self.form.pk)
        self.version.refresh_from_db()

    def send(self, **values):
        return self.client.post(
            self.form.get_absolute_url(),
            {
                "submission_token": new_token(self.form),
                "answer_nombre": "Ana",
                **values,
            },
            HTTP_ACCEPT="application/json",
        )

    def test_six_full_grids_and_105_files_reach_real_multipart_parser(self):
        values = {}
        rows = [{"id": f"r{i}", "label": f"Fila {i}"} for i in range(20)]
        columns = [{"id": f"c{i}", "label": f"Columna {i}"} for i in range(10)]
        for i in range(6):
            self.field(
                f"grid{i}", "GRID_MULTIPLE", configuration={"rows": rows, "columns": columns}
            )
            for row in rows:
                values[f"answer_grid{i}__{row['id']}"] = [c["id"] for c in columns]
        for i in range(21):
            self.field(f"file{i}", "FILE", configuration={"max_files": 5, "extensions": ["txt"]})
            values[f"answer_file{i}"] = [SimpleUploadedFile(f"{j}.txt", b"hi") for j in range(5)]
        self.publish()
        result = self.send(**values)
        self.assertEqual(result.status_code, 200, result.content)
        self.assertTrue(result.json()["received"])
        self.assertEqual(SubmissionFile.objects.count(), 105)

    def test_parser_boundaries_and_recoverable_errors_before_csrf(self):
        self.publish()
        # Repeated parameters count individually, not merely distinct names.
        at_limit = {"unused": ["x"] * (settings.DATA_UPLOAD_MAX_NUMBER_FIELDS - 2)}
        self.assertEqual(self.send(**at_limit).status_code, 200)
        beyond = {"unused": ["x"] * settings.DATA_UPLOAD_MAX_NUMBER_FIELDS}
        response = self.send(**beyond)
        self.assertEqual(response.status_code, 400)
        self.assertIn("tus datos", response.json()["message"])
        for count, expected in [
            (settings.DATA_UPLOAD_MAX_NUMBER_FILES, 200),
            (settings.DATA_UPLOAD_MAX_NUMBER_FILES + 1, 400),
        ]:
            result = self.send(unused=[SimpleUploadedFile(f"{i}.txt", b"x") for i in range(count)])
            self.assertEqual(result.status_code, expected, result.content)
        csrf = Client(enforce_csrf_checks=True)
        response = csrf.post(self.form.get_absolute_url(), beyond, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 403)  # exactly limit parses, CSRF still applies
        beyond["extra"] = "x"
        response = csrf.post(self.form.get_absolute_url(), beyond, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("message", response.json())

    @override_settings(DATA_UPLOAD_MAX_NUMBER_FILES=4)
    def test_budget_rejected_on_save_and_publish(self):
        data = document(self.version)
        data["sections"][0]["fields"].append(
            {
                "id": "files",
                "stable_key": "files",
                "label": "Files",
                "field_type": "FILE",
                "configuration": {"max_files": 5},
            }
        )
        with self.assertRaisesMessage(ValidationError, "archivos en total"):
            save_document(self.form.pk, data)
        self.assertFalse(self.version.fields.filter(stable_key="files").exists())
        self.field("files", "FILE", configuration={"max_files": 5})
        with self.assertRaisesMessage(ValidationError, "archivos en total"):
            self.publish()

    def test_impossible_domains_rejected(self):
        cases = [
            ("NUMBER", {"min_value": 0.1, "max_value": 0.9}),
            ("NUMBER", {"max_value": -1}),
            ("NUMBER", {"min_value": 2**53}),
            ("PHONE", {"min_length": 26}),
            ("PHONE", {"max_length": 5}),
            ("EMAIL", {"min_length": 321}),
            ("EMAIL", {"max_length": 2}),
        ]
        for kind, validation in cases:
            with self.subTest(kind=kind, validation=validation):
                field = self.field("invalid", kind, validation=validation)
                with self.assertRaises(ValidationError):
                    FormSchema(self.version)
                with self.assertRaises(ValidationError):
                    self.publish()
                field.delete()
        field = self.field("valid", "NUMBER", validation={"min_value": 0.1, "max_value": 1.1})
        self.assertEqual(FormSchema(self.version).inputs[str(field.pk)].clean("1"), 1)

    def test_historical_budget_allows_read_and_small_submission(self):
        for i in range(41):
            self.field(f"file{i}", "FILE", configuration={"max_files": 5, "extensions": ["txt"]})
        with override_settings(DATA_UPLOAD_MAX_NUMBER_FILES=1000):
            self.publish()
        self.assertEqual(self.client.get(self.form.get_absolute_url()).status_code, 200)
        self.assertEqual(self.send().status_code, 200)
        self.assertEqual(
            self.send(answer_file0=SimpleUploadedFile("one.txt", b"x")).status_code, 200
        )
        self.assertEqual(SubmissionFile.objects.count(), 1)
        self.assertEqual(
            self.send(
                unused=[SimpleUploadedFile(f"{i}.txt", b"x") for i in range(201)]
            ).status_code,
            400,
        )
        with self.assertRaisesMessage(ValidationError, "archivos en total"):
            save_document(self.form.pk, document(self.version))

    def test_fork_issues_distinct_signed_identities_and_keeps_retry_identity(self):
        self.publish()
        fork = {"submission_action": "fork", "submission_version": str(self.version.pk)}
        tokens = [
            self.client.post(self.form.get_absolute_url(), fork).json()["token"] for _ in range(3)
        ]
        self.assertEqual(len({read_token(token, self.form) for token in tokens}), 3)
        self.assertEqual(
            self.client.post(
                self.form.get_absolute_url(),
                {
                    **fork,
                    "submission_version": str(uuid.uuid4()),
                },
            ).status_code,
            409,
        )
        result = self.client.post(
            self.form.get_absolute_url(),
            {
                "submission_action": "recover",
                "submission_token": tokens[0],
            },
        )
        self.assertEqual(
            read_token(result.json()["token"], self.form), read_token(tokens[0], self.form)
        )
        csrf = Client(enforce_csrf_checks=True)
        self.assertEqual(
            csrf.post(self.form.get_absolute_url(), {"submission_action": "fork"}).status_code, 403
        )
        set_form_status(self.form.pk, "PAUSED")
        self.assertEqual(
            self.client.post(
                self.form.get_absolute_url(), {"submission_action": "fork"}
            ).status_code,
            409,
        )

    def test_backward_condition_rejected_on_save_and_publish(self):
        second = FormSection.objects.create(form_version=self.version, title="Decisión", order=1)
        for field in self.version.fields.exclude(pk=self.name.pk):
            field.section = second
            field.save()
        data = document(self.version)
        choice = self.version.fields.get(stable_key="contactar")
        data["rules"].append(
            {
                "source": str(choice.pk),
                "target_section": str(self.name.section_id),
                "operator": "EQUALS",
                "expected": "si",
                "action": "SHOW",
            }
        )
        with self.assertRaisesMessage(ValidationError, "alcanzable"):
            save_document(self.form.pk, data)
        ConditionalRule.objects.create(
            form_version=self.version,
            source_field=choice,
            target_section=self.name.section,
            operator="EQUALS",
            expected_value="si",
            action="SHOW",
        )
        with self.assertRaisesMessage(ValidationError, "alcanzable"):
            self.publish()

    def test_forward_condition_destination_must_follow_actual_navigation(self):
        second = FormSection.objects.create(form_version=self.version, title="Destino", order=1)
        field = self.field("destination", "SHORT_TEXT", required=True)
        field.section = second
        field.save()
        ConditionalRule.objects.create(
            form_version=self.version,
            source_field=self.name,
            target_section=second,
            operator="IS_NOT_EMPTY",
            action="SHOW",
        )
        schema = FormSchema(self.version)
        path, states = schema.journey({str(self.name.pk): "Ana"})
        self.assertIn(str(second.pk), path)
        self.assertTrue(states[str(field.pk)]["required"])
        first = self.name.section
        first.configuration = {"next_section": "SUBMIT"}
        first.save()
        with self.assertRaisesMessage(ValidationError, "alcanzable"):
            self.publish()

    def test_historical_float_identity_matches_integral_number(self):
        field = self.field("documento", "NUMBER")
        self.form.duplicate_fields = ["documento"]
        self.form.save(update_fields=["duplicate_fields"])
        self.publish()
        old = Submission.objects.create(
            form=self.form, form_version=self.version, idempotency_key=uuid.uuid4()
        )
        SubmissionAnswer.objects.create(submission=old, field=field, value=12345.0)
        new = save_response(self.form.pk, self.version.pk, uuid.uuid4(), {field.pk: 12345})
        self.assertEqual(list(duplicates_for(new)), [old])
        self.assertEqual(new.attention, "DUPLICATE")
        for value in (float("nan"), float("inf"), 12345.5, True):
            self.assertEqual(normalized_identity(value, "NUMBER"), "")

    def test_grid_csv_excel_and_detail_keep_historical_labels(self):
        configuration = {
            "rows": [{"id": "row-id", "label": "Calidad"}],
            "columns": [{"id": "col-id", "label": "Excelente"}],
        }
        single = self.field("single", "GRID_SINGLE", configuration=configuration)
        multi = self.field("multi", "GRID_MULTIPLE", configuration=configuration)
        self.publish()
        submission = save_response(
            self.form.pk,
            self.version.pk,
            uuid.uuid4(),
            {
                single.pk: {"row-id": "col-id"},
                multi.pk: {"row-id": ["col-id"]},
            },
        )
        data = document(self.version)
        for field in data["sections"][0]["fields"]:
            if field["field_type"].startswith("GRID"):
                field["configuration"]["columns"][0]["label"] = "Etiqueta nueva"
        save_document(self.form.pk, data)
        admin = User.objects.create_superuser(username="admin")
        self.client.force_login(admin)
        for route in ("download", "detail"):
            response = self.client.get(
                reverse(f"admin:submissions_submission_{route}", args=[submission.pk])
            )
            self.assertContains(response, "Calidad: Excelente", count=2)
            self.assertNotContains(response, "Etiqueta nueva")
        result = self.client.get(reverse("admin:submissions_submission_report_excel"))
        workbook = load_workbook(io.BytesIO(b"".join(result.streaming_content)))
        self.addCleanup(workbook.close)
        values = [cell.value for row in workbook["Respuestas"] for cell in row]
        self.assertEqual(values.count("Calidad: Excelente"), 2)

    def test_edit_deletion_failure_leaves_retry_and_other_files_are_attempted(self):
        field = self.field("files", "FILE", configuration={"max_files": 2})
        self.publish()
        submission = save_response(
            self.form.pk,
            self.version.pk,
            uuid.uuid4(),
            {
                self.name.pk: "Ana",
                field.pk: [SimpleUploadedFile("a.txt", b"a"), SimpleUploadedFile("b.txt", b"b")],
            },
        )
        files = list(SubmissionFile.objects.all())
        self.client.force_login(User.objects.create_superuser(username="admin"))
        with (
            patch.object(self.storage, "delete", side_effect=OSError("offline")) as delete,
            self.assertLogs("apps.submissions.file_cleanup", level="ERROR"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                reverse("admin:submissions_submission_edit", args=[submission.pk]),
                {
                    "revision": fingerprint(submission),
                    "answer_nombre": "Ana",
                    "remove_files": [str(file.pk) for file in files],
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(delete.call_count, 2)
        self.assertEqual(PendingFileDeletion.objects.count(), 2)
        self.assertFalse(SubmissionFile.objects.exists())
        call_command("retry_file_deletions", stdout=io.StringIO())
        self.assertFalse(PendingFileDeletion.objects.exists())
        self.assertFalse(any(self.storage.exists(file.file.name) for file in files))

    def test_rollback_cleanup_survives_and_continues_after_storage_failure(self):
        field = self.field("files", "FILE", configuration={"max_files": 2})
        self.publish()
        with (
            patch(
                "apps.submissions.duplicates.flag_duplicate", side_effect=RuntimeError("rollback")
            ),
            patch.object(self.storage, "delete", side_effect=OSError("offline")) as delete,
            self.assertLogs("apps.submissions.file_cleanup", level="ERROR"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            with self.assertRaisesMessage(RuntimeError, "rollback"):
                save_response(
                    self.form.pk,
                    self.version.pk,
                    uuid.uuid4(),
                    {
                        field.pk: [
                            SimpleUploadedFile("a.txt", b"a"),
                            SimpleUploadedFile("b.txt", b"b"),
                        ],
                    },
                )
        self.assertFalse(Submission.objects.exists())
        self.assertEqual(delete.call_count, 2)
        self.assertEqual(PendingFileDeletion.objects.count(), 2)

    def test_edit_rollback_keeps_original_file_and_queues_only_new_upload(self):
        field = self.field("files", "FILE", configuration={"max_files": 2})
        self.publish()
        submission = save_response(
            self.form.pk,
            self.version.pk,
            uuid.uuid4(),
            {
                self.name.pk: "Ana",
                field.pk: [SimpleUploadedFile("old.txt", b"old")],
            },
        )
        original = SubmissionFile.objects.get()
        self.client.force_login(User.objects.create_superuser(username="admin"))
        with (
            patch.object(
                admin.site._registry[Submission], "log_change", side_effect=RuntimeError("rollback")
            ),
            patch.object(self.storage, "delete", side_effect=OSError("offline")),
            self.assertLogs("apps.submissions.file_cleanup", level="ERROR"),
        ):
            with self.assertRaisesMessage(RuntimeError, "rollback"):
                self.client.post(
                    reverse("admin:submissions_submission_edit", args=[submission.pk]),
                    {
                        "revision": fingerprint(submission),
                        "answer_nombre": "Ana",
                        "remove_files": [str(original.pk)],
                        "answer_files": SimpleUploadedFile("new.txt", b"new"),
                    },
                )
        self.assertEqual(SubmissionFile.objects.get().pk, original.pk)
        task = PendingFileDeletion.objects.get()
        self.assertNotEqual(task.name, original.file.name)
        call_command("retry_file_deletions", stdout=io.StringIO())
        self.assertTrue(self.storage.exists(original.file.name))
        self.assertFalse(self.storage.exists(task.name))

    def test_unarchive_returns_draft_and_logs_action_without_opening_public_link(self):
        self.publish()
        set_form_status(self.form.pk, "ARCHIVED")
        self.client.force_login(User.objects.create_superuser(username="admin"))
        url = reverse("admin:forms_form_changelist")
        self.assertContains(self.client.get(url), "Desarchivar como borrador")
        result = self.client.post(
            url, {"action": "unarchive_forms", "_selected_action": str(self.form.pk)}
        )
        self.assertEqual(result.status_code, 302)
        self.form.refresh_from_db()
        self.assertEqual(self.form.status, "DRAFT")
        self.assertEqual(self.client.get(self.form.get_absolute_url()).status_code, 404)
        self.assertTrue(self.form.active_version_id)
        with self.assertRaises(ValidationError):
            unarchive_form(self.form.pk)
