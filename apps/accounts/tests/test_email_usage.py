from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from apps.accounts.email_usage import email_usage_info
from apps.notifications.resend_client import UsageUnavailable, usage


@override_settings(EMAIL_PROVIDER="resend", EMAIL_API_KEY="test-send", RESEND_USAGE_API_KEY="")
class EmailUsageTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        reset = (timezone.now() + timedelta(days=1)).isoformat()
        self.data = {
            "daily": {"used": 25, "sent": 20, "received": 5, "limit": 100, "resets_at": reset},
            "monthly": {"used": 2990, "sent": 2985, "received": 5, "limit": 3000},
        }

    def test_combines_account_quotas_and_caches_without_repeated_requests(self):
        with patch("apps.accounts.email_usage.resend_client.usage", return_value=self.data) as api:
            result = email_usage_info()
            self.assertTrue(result["available"])
            self.assertEqual(result["remaining_today"], 10)
            self.assertEqual(result["periods"][0]["remaining"], 75)
            self.assertEqual(email_usage_info(), result)
            api.assert_called_once_with("test-send")

    def test_exhausted_and_unlimited_daily_plans(self):
        self.data["daily"]["limit"] = None
        self.data["monthly"]["used"] = 3001
        with patch("apps.accounts.email_usage.resend_client.usage", return_value=self.data):
            result = email_usage_info()
        self.assertTrue(result["available"])
        self.assertIsNone(result["periods"][0]["remaining"])
        self.assertEqual(result["remaining_today"], 0)
        self.assertEqual(result["periods"][1]["progress"], 100)

    def test_malformed_usage_never_looks_like_zero_usage(self):
        self.data["daily"]["used"] = -1
        with patch("apps.accounts.email_usage.resend_client.usage", return_value=self.data):
            result = email_usage_info()
        self.assertFalse(result["available"])
        self.assertNotIn("remaining_today", result)

    def test_cache_expires_at_quota_reset(self):
        now = timezone.now()
        self.data["daily"]["resets_at"] = (now + timedelta(seconds=10)).isoformat()
        with patch("apps.accounts.email_usage.resend_client.usage", return_value=self.data) as api:
            email_usage_info()
            with patch(
                "apps.accounts.email_usage.timezone.now", return_value=now + timedelta(seconds=11)
            ):
                email_usage_info()
            self.assertEqual(api.call_count, 2)

    def test_monitoring_credentials_have_separate_cache_and_no_key_leaks(self):
        with patch("apps.accounts.email_usage.resend_client.usage", return_value=self.data) as api:
            email_usage_info()
            with override_settings(RESEND_USAGE_API_KEY="test-monitoring"):
                result = email_usage_info()
            self.assertEqual(api.call_count, 2)
            api.assert_called_with("test-monitoring")
            self.assertNotIn("test-monitoring", str(result))

    def test_missing_configuration_does_not_call_provider(self):
        with (
            override_settings(EMAIL_API_KEY=""),
            patch("apps.accounts.email_usage.resend_client.usage") as api,
        ):
            self.assertFalse(email_usage_info()["available"])
            api.assert_not_called()

    def test_provider_error_does_not_disclose_response_or_api_key(self):
        with patch("resend.RequestsClient.request", return_value=(b"sensitive response", 403, {})):
            with self.assertRaises(UsageUnavailable) as error:
                usage("private-key")
        self.assertNotIn("private-key", str(error.exception))
        self.assertNotIn("sensitive", str(error.exception))
