import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from apps.forms.builder import document, save_document
from apps.forms.duplicates import validate_duplicate_fields
from apps.forms.models import Form, FormField
from apps.forms.publication import publish_form
from apps.submissions.duplicates import duplicates_for
from apps.submissions.models import Submission
from apps.submissions.runtime import new_token, read_token, save_response
from apps.submissions.tests.test_public import fixture


class RecoveryDuplicateTests(TestCase):
    def setUp(self):
        self.form, self.version, self.name, self.choice, self.email = fixture()
        self.identity = FormField.objects.create(
            form_version=self.version,
            section=self.name.section,
            order=3,
            label="Número de documento",
            stable_key="documento",
            field_type="SHORT_TEXT",
        )
        self.form.duplicate_fields = ["documento"]
        self.form.save(update_fields=["duplicate_fields"])
        self.form = publish_form(self.form.pk)
        self.url = self.form.get_absolute_url()

    def send(self, identity="12.345", nonce=None):
        return save_response(
            self.form.pk,
            self.version.pk,
            nonce or uuid.uuid4(),
            {
                self.name.pk: "Persona de prueba",
                self.identity.pk: identity,
            },
        )

    def recovery(self, token):
        return self.client.post(
            self.url,
            {
                "submission_action": "recover",
                "submission_token": token,
            },
            HTTP_ACCEPT="application/json",
        )

    def test_recovery_renews_expired_nonce_without_creating_a_response(self):
        with patch(
            "django.core.signing.time.time", return_value=timezone.now().timestamp() - 172800
        ):
            old = new_token(self.form)
        result = self.recovery(old)
        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.json()["received"])
        self.assertFalse(Submission.objects.exists())
        renewed = result.json()["token"]
        self.assertEqual(self.recovery(renewed).json()["received"], False)
        nonce = read_token(renewed, self.form)
        self.send(nonce=nonce)
        confirmed = self.recovery(old)
        self.assertTrue(confirmed.json()["received"])
        self.assertNotContains(confirmed, "Persona de prueba")
        self.assertNotContains(confirmed, "12.345")
        self.assertEqual(Submission.objects.count(), 1)

    def test_recovery_requires_signed_token_for_the_same_form_and_csrf(self):
        self.assertEqual(self.recovery("invalid").status_code, 409)
        other, *_ = fixture("other")
        other = publish_form(other.pk)
        self.assertEqual(self.recovery(new_token(other)).status_code, 409)
        client = Client(enforce_csrf_checks=True)
        result = client.post(
            self.url,
            {
                "submission_action": "recover",
                "submission_token": new_token(self.form),
            },
        )
        self.assertEqual(result.status_code, 403)

    def test_lost_confirmation_survives_new_version_and_pause(self):
        token = new_token(self.form)
        self.send(nonce=read_token(token, self.form))
        save_document(self.form.pk, document(self.form.active_version))
        Form.objects.filter(pk=self.form.pk).update(status="PAUSED")
        self.assertTrue(self.recovery(token).json()["received"])

    def test_unsubmitted_old_version_requires_review(self):
        token = new_token(self.form)
        save_document(self.form.pk, document(self.form.active_version))
        self.assertEqual(self.recovery(token).status_code, 409)
        self.assertFalse(Submission.objects.exists())

    def test_json_validation_and_retries_keep_one_submission(self):
        token = new_token(self.form)
        result = self.client.post(
            self.url, {"submission_token": token}, HTTP_ACCEPT="application/json"
        )
        self.assertEqual(result.status_code, 422)
        self.assertIn("answer_nombre", result.json()["errors"])
        self.assertEqual(result.json()["token"], token)
        for _ in range(2):
            result = self.client.post(
                self.url,
                {
                    "submission_token": token,
                    "answer_nombre": "Ana",
                    "answer_documento": "123",
                },
                HTTP_ACCEPT="application/json",
            )
            self.assertTrue(result.json()["received"])
        self.assertEqual(Submission.objects.count(), 1)
        self.assertEqual(Submission.objects.get().attention, "")

    def test_same_person_different_forms_is_allowed_and_retry_is_not_flagged(self):
        first = self.send()
        retry = self.send(nonce=first.idempotency_key)
        self.assertEqual(retry.pk, first.pk)
        self.assertEqual(retry.attention, "")
        second = self.send("12 345")
        self.assertEqual(second.attention, "DUPLICATE")
        self.assertEqual(second.status, "SUBMITTED")
        self.assertEqual(list(duplicates_for(second)), [first])
        self.assertTrue(second.activity.filter(event_type="duplicate_detected").exists())
        other, version, name, *_ = fixture("other")
        other.duplicate_fields = [name.stable_key]
        other.save(update_fields=["duplicate_fields"])
        other = publish_form(other.pk)
        separate = save_response(other.pk, version.pk, uuid.uuid4(), {name.pk: "12 345"})
        self.assertEqual(separate.attention, "")

    def test_missing_identity_does_not_match_and_trashed_responses_are_excluded(self):
        self.send("")
        self.assertEqual(self.send("").attention, "")
        first = self.send()
        Submission.objects.filter(pk=first.pk).update(deleted_at=timezone.now())
        self.assertEqual(self.send().attention, "")

    def test_all_configured_fields_must_match_including_rejected_responses(self):
        self.form.duplicate_fields = ["documento", "nombre"]
        self.form.save(update_fields=["duplicate_fields"])
        first = self.send()
        Submission.objects.filter(pk=first.pk).update(status="REJECTED")
        different = save_response(
            self.form.pk,
            self.version.pk,
            uuid.uuid4(),
            {
                self.name.pk: "Otra persona",
                self.identity.pk: "12345",
            },
        )
        self.assertEqual(different.attention, "")
        self.assertEqual(self.send().attention, "DUPLICATE")

    def test_configuration_persists_and_matches_historical_versions(self):
        first = self.send()
        data = document(self.form.active_version)
        self.assertEqual(data["duplicate_fields"], ["documento"])
        updated = save_document(self.form.pk, data)
        self.form.refresh_from_db()
        identity = self.form.active_version.fields.get(stable_key="documento")
        second = save_response(
            self.form.pk,
            self.form.active_version_id,
            uuid.uuid4(),
            {
                identity.pk: "12345",
            },
        )
        self.assertEqual(updated["duplicate_fields"], ["documento"])
        self.assertEqual(list(duplicates_for(second)), [first])
        self.assertEqual(second.attention, "DUPLICATE")

    def test_configuration_rejects_unknown_repeated_and_non_scalar_fields(self):
        for invalid in [None, "documento", ["missing"], ["documento", "documento"], [{}]]:
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                validate_duplicate_fields(invalid, [self.identity])
        self.assertEqual(validate_duplicate_fields([], [self.identity]), [])

    def test_match_links_are_only_shown_to_authorized_staff(self):
        first = self.send()
        second = self.send()
        url = reverse("admin:submissions_submission_detail", args=[second.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        user = self.form.created_by
        self.client.force_login(user)
        self.assertEqual(self.client.get(url).status_code, 403)
        user.user_permissions.add(Permission.objects.get(codename="view_submission"))
        first_url = reverse("admin:submissions_submission_detail", args=[first.pk])
        self.assertContains(self.client.get(url), first_url)
        panel = reverse("admin:submissions_submission_panel", args=[second.pk])
        self.assertContains(self.client.get(panel), first_url)
        self.client.logout()
        self.assertNotContains(self.client.get(self.url), first_url)


class ConcurrentIdentityTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_simultaneous_new_responses_flag_exactly_one_possible_duplicate(self):
        form, version, identity, *_ = fixture()
        form.duplicate_fields = [identity.stable_key]
        form.save(update_fields=["duplicate_fields"])
        publish_form(form.pk)

        def send(_):
            close_old_connections()
            try:
                return save_response(
                    form.pk, version.pk, uuid.uuid4(), {identity.pk: "12345"}
                ).attention
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            flags = list(executor.map(send, range(2)))
        self.assertCountEqual(flags, ["", "DUPLICATE"])
        self.assertEqual(Submission.objects.count(), 2)
