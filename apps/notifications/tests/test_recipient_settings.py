from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.forms.builder import document, save_document
from apps.forms.publication import publish_form
from apps.notifications.forms import RecipientSettingsForm
from apps.notifications.models import EmailNotification as Email
from apps.notifications.models import EmailSuppression, FormNotificationSettings
from apps.notifications.recipients import save_settings
from apps.notifications.services import queue_notification
from apps.notifications.tests.test_notifications import SETTINGS, new_review, setup_case
from apps.submissions.runtime import new_token
from apps.submissions.tests.test_public import fixture


@override_settings(**{**SETTINGS, "EMAIL_NOTIFICATIONS_ENABLED": False})
class RecipientSettingsTests(TestCase):
    def setUp(self):
        setup_case(self)
        self.user.user_permissions.set(
            Permission.objects.filter(codename__in=["view_submission", "change_form"])
        )
        self.client.force_login(self.user)
        self.url = reverse("admin:notifications_emailnotification_recipients")

    def post(self, value, **extra):
        return self.client.post(
            self.url,
            {
                "form": self.form.pk,
                "internal_recipients": value,
                "notify_internal_on_submission": "on",
                **extra,
            },
        )

    def test_save_normalizes_deduplicates_and_preserves_other_settings(self):
        FormNotificationSettings.objects.create(
            form=self.form,
            notify_respondent_on_validated=False,
            respondent_email_stable_key="correo",
        )
        other, *_ = fixture("other", "other")
        response = self.post("equipo@EXAMPLE.com; Equipo@example.com\n jefe@example.com, ")
        self.assertRedirects(response, self.url + f"?form={self.form.pk}")
        config = FormNotificationSettings.objects.get(form=self.form)
        self.assertEqual(config.internal_recipients, ["equipo@example.com", "jefe@example.com"])
        self.assertFalse(config.notify_respondent_on_validated)
        self.assertEqual(config.respondent_email_stable_key, "correo")
        self.assertFalse(FormNotificationSettings.objects.filter(form=other).exists())
        self.assertFalse(Email.objects.exists())

    def test_invalid_addresses_do_not_replace_saved_list(self):
        self.post("original@example.com")
        for value in (
            "ok@example.com,invalid",
            "a@example.com\nBcc: hidden@example.com",
            ",".join(f"person{i}@example.com" for i in range(21)),
        ):
            with self.subTest(value=value):
                self.assertEqual(self.post(value).status_code, 400)
                self.assertEqual(
                    FormNotificationSettings.objects.get(form=self.form).internal_recipients,
                    ["original@example.com"],
                )

    def test_clear_restores_creator_and_can_disable(self):
        self.post("other@example.com")
        self.post("", notify_internal_on_submission="")
        config = FormNotificationSettings.objects.get(form=self.form)
        self.assertEqual(config.internal_recipients, [])
        self.assertFalse(config.notify_internal_on_submission)
        self.assertEqual(queue_notification(self.submission).recipient_email, "creator@example.com")

    def test_permissions_csrf_missing_and_deleted_forms(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(self.url, {"form": self.form.pk}).status_code, 403)
        self.assertEqual(self.client.post(self.url).status_code, 400)
        self.assertEqual(self.client.get(self.url, {"form": "invalid"}).status_code, 404)
        self.form.deleted_at = timezone.now()
        self.form.save()
        self.assertEqual(self.post("other@example.com").status_code, 404)
        self.assertContains(self.client.get(self.url), "Aún no hay formularios")
        self.user.user_permissions.set(Permission.objects.filter(codename="view_submission"))
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.post("other@example.com").status_code, 403)
        self.assertNotContains(
            self.client.get(reverse("admin:notifications_emailnotification_changelist")),
            'href="' + self.url + '"',
        )
        self.user.user_permissions.set(Permission.objects.filter(codename="change_form"))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_builder_preserves_recipients_and_detects_stale_settings(self):
        publish_form(self.form.pk)
        self.version.refresh_from_db()
        self.form.refresh_from_db()
        self.version.form = self.form
        before = document(self.version)
        self.post("team@example.com")
        with self.assertRaises(ValidationError):
            save_document(self.form.pk, before)
        current = document(self.version)
        result = save_document(self.form.pk, current)
        self.assertEqual(result["notifications"]["internal_recipients"], ["team@example.com"])
        save_settings(
            self.form, {"notify_internal_on_submission": False}, self.version.fields.all()
        )
        self.assertEqual(
            FormNotificationSettings.objects.get(form=self.form).internal_recipients,
            ["team@example.com"],
        )
        for value in ("team@example.com", ["invalid"], [None]):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                save_settings(self.form, {"internal_recipients": value}, self.version.fields.all())

    def test_empty_and_mixed_separators(self):
        editor = RecipientSettingsForm({"internal_recipients": " ;,\n "})
        self.assertTrue(editor.is_valid())
        self.assertEqual(editor.cleaned_data["internal_recipients"], [])


