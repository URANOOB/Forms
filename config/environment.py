"""Select settings consistently for commands and application entrypoints."""

import os


def configure_settings(default="config.settings.production"):
    if os.environ.get("VERCEL") == "1":
        # Vercel discovers settings through manage.py as well as the entrypoint.
        # Neither discovery nor runtime may inherit development/Worker settings.
        os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.production"
        # These hosts come from Vercel's deployment metadata, never the request.
        # Allow exact deployment/production domains without a *.vercel.app wildcard.
        for name in ("VERCEL_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
            host = os.environ.get(name, "").strip()
            if host:
                for setting, value in (
                    ("DJANGO_ALLOWED_HOSTS", host),
                    ("DJANGO_CSRF_TRUSTED_ORIGINS", f"https://{host}"),
                ):
                    current = os.environ.get(setting, "").split(",")
                    os.environ[setting] = ",".join(dict.fromkeys(filter(None, [*current, value])))
    elif not os.environ.get("DJANGO_SETTINGS_MODULE", "").strip():
        os.environ["DJANGO_SETTINGS_MODULE"] = default
