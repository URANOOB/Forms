import base64
import hashlib
import hmac
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.forms.builder import document, save_document
from apps.forms.models import FormField, FormSection, FormVersion
from apps.forms.publication import publish_form
from apps.notifications import resend_client
from apps.notifications.models import (
    EmailDeliveryEvent,
    EmailSuppression,
    FormNotificationSettings,
)
from apps.notifications.models import (
    EmailNotification as Email,
)
from apps.notifications.recipients import respondent, save_settings, valid_email
from apps.notifications.services import (
    can_retry,
    payload_for,
    queue_notification,
    send_notification,
)
from apps.submissions.models import Submission, SubmissionAnswer, SubmissionReview
from apps.submissions.review import record_review
from apps.submissions.runtime import new_token
from apps.submissions.tests.test_public import fixture

SETTINGS = {
    "EMAIL_NOTIFICATIONS_ENABLED": True,
    "EMAIL_TEST_RECIPIENT": "",
    "EMAIL_FROM": "LogicForms <notificaciones@example.com>",
    "EMAIL_API_KEY": "test-key-never-used",
    "PUBLIC_BASE_URL": "https://forms.example.com",
    "RESEND_WEBHOOK_SECRET": "whsec_" + base64.b64encode(b"test-webhook-secret").decode(),
}


def setup_case(test):
    test.form, test.version, test.name, _, test.email = fixture()
    test.user = test.form.created_by
    test.user.email = "creator@example.com"
    test.user.save()
    test.submission = Submission.objects.create(
        form=test.form, form_version=test.version, idempotency_key=uuid.uuid4()
    )
    SubmissionAnswer.objects.create(
        submission=test.submission, field=test.email, value="respondent@example.com"
    )


def new_review(test, status="VALIDATED", note=""):
    return SubmissionReview.objects.create(
        submission=test.submission,
        previous_status="UNDER_REVIEW",
        status=status,
        note=note,
        actor=test.user,
    )


def webhook(client, kind="delivered", message_id="provider-one", event_id=None, **kwargs):
    event_id = event_id or f"msg_{uuid.uuid4().hex}"
    body = json.dumps(
        {
            "type": f"email.{kind}",
            "created_at": timezone.now().isoformat(),
            "data": {
                "email_id": message_id,
                "html": "PRIVATE PAYLOAD",
                "to": ["private@example.com"],
            },
        }
    )
    timestamp = str(int(time.time()))
    signed = f"{event_id}.{timestamp}.{body}".encode()
    signature = base64.b64encode(
        hmac.new(b"test-webhook-secret", signed, hashlib.sha256).digest()
    ).decode()
    return client.post(
        "/webhooks/resend/",
        body,
        content_type="application/json",
        HTTP_SVIX_ID=event_id,
        HTTP_SVIX_TIMESTAMP=timestamp,
        HTTP_SVIX_SIGNATURE=kwargs.get("signature", f"v1,{signature}"),
    )