@override_settings(**SETTINGS)
class MultipleRecipientDeliveryTests(TransactionTestCase):
    def setUp(self):
        setup_case(self)
        FormNotificationSettings.objects.create(
            form=self.form, internal_recipients=["team@example.com", "boss@example.com"]
        )
        self.sender = patch("apps.notifications.resend_client.send")
        self.send = self.sender.start()
        self.addCleanup(self.sender.stop)
        self.send.side_effect = lambda payload, key: "provider-" + key

    def test_individual_deliveries_after_commit_and_replay(self):
        def send(payload, key):
            self.assertFalse(connection.in_atomic_block)
            self.assertEqual(len(payload["to"]), 1)
            return "provider-" + key

        self.send.side_effect = send
        with transaction.atomic():
            queue_notification(self.submission)
            self.assertEqual(Email.objects.count(), 2)
            self.send.assert_not_called()
        queue_notification(self.submission)
        self.assertEqual(self.send.call_count, 2)
        self.assertEqual(
            set(Email.objects.values_list("recipient_email", "status")),
            {("team@example.com", "SENT"), ("boss@example.com", "SENT")},
        )
        queue_notification(self.submission, new_review(self))
        self.assertEqual(self.send.call_args.args[0]["to"], ["respondent@example.com"])

    def test_rollback_discards_all_recipients(self):
        with self.assertRaises(ValueError), transaction.atomic():
            queue_notification(self.submission)
            raise ValueError
        self.assertFalse(Email.objects.exists())
        self.send.assert_not_called()

    def test_suppression_and_failure_are_independent(self):
        EmailSuppression.objects.create(email="team@example.com", reason="BOUNCED")
        self.send.side_effect = TimeoutError
        queue_notification(self.submission)
        self.assertEqual(Email.objects.get(recipient_email="team@example.com").status, "SUPPRESSED")
        self.assertEqual(Email.objects.get(recipient_email="boss@example.com").status, "FAILED")
        self.assertEqual(self.send.call_count, 1)

    def test_failed_recipient_does_not_prevent_other_delivery(self):
        self.send.side_effect = [TimeoutError(), "provider-success"]
        queue_notification(self.submission)
        self.assertEqual(Email.objects.get(recipient_email="team@example.com").status, "FAILED")
        self.assertEqual(Email.objects.get(recipient_email="boss@example.com").status, "SENT")

    @override_settings(EMAIL_TEST_RECIPIENT="test@example.com")
    def test_test_mode_redirects_each_notification(self):
        queue_notification(self.submission)
        self.assertEqual(Email.objects.count(), 2)
        self.assertEqual(
            Email.objects.filter(is_test=True, recipient_email="test@example.com").count(), 2
        )
        self.assertTrue(
            all(call.args[0]["to"] == ["test@example.com"] for call in self.send.call_args_list)
        )

    def test_public_submission_uses_configured_recipients_once(self):
        publish_form(self.form.pk)
        self.form.refresh_from_db()
        data = {
            "submission_token": new_token(self.form),
            "answer_nombre": "Prueba",
            "answer_contactar": "no",
        }
        for _ in range(2):
            self.assertEqual(self.client.post(self.form.get_absolute_url(), data).status_code, 302)
        self.assertEqual(self.send.call_count, 2)
        self.assertEqual(
            set(Email.objects.values_list("recipient_email", flat=True)),
            {"team@example.com", "boss@example.com"},
        )
