"""Select settings consistently for commands and application entrypoints."""

import os


def configure_settings(default="config.settings.production"):
    if os.environ.get("VERCEL") == "1":
        # Vercel discovers settings through manage.py as well as the entrypoint.
        # Neither discovery nor runtime may inherit development/Worker settings.
        os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.production"
    elif not os.environ.get("DJANGO_SETTINGS_MODULE", "").strip():
        os.environ["DJANGO_SETTINGS_MODULE"] = default
