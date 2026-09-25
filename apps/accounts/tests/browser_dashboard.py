"""Dashboard browser coverage with synthetic submissions and recorded events."""

import tempfile
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import expect, sync_playwright

from apps.accounts.infrastructure import capacity_info
from apps.forms.models import Form, FormVersion
from apps.submissions.models import Submission, SubmissionAnswer, SubmissionFile, SubmissionReview
from apps.submissions.tests.test_public import fixture


class DashboardBrowserTests(StaticLiveServerTestCase):
    def test_dashboard_periods_links_chart_and_mobile(self):
        # Synthetic provider measurements: browser checks never call cloud services.
        database = capacity_info(
            {
                "label": "Base de datos",
                "kind": "database",
                "provider": "Supabase PostgreSQL",
                "available": True,
                "bytes": 42_300_000,
                "tables": 22,
                "scope": "Bases de datos e índices del proyecto",
                "state": "Uso real consultado",
            },
            500_000_000,
        )
        files = capacity_info(
            {
                "label": "Archivos",
                "kind": "files",
                "provider": "Cloudflare R2",
                "is_r2": True,
                "available": True,
                "bytes": 11_119_625,
                "objects": 6,
                "scope": "bucket-de-prueba",
                "state": "Contenido completo del bucket",
                "capacity_note": "Sin límite fijo de capacidad. Los 10 GB-mes gratuitos "
                "se comparten "
                "en la cuenta. El margen de este bucket no es el saldo mensual de facturación.",
            },
            10_000_000_000,
            reference=True,
        )
        self.enterContext(
            patch("apps.accounts.dashboard.infrastructure_info", return_value=[database, files])
        )
        form, version, name, *_ = fixture()
        form.name = "Reporte de Casos Incidentes de Cáncer"
        form.save()
        user = form.created_by
        user.is_superuser = True
        user.save()
        now = timezone.now()
        response = None
        for index in range(4):
            if index:
                form = Form.objects.create(
                    workspace=user.workspace,
                    created_by=user,
                    name=[
                        "",
                        "Formulario de pacientes",
                        "Solicitud de seguimiento",
                        "Registro de ingreso",
                    ][index],
                    slug=f"test-{index}",
                )
                version = FormVersion.objects.create(form=form, version_number=1)
            for number in range(10):
                response = Submission.objects.create(
                    form=form,
                    form_version=version,
                    status=Submission.Status.values[number % 4],
                    idempotency_key=uuid.uuid4(),
                    submitted_at=now - timedelta(days=number % 6, minutes=number),
                )
        old = Submission.objects.create(
            form=form,
            form_version=version,
            idempotency_key=uuid.uuid4(),
            submitted_at=now - timedelta(days=40),
        )
        SubmissionReview.objects.create(
            submission=response,
            previous_status="SUBMITTED",
            status="UNDER_REVIEW",
            actor=user,
            created_at=now - timedelta(minutes=2),
        )
        answer = SubmissionAnswer.objects.create(
            submission=old, field=name, value="Solo datos ficticios"
        )
        SubmissionFile.objects.create(
            answer=answer,
            file="fake/soporte.pdf",
            original_name="Soporte de ingreso.pdf",
            size=10240,
            uploaded_at=now - timedelta(minutes=1),
        )
        cache.clear()
        self.client.force_login(user)
        url = self.live_server_url + reverse("admin:index")
        errors = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(viewport={"width": 1800, "height": 1150})
            context.add_cookies(
                [
                    {
                        "name": "sessionid",
                        "value": self.client.cookies["sessionid"].value,
                        "url": self.live_server_url,
                    }
                ]
            )
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(url)
            expect(page.locator(".metric-card")).to_have_count(5)
            expect(page.locator('[data-status="total"] .metric-value')).to_have_text("40")
            expect(page.locator('[data-status="SUBMITTED"] .metric-value')).to_have_text("12")
            expect(page.locator(".metrics-table tbody tr")).to_have_count(4)
            expect(page.locator(".infrastructure-card")).to_have_count(2)
            expect(page.locator(".infrastructure-card progress")).to_have_count(2)
            expect(page.locator('[data-kind="database"]')).to_contain_text("500 MB")
            expect(page.locator('[data-kind="files"]')).to_contain_text("Margen de referencia")
            expect(page.locator('[data-kind="files"]')).to_contain_text("11,12 MB")
            expect(page.locator(".metrics-events")).to_contain_text("Documento recibido")
            expect(page.locator("#response-trend circle")).to_have_count(7)
            self.assertNotIn("NaN", page.locator("#response-trend").inner_html())
            page.locator("#response-trend circle").last.focus()
            expect(page.locator(".metrics-chart-readout")).to_contain_text("respuestas")
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-dashboard-desktop.png"),
                full_page=True,
            )
            page.locator(".metrics-infrastructure").screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-infrastructure-desktop.png")
            )
            page.locator('[data-status="SUBMITTED"]').click()
            expect(page.locator(".response-total")).to_have_text("12 respuestas")
            page.goto(url)
            page.get_by_role("navigation", name="Período del inicio").get_by_role(
                "link", name="Todo", exact=True
            ).click()
            expect(page.locator('[data-status="total"] .metric-value')).to_have_text("41")
            expect(page.locator("#response-trend circle")).to_have_count(30)
            page.get_by_role("navigation", name="Período del inicio").get_by_role(
                "link", name="Hoy", exact=True
            ).click()
            expect(page.locator("#response-trend circle")).to_have_count(1)
            expect(page.locator(".metric-card")).to_have_count(5)
            page.get_by_role("navigation", name="Período del inicio").get_by_role(
                "link", name="30 días", exact=True
            ).click()
            expect(page.locator('[data-status="total"] .metric-value')).to_have_text("40")
            page.evaluate("document.documentElement.classList.add('dark')")
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-dashboard-dark.png"), full_page=True
            )
            page.evaluate("document.documentElement.classList.remove('dark')")
            page.set_viewport_size({"width": 390, "height": 844})
            self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            page.locator(".metrics-chart-data summary").click()
            expect(page.locator(".metrics-chart-data tbody tr")).to_have_count(30)
            page.locator(".metrics-chart-data summary").click()
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-dashboard-mobile.png"), full_page=True
            )
            page.get_by_role("button", name="Abrir o cerrar navegación").click()
            expect(page.locator("#nav-sidebar")).to_be_visible()
            browser.close()
        self.assertFalse(errors, errors)
