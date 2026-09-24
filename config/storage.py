"""Storage selection; enabling R2 never changes the static-file backend."""

from django.core.exceptions import ImproperlyConfigured


def storage_settings(base_dir, env):
    configured = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": base_dir / "media"},
        },
        "responses": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": base_dir / "private_uploads"},
        },
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    provider = env.get("FILE_STORAGE", "local").strip().lower()
    if provider == "local":
        return configured
    if provider != "r2":
        raise ImproperlyConfigured("FILE_STORAGE debe ser local o r2.")
    required = ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME")
    missing = [name for name in required if not env.get(name, "").strip()]
    endpoint = env.get("R2_ENDPOINT", "").strip()
    if not endpoint:
        account = env.get("R2_ACCOUNT_ID", "").strip()
        if not account:
            missing.append("R2_ACCOUNT_ID o R2_ENDPOINT")
        endpoint = f"https://{account}.r2.cloudflarestorage.com"
    if missing:
        raise ImproperlyConfigured("Falta configurar: " + ", ".join(missing))
    if not endpoint.startswith("https://"):
        raise ImproperlyConfigured("R2_ENDPOINT debe usar HTTPS.")
    for alias in ("default", "responses"):
        configured[alias] = {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "access_key": env["R2_ACCESS_KEY_ID"],
                "secret_key": env["R2_SECRET_ACCESS_KEY"],
                "bucket_name": env["R2_BUCKET_NAME"],
                "endpoint_url": endpoint,
                "region_name": "auto",
                "signature_version": "s3v4",
                "default_acl": None,
                "custom_domain": None,
                "querystring_auth": True,
                "querystring_expire": 60,
                "file_overwrite": False,
                "max_memory_size": 5 * 1024 * 1024,
                "object_parameters": {"CacheControl": "private, no-store"},
            },
        }
    return configured
