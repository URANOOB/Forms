import tempfile
import uuid
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.files.storage import FileSystemStorage
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.dashboard import dashboard_callback, trend_context
from apps.accounts.infrastructure import database_info, files_info, infrastructure_info
from apps.forms.models import Form, FormVersion
from apps.submissions.models import Submission, SubmissionAnswer, SubmissionFile, SubmissionReview
from apps.submissions.tests.test_public import fixture


class DashboardTests(TestCase):
    def setUp(self):
        self.form, self.version, self.name, *_ = fixture()
        self.user = self.form.created_by
        self.user.user_permissions.add(Permission.objects.get(codename="view_submission"))
        self.now = timezone.make_aware(datetime(2026, 9, 23, 12))
        cache.clear()

    def submission(self, status="SUBMITTED", days=0, **kwargs):
        return Submission.objects.create(
            form=kwargs.pop("form", self.form),
            form_version=kwargs.pop("form_version", self.version),
            status=status,
            idempotency_key=uuid.uuid4(),
            submitted_at=self.now - timedelta(days=days),
            **kwargs,
        )

    def context(self, period="7d", **params):
        request = RequestFactory().get(reverse("admin:index"), {"period": period, **params})
        request.user = self.user
        with patch("apps.accounts.dashboard.timezone.now", return_value=self.now):
            return dashboard_callback(request, {})

    def test_status_metrics_and_table_use_the_selected_received_cohort(self):
        for status in Submission.Status.values:
            self.submission(status, days=2)
        self.submission(days=0)
        self.submission(days=8)
        self.submission(days=40)
        self.submission(days=-1)
        data = self.context()
        values = {card["status"]: card["value"] for card in data["dashboard_cards"]}
        self.assertEqual(
            values,
            {
                "SUBMITTED": 2,
                "received_today": 1,
                "UNDER_REVIEW": 1,
                "VALIDATED": 1,
                "REJECTED": 1,
            },
        )
        self.assertEqual(data["dashboard_trend"]["total"], 5)
        self.assertEqual(data["dashboard_cards"][3]["note"], "20,0 % del total")
        self.assertEqual(data["dashboard_forms"][0]["total"], 5)
        self.assertEqual(data["dashboard_forms"][0]["pending"], 2)
        self.assertEqual(self.context("today")["dashboard_cards"][0]["value"], 1)
        self.assertEqual(self.context("30d")["dashboard_trend"]["total"], 6)
        self.assertEqual(self.context("all")["dashboard_trend"]["total"], 7)
        self.assertEqual(self.context("invalid")["dashboard_period"], "7d")

    def test_trend_fills_gaps_compares_previous_period_and_handles_zero(self):
        self.submission(days=0)
        self.submission(days=2)
        self.submission(days=8)
        data = self.context()["dashboard_trend"]
        self.assertEqual(len(data["points"]), 7)
        self.assertEqual(sum(point["count"] for point in data["points"]), 2)
        self.assertEqual(data["previous"], 1)
        self.assertEqual(data["change"], 100)
        self.assertEqual(data["points"][0]["count"], 0)
        empty = trend_context(Submission.objects.none(), self.now.date(), self.now, 30)
        self.assertEqual(empty["total"], 0)
        self.assertIsNone(empty["change"])
        self.assertEqual(self.context("all")["dashboard_trend"]["days"], 30)

    def test_date_boundaries_follow_the_application_timezone(self):
        with timezone.override("America/Bogota"):
            self.now = datetime(2026, 9, 23, 6, tzinfo=dt_timezone.utc)
            before = self.submission()
            after = self.submission()
            Submission.objects.filter(pk=before.pk).update(
                submitted_at=datetime(2026, 9, 23, 4, 59, tzinfo=dt_timezone.utc)
            )
            Submission.objects.filter(pk=after.pk).update(
                submitted_at=datetime(2026, 9, 23, 5, 0, tzinfo=dt_timezone.utc)
            )
            data = self.context("today")
            self.assertEqual(data["dashboard_cards"][0]["value"], 1)
            self.assertEqual(data["dashboard_trend"]["total"], 1)

    def test_recent_activity_uses_event_times_and_skips_unknown_upload_dates(self):
        response = self.submission("UNDER_REVIEW", days=40)
        SubmissionReview.objects.create(
            submission=response,
            previous_status="SUBMITTED",
            status="UNDER_REVIEW",
            actor=self.user,
            created_at=self.now - timedelta(minutes=10),
        )
        answer = SubmissionAnswer.objects.create(
            submission=response, field=self.name, value="Privado"
        )
        SubmissionFile.objects.create(
            answer=answer,
            file="fake/a.pdf",
            original_name="Nuevo.pdf",
            size=12,
            uploaded_at=self.now - timedelta(minutes=5),
        )
        SubmissionFile.objects.create(
            answer=answer, file="fake/b.pdf", original_name="Antiguo.pdf", size=12, uploaded_at=None
        )
        data = self.context("today")
        self.assertEqual(data["dashboard_cards"][0]["value"], 0)
        self.assertEqual(
            [event["label"] for event in data["dashboard_events"]],
            ["Documento recibido", "Respuesta en revisión"],
        )
        self.assertNotIn("Privado", str(data["dashboard_events"]))
        self.assertNotIn("Antiguo.pdf", str(data["dashboard_events"]))

    def test_links_preserve_period_status_and_form_and_open_filtered_responses(self):
        self.submission()
        self.submission("VALIDATED")
        data = self.context()
        link = data["dashboard_cards"][0]["url"]
        params = parse_qs(urlparse(link).query)
        self.assertEqual(params["status__exact"], ["SUBMITTED"])
        self.assertIn("submitted_at__gte", params)
        self.client.force_login(self.user)
        result = self.client.get(link)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.context["cl"].result_count, 1)
        self.assertIn(str(self.form.pk), data["dashboard_forms"][0]["url"])

    def test_pending_first_pagination_and_deleted_form_responses_are_retained(self):
        self.submission("VALIDATED")
        Form.objects.filter(pk=self.form.pk).update(deleted_at=self.now)
        for index in range(11):
            form = Form.objects.create(
                workspace=self.form.workspace,
                created_by=self.user,
                name=f"Solicitud {index}",
                slug=f"solicitud-{index}",
            )
            version = FormVersion.objects.create(form=form, version_number=1)
            self.submission(form=form, form_version=version)
        first = self.context()
        self.assertEqual(len(first["dashboard_forms"]), 10)
        self.assertTrue(all(row["pending"] for row in first["dashboard_forms"]))
        self.assertEqual(first["dashboard_next"], "?period=7d&page=2")
        last = self.context(page="2")
        self.assertEqual(last["dashboard_forms"][-1]["form_id"], self.form.pk)
        self.assertIsNotNone(last["dashboard_forms"][-1]["form__deleted_at"])

    def test_permission_boundaries_and_infrastructure_have_no_fake_capacity(self):
        self.assertEqual(self.context()["dashboard_infrastructure"], [])
        self.user.user_permissions.clear()
        self.user = type(self.user).objects.get(pk=self.user.pk)
        with patch("apps.accounts.dashboard.infrastructure_info") as infra:
            data = self.context()
        infra.assert_not_called()
        self.assertFalse(data["dashboard_can_responses"])
        self.assertNotIn("dashboard_cards", data)
        self.user.is_superuser = True
        self.user.save()
        data = self.context()
        self.assertEqual(
            [card["label"] for card in data["dashboard_infrastructure"]],
            ["Base de datos", "Archivos"],
        )
        self.assertNotIn("percent", str(data["dashboard_infrastructure"]))
        self.assertNotIn("disk", str(data["dashboard_infrastructure"]))

    def test_infrastructure_database_read_actual_local_sizes_and_cache(self):
        database = database_info()
        self.assertTrue(database["available"])
        self.assertGreater(database["bytes"], 0)
        self.assertGreater(database["tables"], 0)
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "unregistered.pdf").write_bytes(b"a" * 123)
            storage = FileSystemStorage(location=directory)
            with patch("apps.accounts.infrastructure._file_storages", return_value=[storage]):
                self.assertEqual(files_info()["bytes"], 123)
                self.assertEqual(files_info()["objects"], 1)
                with patch("apps.accounts.infrastructure._local_usage", side_effect=OSError):
                    self.assertFalse(files_info()["available"])
                cache.clear()
                infrastructure_info()
                with CaptureQueriesContext(connection) as queries:
                    infrastructure_info()
                self.assertEqual(len(queries), 0)
