"""Run explicitly; set PLAYWRIGHT_NODE_MODULE to an installed Playwright Node package.

Uses Node to keep the browser suite independent of Python native browser bindings.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.files.storage import FileSystemStorage
from django.test import override_settings

from apps.accounts.models import RateLimitBucket
from apps.forms.models import FieldOption, FormField
from apps.forms.publication import publish_form
from apps.submissions.models import Submission, SubmissionFile
from apps.submissions.tests.test_public import fixture


@skipUnless(
    shutil.which("node") and os.getenv("PLAYWRIGHT_NODE_MODULE"), "Node Playwright required"
)
class DraftBrowserTests(StaticLiveServerTestCase):
    def test_restore_expiry_offline_lost_receipt_and_attachments(self):
        with (
            tempfile.TemporaryDirectory() as uploads,
            patch.object(
                SubmissionFile._meta.get_field("file"),
                "storage",
                FileSystemStorage(location=uploads),
            ),
            override_settings(
                STORAGES={
                    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                    "staticfiles": {
                        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
                    },
                    "responses": {
                        "BACKEND": "django.core.files.storage.FileSystemStorage",
                        "OPTIONS": {"location": uploads},
                    },
                }
            ),
        ):
            form, version, name, *_ = fixture()
            for key, label, kind, config in [
                ("documento", "Documento", "SHORT_TEXT", {}),
                ("archivo", "Adjunto", "FILE", {"extensions": ["txt"], "max_mb": 1}),
                ("fecha", "Fecha", "DATE", {}),
                ("multiple", "Opciones", "MULTIPLE_CHOICE", {}),
            ]:
                FormField.objects.create(
                    form_version=version,
                    section=name.section,
                    stable_key=key,
                    label=label,
                    field_type=kind,
                    configuration=config,
                    order=version.fields.count(),
                )
            multi = version.fields.get(stable_key="multiple")
            FieldOption.objects.create(field=multi, label="Opción uno", value="uno")
            FieldOption.objects.create(field=multi, label="Opción dos", value="dos")
            form.duplicate_fields = ["documento"]
            form.save(update_fields=["duplicate_fields"])
            form = publish_form(form.pk)
            env = {
                **os.environ,
                "FORMS_DRAFT_FIXTURE": json.dumps(
                    {
                        "url": self.live_server_url + form.get_absolute_url(),
                        "formId": str(form.pk),
                        "versionId": str(version.pk),
                    }
                ),
            }
            for mode in ["main", "files"]:
                # These independent browser scenarios share the live server's loopback IP.
                RateLimitBucket.objects.all().delete()
                result = subprocess.run(
                    [shutil.which("node"), str(Path(__file__).with_suffix(".cjs"))],
                    env={**env, "FORMS_DRAFT_MODE": mode},
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=180,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(Submission.objects.count(), 4)
            self.assertEqual(Submission.objects.filter(attention="DUPLICATE").count(), 1)
            self.assertEqual(SubmissionFile.objects.count(), 1)
