from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.files.storage import InMemoryStorage, StorageHandler
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from apps.accounts.management.commands.copy_files_to_r2 import copy_verified, digest
from config.storage import storage_settings


class StorageTests(SimpleTestCase):
    def test_r2_uses_private_storage_for_both_file_types_and_keeps_static_local(self):
        config = storage_settings(
            Path("test"),
            {
                "FILE_STORAGE": "r2",
                "R2_ACCOUNT_ID": "example",
                "R2_ACCESS_KEY_ID": "test",
                "R2_SECRET_ACCESS_KEY": "test",
                "R2_BUCKET_NAME": "private-files",
            },
        )
        storages = StorageHandler(config)
        for alias in ("default", "responses"):
            storage = storages[alias]
            self.assertIsNone(storage.default_acl)
            self.assertIsNone(storage.custom_domain)
            self.assertTrue(storage.querystring_auth)
            self.assertFalse(storage.file_overwrite)
            self.assertEqual(storage.endpoint_url, "https://example.r2.cloudflarestorage.com")
        self.assertEqual(storages["staticfiles"].__class__.__name__, "StaticFilesStorage")

    def test_missing_credentials_fail_closed_and_local_does_not_need_credentials(self):
        self.assertIn("responses", storage_settings(Path("test"), {}))
        with self.assertRaises(ImproperlyConfigured):
            storage_settings(Path("test"), {"FILE_STORAGE": "r2"})
        with self.assertRaises(ImproperlyConfigured):
            storage_settings(Path("test"), {"FILE_STORAGE": "typo"})

    def test_copy_preserves_key_and_bytes_and_is_resumable(self):
        source, destination = InMemoryStorage(), InMemoryStorage()
        name = source.save("responses/example/file.pdf", ContentFile(b"private binary\x00\xff"))
        checksum = digest(source, name)
        self.assertTrue(copy_verified(source, destination, name, checksum))
        self.assertEqual(digest(destination, name), checksum)
        self.assertFalse(copy_verified(source, destination, name, checksum))
        self.assertTrue(source.exists(name))

    def test_conflicting_destination_is_never_overwritten(self):
        source, destination = InMemoryStorage(), InMemoryStorage()
        name = source.save("same.pdf", ContentFile(b"original"))
        destination.save(name, ContentFile(b"existing"))
        with self.assertRaises(CommandError):
            copy_verified(source, destination, name, digest(source, name))
        with destination.open(name) as result:
            self.assertEqual(result.read(), b"existing")

    def test_corrupt_copy_fails_verification(self):
        source, destination = InMemoryStorage(), InMemoryStorage()
        name = source.save("example.pdf", ContentFile(b"original"))
        with patch.object(
            destination,
            "save",
            side_effect=lambda key, _: InMemoryStorage.save(
                destination, key, ContentFile(b"corrupt")
            ),
        ):
            with self.assertRaises(CommandError):
                copy_verified(source, destination, name, digest(source, name))


class CopyCommandTests(TestCase):
    def test_dry_run_never_constructs_remote_storage(self):
        output = StringIO()
        with patch("apps.accounts.management.commands.copy_files_to_r2.StorageHandler") as handler:
            call_command("copy_files_to_r2", stdout=output)
        handler.assert_not_called()
        self.assertIn("Simulación", output.getvalue())
