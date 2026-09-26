import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.forms.models import Form, FormVersion
from apps.submissions.admin_views import fingerprint
from apps.submissions.models import Submission, SubmissionAnswer, SubmissionReview
from apps.submissions.tests.test_public import fixture


class ReviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.form, cls.version, cls.name, *_ = fixture()
        cls.user = cls.form.created_by
        cls.user.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="submissions",
                codename__in=[
                    "view_submission",
                    "change_submission",
                    "delete_submission",
                ],
            )
        )
        cls.viewer = User.objects.create_user(username="read-only", is_staff=True)
        cls.viewer.user_permissions.add(Permission.objects.get(codename="view_submission"))

    def setUp(self):
        self.submission = Submission.objects.create(
            form=self.form,
            form_version=self.version,
            idempotency_key=uuid.uuid4(),
        )
        SubmissionAnswer.objects.create(
            submission=self.submission,
            field=self.name,
            value="María de prueba",
        )
        self.client.force_login(self.user)
        self.url = reverse("admin:submissions_submission_review", args=[self.submission.pk])
        self.list_url = reverse("admin:submissions_submission_changelist")
        self.detail_url = reverse("admin:submissions_submission_detail", args=[self.submission.pk])

    def review(self, status, note="", **extra):
        self.submission.refresh_from_db()
        return self.client.post(
            self.url,
            {
                "status": status,
                "note": note,
                "revision": self.submission.review_revision,
                **extra,
            },
            HTTP_ACCEPT="application/json",
        )

    def test_review_cycle_records_actor_reason_and_leaves_answers_untouched(self):
        original_date = self.submission.submitted_at
        for status, note in [
            ("UNDER_REVIEW", ""),
            ("REJECTED", "Falta el documento"),
            ("UNDER_REVIEW", "Se recibió la aclaración"),
            ("VALIDATED", "Comprobado"),
        ]:
            self.assertEqual(self.review(status, note).status_code, 200)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, "VALIDATED")
        self.assertEqual(self.submission.review_revision, 4)
        self.assertEqual(self.submission.submitted_at, original_date)
        self.assertEqual(self.submission.form_version, self.version)
        self.assertEqual(self.submission.answers.get().value, "María de prueba")
        self.assertEqual(self.submission.reviews.count(), 4)
        self.assertEqual(self.submission.reviews.first().actor, self.user)
        self.assertEqual(LogEntry.objects.filter(object_id=str(self.submission.pk)).count(), 4)
        detail = self.client.get(self.detail_url)
        self.assertContains(detail, "Falta el documento")
        self.assertContains(detail, "Se recibió la aclaración")

    def test_reject_requires_nonblank_reason_and_limits_note_length(self):
        self.review("UNDER_REVIEW")
        for note in ("", " \n\t", "x" * 2001):
            with self.subTest(note=note[:15]):
                self.assertEqual(self.review("REJECTED", note).status_code, 422)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, "UNDER_REVIEW")
        self.assertEqual(self.submission.reviews.count(), 1)
        self.assertEqual(self.review("REJECTED", "  Incompleta  ").status_code, 200)
        self.assertEqual(self.submission.reviews.first().note, "Incompleta")

    def test_invalid_transition_and_stale_revision_do_not_write(self):
        self.assertEqual(self.review("VALIDATED").status_code, 422)
        self.assertEqual(self.review("UNKNOWN").status_code, 422)
        self.review("UNDER_REVIEW")
        self.assertEqual(self.review("VALIDATED", revision=0).status_code, 409)
        self.assertEqual(self.review("REJECTED", "Motivo", revision="bad").status_code, 409)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, "UNDER_REVIEW")
        self.assertEqual(self.submission.reviews.count(), 1)

    def test_no_js_submission_redirects_and_shows_errors(self):
        self.assertEqual(
            self.client.post(
                self.url,
                {
                    "status": "UNDER_REVIEW",
                    "revision": 0,
                },
            ).status_code,
            302,
        )
        response = self.client.post(self.url, {"status": "REJECTED", "revision": 1})
        self.assertContains(response, "Indica el motivo del rechazo.", status_code=422)

    def test_permissions_csrf_and_post_only(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(
            strict.post(
                self.url,
                {
                    "status": "UNDER_REVIEW",
                    "revision": 0,
                },
            ).status_code,
            403,
        )
        self.client.force_login(self.viewer)
        self.assertEqual(self.review("UNDER_REVIEW").status_code, 403)
        self.assertNotContains(self.client.get(self.list_url), "data-review-url=")
        self.assertNotContains(self.client.get(self.detail_url), "data-review-form")
        self.client.logout()
        self.assertEqual(self.client.get(self.list_url).status_code, 302)
        self.assertEqual(self.client.post(self.url, {}).status_code, 302)

    def test_board_counts_all_matches_and_limits_each_column_independently(self):
        Submission.objects.bulk_create(
            [
                Submission(
                    form=self.form,
                    form_version=self.version,
                    status=status,
                    idempotency_key=uuid.uuid4(),
                )
                for status in Submission.Status.values
                for _ in range(14)
            ]
        )
        response = self.client.get(self.list_url, {"view": "board"})
        self.assertEqual(response.status_code, 200)
        columns = response.context["response_columns"]
        self.assertEqual([column["total"] for column in columns], [15, 14, 14, 14])
        self.assertTrue(all(len(column["cards"]) == 12 for column in columns))
        self.assertTrue(all(column["has_more"] for column in columns))
        self.assertContains(response, 'aria-label="Respuestas por estado;')
        table = self.client.get(self.list_url, {"view": "list"})
        self.assertEqual(table.status_code, 200)
        self.assertEqual(table.context["response_layout"], "list")
        self.assertContains(table, 'id="result_list"')
        filtered = self.client.get(self.list_url + columns[2]["all_url"])
        self.assertEqual(filtered.context["cl"].result_count, 14)

    def test_board_search_and_filters_are_preserved_between_views(self):
        other = Form.objects.create(
            workspace=self.form.workspace,
            created_by=self.user,
            name="Otro",
            slug="otro",
        )
        version = FormVersion.objects.create(form=other, version_number=1)
        Submission.objects.create(form=other, form_version=version, idempotency_key=uuid.uuid4())
        response = self.client.get(self.list_url, {"q": "María", "form": self.form.pk})
        self.assertEqual(response.context["cl"].result_count, 1)
        self.assertIn("form=", response.context["list_url"])
        self.assertIn("q=", response.context["list_url"])
        filtered = self.client.get(self.list_url, {"status__exact": "VALIDATED"})
        self.assertEqual(sum(c["total"] for c in filtered.context["response_columns"]), 0)

    def test_review_notes_and_form_names_are_escaped(self):
        self.review("UNDER_REVIEW", '<script>alert("test")</script>')
        detail = self.client.get(self.detail_url)
        self.assertContains(detail, "&lt;script&gt;")
        self.assertNotContains(detail, '<script>alert("test")</script>')

    def test_editing_final_response_reopens_review_and_cannot_bypass_workflow(self):
        self.review("UNDER_REVIEW")
        self.review("VALIDATED")
        self.submission.refresh_from_db()
        edit_url = reverse("admin:submissions_submission_edit", args=[self.submission.pk])
        data = {
            "revision": fingerprint(self.submission),
            "answer_nombre": "Corregido",
            "response_status": "REJECTED",
        }
        response = self.client.post(edit_url, data)
        self.assertEqual(response.status_code, 302)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, "UNDER_REVIEW")
        self.assertEqual(self.submission.reviews.count(), 3)
        self.assertIn("cambios", self.submission.reviews.first().note)

    def test_review_revision_invalidates_stale_answer_edit_even_after_round_trip(self):
        original = fingerprint(self.submission)
        self.review("UNDER_REVIEW")
        edit_url = reverse("admin:submissions_submission_edit", args=[self.submission.pk])
        response = self.client.post(edit_url, {"revision": original, "answer_nombre": "Cambio"})
        self.assertContains(response, "Otra persona modificó", status_code=422)
        self.assertEqual(self.submission.answers.get().value, "María de prueba")

    def test_answer_changes_invalidate_pending_review_but_noop_edit_keeps_final_status(self):
        self.review("UNDER_REVIEW")
        self.submission.refresh_from_db()
        review_revision = self.submission.review_revision
        edit_url = reverse("admin:submissions_submission_edit", args=[self.submission.pk])
        response = self.client.post(
            edit_url,
            {
                "revision": fingerprint(self.submission),
                "answer_nombre": "Nuevo nombre",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.review("VALIDATED", revision=review_revision).status_code, 409)
        self.assertEqual(self.review("VALIDATED").status_code, 200)
        self.submission.refresh_from_db()
        response = self.client.post(
            edit_url,
            {
                "revision": fingerprint(self.submission),
                "answer_nombre": "Nuevo nombre",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, "VALIDATED")
        self.assertEqual(self.submission.reviews.count(), 2)

    def test_history_can_show_deleted_actor(self):
        self.review("UNDER_REVIEW")
        self.submission.reviews.update(actor=None)
        self.assertContains(self.client.get(self.detail_url), "Usuario eliminado")

    def test_trashing_response_preserves_its_review_history(self):
        self.review("UNDER_REVIEW")
        response = self.client.post(
            reverse("admin:submissions_submission_remove", args=[self.submission.pk]),
            {"confirm_delete": "yes"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(SubmissionReview.objects.exists())
        self.assertFalse(Submission.objects.filter(pk=self.submission.pk).exists())
        self.assertTrue(Submission.all_objects.filter(pk=self.submission.pk).exists())


class ConcurrentReviewTests(TransactionTestCase):
    def test_two_reviewers_cannot_overwrite_each_other(self):
        form, version, *_ = fixture()
        user = form.created_by
        user.user_permissions.add(Permission.objects.get(codename="change_submission"))
        submission = Submission.objects.create(
            form=form,
            form_version=version,
            idempotency_key=uuid.uuid4(),
        )
        clients = [Client(), Client()]
        for client in clients:
            client.force_login(user)
        barrier = Barrier(2)

        def update(client):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return client.post(
                    reverse("admin:submissions_submission_review", args=[submission.pk]),
                    {"status": "UNDER_REVIEW", "revision": 0},
                    HTTP_ACCEPT="application/json",
                ).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(update, clients))
        self.assertEqual(sorted(results), [200, 409])
        self.assertEqual(submission.reviews.count(), 1)
