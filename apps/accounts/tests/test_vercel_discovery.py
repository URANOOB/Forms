import json
import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

# Reproduce the builder's discovery: intercept the management command, import
# settings without django.setup(), then serialize every uppercase attribute.
DISCOVER = """
import importlib, json, os, runpy
from unittest.mock import patch
with patch('django.core.management.execute_from_command_line'):
    runpy.run_path('manage.py', run_name='__main__')
name = os.environ.get('DJANGO_SETTINGS_MODULE')
module = importlib.import_module(name)
values = {key: getattr(module, key) for key in dir(module) if key.isupper()}
json.dumps(values, default=str)
print(json.dumps({'module': name, 'debug': values['DEBUG'],
                 'demo': values['ENABLE_DEMO_SEED'],
                 'wsgi': values['WSGI_APPLICATION']}))
"""


class VercelDiscoveryTests(SimpleTestCase):
    def environment(self):
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("DJANGO_", "VERCEL", "R2_"))
        }
        env.update(
            PYTHON_DOTENV_DISABLED="1",
            DATABASE_URL="postgresql://build:build@127.0.0.1/build",
            DJANGO_SECRET_KEY="discovery-test-key-not-used-for-runtime-sessions-0123456789",
            DJANGO_ALLOWED_HOSTS="build.invalid",
            FILE_STORAGE="local",
        )
        return env

    def discover(self, env):
        return subprocess.run(
            [sys.executable, "-c", DISCOVER],
            cwd=Path(settings.BASE_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def test_vercel_discovers_serializable_production_settings(self):
        for previous in (None, "", "config.settings.local", "config.settings.workers"):
            with self.subTest(previous=previous):
                env = self.environment()
                env["VERCEL"] = "1"
                if previous is not None:
                    env["DJANGO_SETTINGS_MODULE"] = previous
                result = self.discover(env)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    json.loads(result.stdout),
                    {
                        "module": "config.settings.production",
                        "debug": False,
                        "demo": False,
                        "wsgi": "config.wsgi.application",
                    },
                )

    def test_native_development_still_uses_local_settings(self):
        result = self.discover(self.environment())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["module"], "config.settings.local")

    def test_missing_database_configuration_is_not_hidden(self):
        env = self.environment()
        env["VERCEL"] = "1"
        env.pop("DATABASE_URL")
        result = self.discover(env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DATABASE_URL es obligatoria", result.stderr)

    def test_navigation_links_resolve_after_django_startup(self):
        navigation = settings.UNFOLD["SIDEBAR"]["navigation"][0]["items"]
        self.assertEqual(
            [item["link"](None) for item in navigation],
            [
                "/admin/",
                "/admin/forms/form/",
                "/admin/submissions/submission/",
                "/admin/accounts/user/",
            ],
        )
