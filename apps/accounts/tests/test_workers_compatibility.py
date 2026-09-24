from types import SimpleNamespace

from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.test import SimpleTestCase

from config.workers_hashers import WorkersPBKDF2PasswordHasher
from config.workers_storage import normalize_s3_headers


class WorkersPasswordTests(SimpleTestCase):
    def test_existing_django_hashes_remain_valid(self):
        native = PBKDF2PasswordHasher()
        worker = WorkersPBKDF2PasswordHasher()
        for password in ("synthetic password", "Contraseña 🔒"):
            with self.subTest(password=password):
                encoded = native.encode(password, "synthetic-salt")
                self.assertEqual(encoded, worker.encode(password, "synthetic-salt"))
                self.assertTrue(worker.verify(password, encoded))
                self.assertFalse(worker.verify("incorrect", encoded))

    def test_older_iteration_counts_can_be_verified_and_upgraded(self):
        worker = WorkersPBKDF2PasswordHasher()
        encoded = PBKDF2PasswordHasher().encode("synthetic", "test-salt", 10000)
        self.assertTrue(worker.verify("synthetic", encoded))
        self.assertTrue(worker.must_update(encoded))
        self.assertEqual(worker.iterations, PBKDF2PasswordHasher.iterations)


class WorkersS3Tests(SimpleTestCase):
    def test_signed_headers_reach_fetch_as_text_without_changing_values(self):
        request = SimpleNamespace(
            headers={"X-Amz-Date": b"20260924T044250Z", "Authorization": "signed-value"}
        )
        normalize_s3_headers(request)
        self.assertEqual(request.headers["X-Amz-Date"], "20260924T044250Z")
        self.assertEqual(request.headers["Authorization"], "signed-value")