@override_settings(**SETTINGS)
class RecipientTests(TestCase):
    def setUp(self):
        setup_case(self)

    def extra_field(self, kind="EMAIL", version=None):
        return FormField.objects.create(
            form_version=version or self.version,
            section=self.name.section,
            stable_key="otro",
            field_type=kind,
            label="Correo del respondiente",
            order=4,
        )

    def test_single_semantic_email_and_not_label(self):
        self.email.label = "Dirección de contacto"
        self.email.save()
        SubmissionAnswer.objects.create(
            submission=self.submission,
            field=self.extra_field("SHORT_TEXT"),
            value="wrong@example.com",
        )
        self.assertEqual(respondent(self.submission), ("respondent@example.com", ""))

    def test_none_invalid_and_non_string_are_skipped(self):
        for value in ("", "invalid", None, ["x@example.com"], {"email": "x@example.com"}):
            with self.subTest(value=value):
                self.submission.answers.update(value=value)
                email, reason = respondent(self.submission)
                self.assertEqual(email, "")
                self.assertTrue(reason)

    def test_overlong_email_cannot_break_outbox_database_write(self):
        self.assertEqual(valid_email("x" * 64 + "@" + ".".join(["x" * 63] * 3) + ".com"), "")

    def test_multiple_requires_explicit_selection(self):
        other = self.extra_field()
        SubmissionAnswer.objects.create(
            submission=self.submission, field=other, value="other@example.com"
        )
        self.assertIn("varios campos", respondent(self.submission)[1])
        self.assertEqual(respondent(self.submission, "otro"), ("other@example.com", ""))
        self.assertEqual(respondent(self.submission, "missing")[0], "")
        item = queue_notification(self.submission, new_review(self))
        self.assertEqual(item.status, "SKIPPED")
        self.assertEqual(item.attempts, 0)

    def test_selection_uses_submission_version(self):
        publish_form(self.form.pk)
        newer = FormVersion.objects.create(form=self.form, version_number=2)
        section = FormSection.objects.create(form_version=newer, title="Nueva sección")
        FormField.objects.create(
            section=section,
            form_version=newer,
            stable_key="correo",
            field_type="SHORT_TEXT",
            label="Cambió",
        )
        self.assertEqual(respondent(self.submission, "correo"), ("respondent@example.com", ""))

    def test_config_validates_type_and_semantic_field(self):
        for data in (
            {"notify_internal_on_submission": "false"},
            {"respondent_email_stable_key": "nombre"},
            {"respondent_email_stable_key": "missing"},
            {"unknown": True},
            [],
        ):
            with self.subTest(data=data), self.assertRaises(ValidationError):
                save_settings(self.form, data, self.version.fields.all())
        save_settings(
            self.form, {"respondent_email_stable_key": "correo"}, self.version.fields.all()
        )
        self.assertEqual(self.form.email_settings.respondent_email_stable_key, "correo")

    def test_builder_persists_settings_and_fingerprint(self):
        publish_form(self.form.pk)
        self.version.refresh_from_db()
        self.form.refresh_from_db()
        self.version.form = self.form
        before = document(self.version)
        data = {
            **before,
            "notifications": {**before["notifications"], "notify_internal_on_submission": False},
        }
        result = save_document(self.form.pk, data)
        self.assertFalse(result["notifications"]["notify_internal_on_submission"])
        self.assertNotEqual(before["fingerprint"], result["fingerprint"])
        with self.assertRaises(ValidationError):
            save_document(self.form.pk, before)

    def test_templates_escape_rejection_and_have_only_intended_content(self):
        SubmissionAnswer.objects.create(
            submission=self.submission, field=self.name, value="PRIVATE ANSWER"
        )
        item = queue_notification(
            self.submission, new_review(self, "REJECTED", '<script>alert("x")</script>')
        )
        payload = payload_for(item)
        self.assertNotIn("<script>", payload["html"])
        self.assertIn("&lt;script&gt;", payload["html"])
        self.assertIn("<script>", payload["text"])
        self.assertIn("https://forms.example.com" + self.form.get_absolute_url(), payload["html"])
        self.assertNotIn("PRIVATE ANSWER", str(payload))
        self.assertNotIn("attachments", payload)
        received = payload_for(queue_notification(self.submission))
        self.assertIn(
            reverse("admin:submissions_submission_detail", args=[self.submission.pk]),
            received["html"],
        )
        self.assertNotIn("PRIVATE ANSWER", str(received))

    def test_no_bodies_are_stored(self):
        self.assertFalse(
            {"body_html", "body_text", "html", "text"} & {f.name for f in Email._meta.fields}
        )


