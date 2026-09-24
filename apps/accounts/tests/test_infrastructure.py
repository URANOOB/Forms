import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from django.core.cache import cache
from django.core.files.storage import FileSystemStorage
from django.test import SimpleTestCase, override_settings
from storages.backends.s3 import S3Storage

from apps.accounts.infrastructure import (
    capacity_info,
    files_info,
    infrastructure_info,
    storage_size,
)


@override_settings(DATABASE_CAPACITY_BYTES=None, R2_FREE_STORAGE_REFERENCE_BYTES=10_000_000_000)
class InfrastructureTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.storage = S3Storage(
            access_key="test",
            secret_key="test",
            bucket_name="private-test",
            endpoint_url="https://example.r2.cloudflarestorage.com",
            region_name="auto",
        )

    def r2_info(self, pages):
        client = MagicMock()
        client.get_paginator.return_value.paginate.return_value = pages
        with (
            patch("apps.accounts.infrastructure._file_storages", return_value=[self.storage] * 2),
            patch("apps.accounts.infrastructure._bucket_client", return_value=client),
        ):
            result = files_info()
        client.get_paginator.return_value.paginate.assert_called_once_with(Bucket="private-test")
        client.close.assert_called_once()
        return result

    def test_paginated_bucket_counts_objects_not_in_database_without_double_counting_aliases(self):
        result = self.r2_info(
            [
                {"Contents": [{"Key": "unregistered", "Size": 125}]},
                {"Contents": [{"Key": "another", "Size": 875}]},
            ]
        )
        self.assertEqual(result["objects"], 2)
        self.assertEqual(result["bytes"], 1000)
        self.assertEqual(result["remaining_bytes"], 9_999_999_000)
        self.assertEqual(result["provider"], "Cloudflare R2")
        self.assertEqual(result["remaining_label"], "Margen de referencia")
        self.assertIn("no es el saldo mensual", result["capacity_note"])

    def test_empty_bucket_is_a_successful_zero_measurement(self):
        result = self.r2_info([{}])
        self.assertTrue(result["available"])
        self.assertEqual(result["objects"], 0)
        self.assertEqual(result["percent"], 0)

    def test_partial_failure_never_appears_as_zero_or_a_complete_total(self):
        def pages():
            yield {"Contents": [{"Size": 125}]}
            raise ClientError({"Error": {"Code": "AccessDenied"}}, "ListObjectsV2")

        result = self.r2_info(pages())
        self.assertFalse(result["available"])
        self.assertNotIn("bytes", result)
        self.assertNotIn("objects", result)
        self.assertNotIn("percent", result)
        self.assertEqual(result["remaining_display"], "No disponible")

    def test_listing_timeout_does_not_publish_partial_usage(self):
        with patch("apps.accounts.infrastructure.time.monotonic", side_effect=[0, 11]):
            result = self.r2_info([{"Contents": [{"Size": 1}]}])
        self.assertFalse(result["available"])

    def test_infrequent_access_does_not_use_standard_free_reference(self):
        result = self.r2_info([{"Contents": [{"Size": 125, "StorageClass": "STANDARD_IA"}]}])
        self.assertTrue(result["available"])
        self.assertNotIn("percent", result)
        self.assertEqual(result["remaining_display"], "Sin límite fijo")

    def test_capacity_exceeded_clamps_free_space_and_bar_but_keeps_actual_percentage(self):
        result = capacity_info({"available": True, "bytes": 750}, 500)
        self.assertEqual(result["remaining_bytes"], 0)
        self.assertEqual(result["progress"], 100)
        self.assertEqual(result["percent"], 150)
        self.assertTrue(result["over_capacity"])

    def test_unknown_capacity_or_unavailable_measurement_never_invents_remaining_space(self):
        result = capacity_info({"available": True, "bytes": 123}, None)
        self.assertNotIn("remaining_bytes", result)
        self.assertNotIn("percent", result)
        result = capacity_info({"available": False}, 500)
        self.assertNotIn("remaining_bytes", result)
        self.assertEqual(result["remaining_display"], "No disponible")

    def test_units_match_configured_decimal_plan_values(self):
        self.assertEqual(storage_size(500_000_000), "500 MB")
        self.assertEqual(storage_size(10_000_000_000), "10 GB")

    def test_local_actual_files_include_orphans_and_overlapping_roots_are_not_counted_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nested").mkdir()
            (root / "one").write_bytes(b"123")
            (root / "nested" / "two").write_bytes(b"4567")
            stores = [FileSystemStorage(location=root), FileSystemStorage(location=root / "nested")]
            with patch("apps.accounts.infrastructure._file_storages", return_value=stores):
                result = files_info()
        self.assertEqual((result["bytes"], result["objects"]), (7, 2))
        self.assertIsNone(result["capacity_bytes"])

    def test_cache_is_isolated_by_bucket_and_capacity(self):
        with (
            patch("apps.accounts.infrastructure._file_storages", return_value=[self.storage]),
            patch("apps.accounts.infrastructure.database_info", return_value={"available": True}),
            patch(
                "apps.accounts.infrastructure.files_info", return_value={"available": True}
            ) as probe,
        ):
            infrastructure_info()
            infrastructure_info()
            self.assertEqual(probe.call_count, 1)
            self.storage.bucket_name = "different-bucket"
            infrastructure_info()
            self.assertEqual(probe.call_count, 2)
            with override_settings(DATABASE_CAPACITY_BYTES=500_000_000):
                infrastructure_info()
            self.assertEqual(probe.call_count, 3)
