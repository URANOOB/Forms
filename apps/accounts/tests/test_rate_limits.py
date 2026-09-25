from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from threading import Barrier
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.db import DatabaseError, close_old_connections
from django.test import (
    Client,
    RequestFactory,
    SimpleTestCase,
    TestCase,
    TransactionTestCase,
    override_settings,
)
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import RateLimitBucket
from apps.accounts.rate_limits import client_identity, consume
from apps.forms.publication import publish_form
from apps.submissions.models import Submission
from apps.submissions.tests.test_public import fixture


class RateLimitTests(TestCase):
    def setUp(self):
        form, *_ = fixture()
        self.form = publish_form(form.pk)
        self.url = self.form.get_absolute_url()

    def limits(self, **kwargs):
        return override_settings(RATE_LIMITS={**settings.RATE_LIMITS, **kwargs})

    def test_public_posts_are_limited_across_clients_routes_and_new_tokens(self):
        with self.limits(public_post=(2, 60)):
            self.assertNotEqual(self.client.post(self.url).status_code, 429)
            self.assertNotEqual(Client().post(self.url).status_code, 429)
            legacy = reverse("legacy_public_form", args=[self.form.workspace.slug, self.form.slug])
            response = Client().post(legacy, HTTP_X_FORWARDED_FOR="198.51.100.1")
            self.assertEqual(response.status_code, 429)
            self.assertTrue(1 <= int(response["Retry-After"]) <= 60)
            self.assertIn("no-store", response["Cache-Control"])
            self.assertNotEqual(
                Client().post(self.url, REMOTE_ADDR="198.51.100.2").status_code, 429
            )

    def test_new_signed_tokens_do_not_allow_additional_valid_submissions(self):
        with self.limits(public_post=(1, 60)):
            first_token = self.client.get(self.url).context["token"]
            second_token = self.client.get(self.url).context["token"]
            self.assertNotEqual(first_token, second_token)
            payload = {
                "submission_token": first_token,
                "answer_nombre": "Ana",
                "answer_contactar": "no",
            }
            self.assertEqual(self.client.post(self.url, payload).status_code, 302)
            payload["submission_token"] = second_token
            self.assertEqual(self.client.post(self.url, payload).status_code, 429)
            self.assertEqual(Submission.objects.count(), 1)

    def test_hourly_limit_survives_short_window_expiry(self):
        with self.limits(public_post=(100, 60), public_hour=(1, 3600)):
            self.client.post(self.url)
            self.assertEqual(self.client.post(self.url).status_code, 429)

    def test_get_throttle_and_expiry_do_not_extend_on_rejected_requests(self):
        with self.limits(public_read=(1, 60)):
            self.assertEqual(self.client.get(self.url).status_code, 200)
            expires = RateLimitBucket.objects.get().expires_at
            self.assertEqual(Client().get(self.url).status_code, 429)
            self.assertEqual(RateLimitBucket.objects.get().expires_at, expires)
            RateLimitBucket.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
            self.assertEqual(self.client.get(self.url).status_code, 200)
            self.assertEqual(RateLimitBucket.objects.get().count, 1)

    def test_csrf_failures_are_counted_before_csrf_rejection(self):
        client = Client(enforce_csrf_checks=True)
        with self.limits(public_post=(1, 60)):
            self.assertEqual(client.post(self.url).status_code, 403)
            self.assertEqual(client.post(self.url).status_code, 429)

    def test_login_limits_by_account_even_from_different_addresses(self):
        with self.limits(login_account=(1, 900)):
            self.client.post(reverse("admin:login"), {"username": "person", "password": "bad"})
            response = Client().post(
                reverse("admin:login"),
                {"username": " PERSON ", "password": "bad"},
                REMOTE_ADDR="198.51.100.1",
            )
            self.assertEqual(response.status_code, 429)
            self.assertTrue(
                all(len(key) == 64 for key in RateLimitBucket.objects.values_list("key", flat=True))
            )

    def test_login_ip_limit_precedes_username_and_password_checks(self):
        with self.limits(login_ip=(1, 300)):
            self.client.post(reverse("admin:login"), {"username": "one"})
            self.assertEqual(
                self.client.post(reverse("admin:login"), {"username": "two"}).status_code, 429
            )
            self.assertEqual(self.client.get(reverse("admin:login")).status_code, 200)

    def test_unavailable_limiter_fails_closed(self):
        with patch("apps.accounts.rate_limits.consume", side_effect=DatabaseError):
            self.assertEqual(self.client.post(self.url).status_code, 503)
            self.assertEqual(self.client.post(reverse("admin:login")).status_code, 503)

    def test_cleanup_removes_only_expired_counters(self):
        RateLimitBucket.objects.create(
            key="expired", count=1, expires_at=timezone.now() - timedelta(seconds=1)
        )
        consume("public_read", "active")
        call_command("clear_rate_limits", stdout=StringIO())
        self.assertEqual(RateLimitBucket.objects.count(), 1)
        self.assertFalse(RateLimitBucket.objects.filter(key="expired").exists())


class AddressTests(SimpleTestCase):
    @override_settings(RATE_LIMIT_IP_HEADER=None)
    def test_untrusted_forwarded_header_is_ignored_and_ipv6_is_grouped(self):
        request = RequestFactory().get(
            "/", HTTP_X_FORWARDED_FOR="spoof", REMOTE_ADDR="2001:db8:1::1"
        )
        self.assertEqual(client_identity(request), "2001:db8:1::/64")
        request.META["REMOTE_ADDR"] = "::ffff:192.0.2.1"
        self.assertEqual(client_identity(request), "192.0.2.1")

    @override_settings(RATE_LIMIT_IP_HEADER="HTTP_X_VERCEL_FORWARDED_FOR")
    def test_vercel_uses_platform_header_and_missing_metadata_does_not_bypass(self):
        request = RequestFactory().get(
            "/", HTTP_X_VERCEL_FORWARDED_FOR="192.0.2.1", HTTP_X_FORWARDED_FOR="spoof"
        )
        self.assertEqual(client_identity(request), "192.0.2.1")
        request.META["HTTP_X_VERCEL_FORWARDED_FOR"] = "bad, list"
        self.assertEqual(client_identity(request), "unknown")


class ConcurrentRateLimitTests(TransactionTestCase):
    def test_concurrent_first_requests_share_one_atomic_counter(self):
        barrier = Barrier(6)

        def hit(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return consume("public_post", "same-client")
            finally:
                close_old_connections()

        with override_settings(RATE_LIMITS={"public_post": (2, 60)}):
            with ThreadPoolExecutor(max_workers=6) as executor:
                results = list(executor.map(hit, range(6)))
        self.assertEqual(results.count(0), 2)
        self.assertEqual(RateLimitBucket.objects.count(), 1)