@override_settings(**SETTINGS)
class DeliveryTests(TransactionTestCase):
    def setUp(self):
        setup_case(self)
        self.sender = patch("apps.notifications.resend_client.send", return_value="provider-one")
        self.mock_send = self.sender.start()
        self.addCleanup(self.sender.stop)

    def pending(self, review=None):
        with patch("apps.notifications.services.send_notification"):
            return queue_notification(self.submission, review)

    def test_commit_sends_once_outside_transaction_and_duplicate_does_not(self):
        def sent(payload, key):
            self.assertFalse(connection.in_atomic_block)
            self.assertEqual(payload["to"], ["creator@example.com"])
            self.assertTrue(key)
            return "provider-one"

        self.mock_send.side_effect = sent
        with transaction.atomic():
            item = queue_notification(self.submission)
            self.assertEqual(item.status, "PENDING")
            self.mock_send.assert_not_called()
        item.refresh_from_db()
        self.assertEqual(
            (item.status, item.attempts, item.provider_message_id), ("SENT", 1, "provider-one")
        )
        self.assertEqual(queue_notification(self.submission).pk, item.pk)
        self.mock_send.assert_called_once()
        self.assertEqual(item.send_attempts.get().status, "SENT")

    def test_rollback_drops_outbox_and_callback(self):
        with self.assertRaises(ValueError), transaction.atomic():
            queue_notification(self.submission)
            raise ValueError
        self.assertFalse(Email.objects.exists())
        self.mock_send.assert_not_called()

    def test_disabled_invalid_and_test_override(self):
        with override_settings(EMAIL_NOTIFICATIONS_ENABLED=False):
            item = queue_notification(self.submission)
        self.assertEqual(item.status, "SKIPPED")
        self.mock_send.assert_not_called()
        with override_settings(EMAIL_TEST_RECIPIENT="test@example.com"):
            item = queue_notification(self.submission, new_review(self))
        self.assertEqual(item.recipient_email, "test@example.com")
        self.assertTrue(item.is_test)
        self.assertEqual(self.mock_send.call_args.args[0]["to"], ["test@example.com"])

    def test_creator_without_valid_email_and_form_flags_skip(self):
        self.user.email = "invalid"
        self.user.save()
        self.submission.form.created_by = self.user
        self.assertEqual(queue_notification(self.submission).status, "SKIPPED")
        FormNotificationSettings.objects.create(
            form=self.form, notify_respondent_on_validated=False
        )
        self.assertEqual(queue_notification(self.submission, new_review(self)).status, "SKIPPED")
        self.mock_send.assert_not_called()

    def test_failure_preserves_workflow_and_sanitizes_error(self):
        self.mock_send.side_effect = RuntimeError("re_secret private@example.com PRIVATE PAYLOAD")
        with transaction.atomic():
            record_review(self.submission, "UNDER_REVIEW", "", self.user)
        with transaction.atomic():
            record_review(self.submission, "VALIDATED", "", self.user)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, "VALIDATED")
        item = Email.objects.get()
        self.assertEqual((item.status, item.attempts), ("FAILED", 1))
        self.assertNotIn("secret", item.last_error)
        self.assertNotIn("private@", item.send_attempts.get().error)

    def test_public_response_survives_provider_failure_and_replay(self):
        publish_form(self.form.pk)
        self.form.refresh_from_db()
        self.mock_send.side_effect = TimeoutError("private")
        token = new_token(self.form)
        data = {"submission_token": token, "answer_nombre": "Prueba", "answer_contactar": "no"}
        for _ in range(2):
            response = self.client.post(self.form.get_absolute_url(), data)
            self.assertEqual(response.status_code, 302)
        self.assertEqual(Submission.objects.count(), 2)
        self.assertEqual(Email.objects.count(), 1)
        self.assertEqual(Email.objects.get().status, "FAILED")
        self.mock_send.assert_called_once()

    def test_reopening_creates_new_notification_but_same_review_does_not(self):
        self.mock_send.side_effect = ["provider-one", "provider-two"]
        for status in ("UNDER_REVIEW", "VALIDATED", "UNDER_REVIEW", "VALIDATED"):
            with transaction.atomic():
                review = record_review(self.submission, status, "", self.user)
            queue_notification(self.submission, review)
        self.assertEqual(Email.objects.count(), 2)
        self.assertEqual(self.mock_send.call_count, 2)

    def test_transport_retry_keeps_key_and_refuses_after_window_or_payload_change(self):
        item = self.pending()
        self.mock_send.side_effect = TimeoutError
        self.assertFalse(send_notification(item.pk))
        first_key = self.mock_send.call_args.args[1]
        self.mock_send.side_effect = None
        self.assertTrue(send_notification(item.pk, retry=True))
        self.assertEqual(self.mock_send.call_args.args[1], first_key)
        item.refresh_from_db()
        self.assertEqual(item.attempts, 2)
        item.status, item.provider_message_id = "FAILED", None
        item.first_attempt_at = timezone.now() - timedelta(hours=24)
        item.save()
        self.assertFalse(can_retry(item))
        self.assertFalse(send_notification(item.pk, retry=True))
        item.first_attempt_at = timezone.now()
        item.save()
        with override_settings(EMAIL_FROM="Different <sender@example.com>"):
            self.assertFalse(send_notification(item.pk, retry=True))
        item.refresh_from_db()
        self.assertIn("contenido cambió", item.last_error)

    def test_sending_lease_and_atomic_guard(self):
        item = self.pending()
        with transaction.atomic():
            self.assertFalse(send_notification(item.pk))
        item.status = "SENDING"
        item.lease_until = timezone.now() + timedelta(minutes=2)
        item.save()
        self.assertFalse(send_notification(item.pk, retry=True))
        item.lease_until = timezone.now() - timedelta(seconds=1)
        item.save()
        self.assertTrue(send_notification(item.pk, retry=True))

    def test_two_workers_claim_only_one_send(self):
        item = self.pending()
        entered, release = Event(), Event()

        def send(payload, key):
            entered.set()
            self.assertTrue(release.wait(10))
            return "provider-one"

        def worker():
            close_old_connections()
            try:
                return send_notification(item.pk, retry=True)
            finally:
                close_old_connections()

        self.mock_send.side_effect = send
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(worker)
            try:
                self.assertTrue(entered.wait(10))
                self.assertFalse(pool.submit(worker).result(timeout=10))
            finally:
                release.set()
            self.assertTrue(first.result(timeout=10))
        self.mock_send.assert_called_once()

    def test_early_webhook_is_reconciled_and_records_timeline_once(self):
        def send(payload, key):
            self.assertEqual(webhook(self.client, event_id="msg_early").status_code, 204)
            self.assertIsNone(EmailDeliveryEvent.objects.get().notification_id)
            return "provider-one"

        self.mock_send.side_effect = send
        item = queue_notification(self.submission)
        item.refresh_from_db()
        self.assertEqual(item.status, "DELIVERED")
        self.assertIsNotNone(item.delivered_at)
        self.assertEqual(item.delivery_events.count(), 1)
        self.assertEqual(webhook(self.client, event_id="msg_early").status_code, 204)
        self.assertEqual(self.submission.activity.filter(event_type="email_delivery").count(), 1)

    def test_provider_confirmed_failure_gets_new_key_and_old_events_do_not_regress(self):
        item = queue_notification(self.submission)
        old_key = self.mock_send.call_args.args[1]
        self.assertEqual(webhook(self.client, "failed").status_code, 204)
        self.mock_send.return_value = "provider-two"
        self.assertTrue(send_notification(item.pk, retry=True))
        self.assertNotEqual(old_key, self.mock_send.call_args.args[1])
        self.assertEqual(webhook(self.client, "failed").status_code, 204)
        item.refresh_from_db()
        self.assertEqual((item.status, item.generation), ("SENT", 1))

    def test_suppression_and_deleted_submission_prevent_sending(self):
        item = self.pending()
        EmailSuppression.objects.create(email=item.recipient_email, reason="BOUNCED")
        self.assertFalse(send_notification(item.pk))
        item.refresh_from_db()
        self.assertEqual(item.status, "SUPPRESSED")
        EmailSuppression.objects.all().delete()
        item.status = "PENDING"
        item.save()
        self.submission.deleted_at = timezone.now()
        self.submission.save()
        self.assertFalse(send_notification(item.pk))
        self.mock_send.assert_not_called()


