"""Production settings loaded from Workers bindings, never a bundled .env file."""

import os
import ssl

import urllib3.util.ssl_
from workers import env

# Pyodide preloads urllib3 before its SSL shim is available. Restore the module
# reference needed by botocore; HTTPS verification remains managed by Fetch.
urllib3.util.ssl_.ssl = ssl
urllib3.util.ssl_.SSLContext = ssl.SSLContext

for name in (
    "DATABASE_URL",
    "DJANGO_SECRET_KEY",
    "DJANGO_ALLOWED_HOSTS",
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "FILE_STORAGE",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_ACCOUNT_ID",
    "R2_BUCKET_NAME",
    "R2_ENDPOINT",
    "DATABASE_CAPACITY_BYTES",
    "R2_FREE_STORAGE_REFERENCE_BYTES",
):
    value = getattr(env, name, None)
    if value is not None:
        os.environ[name] = str(value)

from .production import *  # noqa: E402,F403

# The entrypoint serializes complete WSGI response lifetimes on this single thread.
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
PASSWORD_HASHERS = ["config.workers_hashers.WorkersPBKDF2PasswordHasher"]

# boto3's transfer thread pool is unavailable in WebAssembly.
from boto3.s3.transfer import TransferConfig  # noqa: E402
from botocore.config import Config  # noqa: E402

for alias in ("default", "responses"):
    STORAGES[alias]["BACKEND"] = "config.workers_storage.WorkersS3Storage"  # noqa: F405
    STORAGES[alias]["OPTIONS"]["transfer_config"] = TransferConfig(use_threads=False)  # noqa: F405
    STORAGES[alias]["OPTIONS"]["client_config"] = Config(  # noqa: F405
        signature_version="s3v4",
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
    )
