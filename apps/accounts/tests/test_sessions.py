from time import time
from unittest.mock import patch

from django.contrib.sessions.models import Session
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.sessions import ACTIVITY_KEY
from apps.forms.publication import publish_form
from apps.submissions.tests.test_public import fixture


@override_settings(SESSION_IDLE_TIMEOUT_SECONDS=60)
class IdleSessionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="session-admin")
        self.now = time()
        self.clock = patch("apps.accounts.sessions.time", return_value=self.now)
        self.time = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.client.force_login(self.user)
        self.url = reverse("session_activity")

    def test_login_initializes_absolute_expiry(self):
        self.assertEqual(self.client.session[ACTIVITY_KEY], self.now)
        self.assertAlmostEqual(
            self.client.session.get_expiry_date().timestamp(), self.now + 60, places=4
        )

    def test_polling_does_not_extend_session_and_expiry_deletes_it(self):
        key = self.client.session.session_key
        self.time.return_value = self.now + 59
        self.assertEqual(self.client.get(reverse("platform_activity")).status_code, 200)
        result = self.client.get(self.url)
        self.assertEqual(result.json()["remaining_seconds"], 1)
        self.assertIn("no-store", result["Cache-Control"])
        self.assertEqual(self.client.session[ACTIVITY_KEY], self.now)
        self.time.return_value = self.now + 60
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertFalse(Session.objects.filter(session_key=key).exists())
        self.assertEqual(self.client.post(self.url).status_code, 401)

    def test_activity_slides_deadline_shared_by_tabs(self):
        other_tab = Client()
        other_tab.cookies = self.client.cookies.copy()
        self.time.return_value = self.now + 45
        self.assertEqual(other_tab.post(self.url).json()["remaining_seconds"], 60)
        self.time.return_value = self.now + 61
        self.assertEqual(self.client.get(self.url).json()["remaining_seconds"], 44)
        self.time.return_value = self.now + 105
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(other_tab.post(self.url).status_code, 401)

    def test_navigation_renews_but_background_reads_do_not(self):
        self.time.return_value = self.now + 10
        self.client.get(reverse("admin:accounts_user_changelist"))
        self.assertEqual(self.client.session[ACTIVITY_KEY], self.now + 10)
        self.time.return_value = self.now + 20
        self.client.get(reverse("platform_search"), {"format": "json"}, HTTP_SEC_FETCH_MODE="cors")
        self.assertEqual(self.client.session[ACTIVITY_KEY], self.now + 10)

    def test_expired_session_cannot_submit_protected_changes(self):
        self.time.return_value = self.now + 61
        response = self.client.post(reverse("admin:accounts_user_add"), {"username": "intruder"})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response.url)
        self.assertFalse(User.objects.filter(username="intruder").exists())

    def test_activity_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        client.get(self.url)
        self.assertEqual(client.post(self.url).status_code, 403)
        self.assertEqual(
            client.post(self.url, HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value).status_code,
            200,
        )

    def test_existing_session_gets_deadline_and_public_form_keeps_working(self):
        session = self.client.session
        del session[ACTIVITY_KEY]
        session.save()
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.session[ACTIVITY_KEY], self.now)
        form, *_ = fixture()
        form = publish_form(form.pk)
        self.time.return_value = self.now + 61
        self.assertEqual(self.client.get(form.get_absolute_url()).status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        anonymous = Client()
        self.assertEqual(anonymous.get(form.get_absolute_url()).status_code, 200)
        self.assertNotIn("sessionid", anonymous.cookies)