@override_settings(**SETTINGS)
class WebhookTests(TestCase):
    def setUp(self):
        setup_case(self)
        self.item = queue_notification(self.submission)
        self.item.status, self.item.provider_message_id = "SENT", "provider-one"
        self.item.save()

    def test_signed_events_idempotent_and_metadata_private(self):
        for kind, status in (
            ("sent", "SENT"),
            ("delivery_delayed", "DELIVERY_DELAYED"),
            ("failed", "FAILED"),
            ("delivered", "DELIVERED"),
            ("suppressed", "SUPPRESSED"),
            ("bounced", "BOUNCED"),
            ("complained", "COMPLAINED"),
        ):
            with self.subTest(kind=kind):
                for _ in range(2):
                    self.assertEqual(
                        webhook(self.client, kind, event_id=f"msg_{kind}").status_code, 204
                    )
                self.item.refresh_from_db()
                self.assertEqual(self.item.status, status)
        self.assertEqual(EmailDeliveryEvent.objects.count(), 7)
        self.assertEqual(self.submission.activity.filter(event_type="email_delivery").count(), 6)
        self.assertTrue(all(event.metadata == {} for event in EmailDeliveryEvent.objects.all()))
        self.assertTrue(EmailSuppression.objects.filter(email=self.item.recipient_email).exists())
        self.assertFalse(can_retry(self.item))

    def test_delayed_old_sent_does_not_regress_delivery(self):
        webhook(self.client)
        webhook(self.client, "sent")
        webhook(self.client, "delivery_delayed")
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "DELIVERED")
        self.assertEqual(self.item.last_provider_event, "email.delivered")

    def test_invalid_missing_signature_and_missing_secret(self):
        self.assertEqual(webhook(self.client, signature="v1,bad").status_code, 400)
        self.assertEqual(
            self.client.post(
                "/webhooks/resend/", "{}", content_type="application/json"
            ).status_code,
            400,
        )
        with override_settings(RESEND_WEBHOOK_SECRET=""):
            self.assertEqual(webhook(self.client).status_code, 503)
        self.assertFalse(EmailDeliveryEvent.objects.exists())
        self.assertEqual(self.client.get("/webhooks/resend/").status_code, 405)

    def test_unknown_message_retained_without_payload_and_unknown_event_ignored(self):
        self.assertEqual(webhook(self.client, message_id="unknown").status_code, 204)
        event = EmailDeliveryEvent.objects.get()
        self.assertIsNone(event.notification_id)
        self.assertEqual(event.metadata, {})
        self.assertEqual(webhook(self.client, "opened").status_code, 204)
        self.assertEqual(EmailDeliveryEvent.objects.count(), 1)

    def test_reused_event_id_with_different_message_is_rejected(self):
        self.assertEqual(webhook(self.client, event_id="msg_same").status_code, 204)
        self.assertEqual(
            webhook(self.client, message_id="other", event_id="msg_same").status_code, 400
        )
        self.assertEqual(EmailDeliveryEvent.objects.count(), 1)

    def test_verified_malformed_payload_does_not_raise_server_error(self):
        for payload in (
            [],
            {"type": []},
            {"type": "email.sent", "data": []},
            {"type": "email.sent", "data": {"email_id": []}},
        ):
            with patch("apps.notifications.resend_client.verify", return_value=payload):
                self.assertEqual(
                    self.client.post(
                        "/webhooks/resend/", "{}", content_type="application/json"
                    ).status_code,
                    400,
                )

    def test_oversized_body_rejected(self):
        self.assertEqual(
            self.client.post(
                "/webhooks/resend/", "x" * 65537, content_type="application/json"
            ).status_code,
            413,
        )

    def test_sdk_boundary_and_sanitized_errors(self):
        with patch("resend.Emails.send", return_value={"id": "provider"}) as sdk:
            self.assertEqual(resend_client.send({"subject": "test"}, "key"), "provider")
        sdk.assert_called_once_with({"subject": "test"}, {"idempotency_key": "key"})
        error = RuntimeError("PRIVATE")
        error.code = "429"
        self.assertIn("limitó", resend_client.safe_error(error))


@override_settings(**SETTINGS)
class EmailUITests(TestCase):
    def setUp(self):
        setup_case(self)
        self.user.user_permissions.add(Permission.objects.get(codename="view_submission"))
        self.item = queue_notification(self.submission)
        self.url = reverse("admin:notifications_emailnotification_changelist")
        self.retry_url = reverse("admin:notifications_emailnotification_retry", args=[self.item.pk])

    def test_login_permission_and_read_only_routes(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.user.user_permissions.clear()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.user.user_permissions.add(Permission.objects.get(codename="view_submission"))
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.post(self.url, {"status": "DELIVERED"}).status_code, 405)
        for suffix in ("add/", f"{self.item.pk}/change/", f"{self.item.pk}/delete/"):
            self.assertEqual(self.client.get(self.url + suffix).status_code, 404)
        self.assertEqual(self.client.post(self.retry_url).status_code, 403)

    def test_masked_metadata_and_metrics(self):
        self.user.email = "operator@example.com"
        self.user.save()
        self.item.status = "DELIVERED"
        self.item.sent_at = self.item.delivered_at = timezone.now()
        self.item.subject = "PRIVATE SUBJECT"
        self.item.save()
        self.client.force_login(self.user)
        response = self.client.get(self.url, {"selected": self.item.pk})
        self.assertContains(response, "cr***@example.com")
        self.assertNotContains(response, "creator@example.com")
        self.assertNotContains(response, "PRIVATE SUBJECT")
        self.assertNotContains(response, "<iframe")
        self.assertContains(response, "Historial de entrega")
        self.assertNotContains(response, ">Reintentar<")
        self.assertEqual(
            response.context["metrics"], {"sent": 1, "delivered": 1, "pending": 0, "failed": 0}
        )

    def test_filters_pagination_validation_and_selected_scope(self):
        self.client.force_login(self.user)
        for index in range(12):
            Email.objects.create(
                form=self.form,
                form_name="Otro formulario",
                event_type="SUBMISSION_VALIDATED",
                recipient_kind="RESPONDENT",
                recipient_email="other@example.com",
                status="FAILED",
                idempotency_key=f"other-{index}",
            )
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["page"]), 10)
        response = self.client.get(self.url, {"page": 2})
        self.assertEqual(len(response.context["page"]), 3)
        for params in (
            {"q": "creator@"},
            {"status": "PENDING"},
            {"event": "SUBMISSION_RECEIVED"},
            {"kind": "INTERNAL"},
        ):
            self.assertEqual(self.client.get(self.url, params).context["page"].paginator.count, 1)
        self.assertIsNone(
            self.client.get(self.url, {"q": "Otro", "selected": self.item.pk}).context["selected"]
        )
        self.assertEqual(self.client.get(self.url, {"status": "INVALID"}).status_code, 400)
        self.assertEqual(self.client.get(self.url, {"selected": "invalid"}).status_code, 200)

    def test_superuser_retry_only_failed_and_csrf(self):
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        self.item.status = "FAILED"
        self.item.save()
        response = self.client.get(self.url, {"selected": self.item.pk})
        self.assertContains(response, "creator@example.com")
        self.assertContains(response, ">Reintentar<")
        with patch("apps.notifications.views.send_notification", return_value=True) as send:
            self.assertEqual(self.client.post(self.retry_url).status_code, 302)
            send.assert_called_once_with(self.item.pk, retry=True)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.retry_url).status_code, 403)
        self.assertEqual(self.client.get(self.retry_url).status_code, 405)
        for status in ("SENT", "DELIVERED", "BOUNCED", "COMPLAINED", "SUPPRESSED", "SKIPPED"):
            self.item.status = status
            self.item.save()
            with patch("apps.notifications.views.send_notification") as send:
                self.client.post(self.retry_url)
                send.assert_not_called()
