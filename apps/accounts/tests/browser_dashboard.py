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
        user.email = "demo@example.com"
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
            browser = playwright.chromium.launch(headless=True)
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
            frame = page.locator("#page")
            main = page.locator("#main")
            topbar = page.locator("#platform-topbar")
            frame_bounds = frame.bounding_box()
            topbar_bounds = topbar.bounding_box()
            self.assertAlmostEqual(frame_bounds["y"], 18, delta=1)
            self.assertAlmostEqual(frame_bounds["y"] + frame_bounds["height"], 1150 - 18, delta=1)
            main.evaluate("element => element.scrollTop = 600")
            self.assertGreater(main.evaluate("element => element.scrollTop"), 500)
            self.assertEqual(page.evaluate("window.scrollY"), 0)
            self.assertAlmostEqual(topbar.bounding_box()["y"], topbar_bounds["y"], delta=1)
            self.assertTrue(
                page.evaluate("""() => {
                const bounds = document.getElementById('page').getBoundingClientRect();
                const x = bounds.right - 80;
                return [bounds.top - 5, bounds.bottom + 5].every(y =>
                    !document.elementFromPoint(x, y)?.closest('#page'));
            }""")
            )
            page.screenshot(path=str(Path(tempfile.gettempdir()) / "forms-frame-scrolled.png"))
            main.evaluate("element => element.scrollTop = element.scrollHeight")
            expect(page.locator(".metrics-events li").last).to_be_in_viewport()
            page.screenshot(path=str(Path(tempfile.gettempdir()) / "forms-frame-bottom.png"))
            main.evaluate("element => element.scrollTop = 0")
            expect(page.locator(".metric-card")).to_have_count(5)
            expect(page.locator(".metrics-trend-total strong")).to_have_text("40")
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
            expect(page.locator(".response-alternate-heading")).to_contain_text("12 respuestas")
            page.goto(url)
            page.get_by_role("navigation", name="Período de las estadísticas").get_by_role(
                "link", name="Todo", exact=True
            ).click()
            self.assertEqual(
                sum(
                    int(value)
                    for value in page.locator(
                        '.metrics-table [data-label="Total"]'
                    ).all_text_contents()
                ),
                41,
            )
            expect(page.locator("#response-trend circle")).to_have_count(30)
            page.get_by_role("navigation", name="Período de las estadísticas").get_by_role(
                "link", name="Hoy", exact=True
            ).click()
            expect(page.locator("#response-trend circle")).to_have_count(1)
            expect(page.locator(".metric-card")).to_have_count(5)
            page.get_by_role("navigation", name="Período de las estadísticas").get_by_role(
                "link", name="30 días", exact=True
            ).click()
            expect(page.locator(".metrics-trend-total strong")).to_have_text("40")
            page.evaluate("document.documentElement.classList.add('dark')")
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-dashboard-dark.png"), full_page=True
            )
            page.evaluate("document.documentElement.classList.remove('dark')")
            page.set_viewport_size({"width": 390, "height": 844})
            self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            expect(page.locator("#trend-start")).to_be_visible()
            expect(page.locator("#trend-end")).to_be_visible()
            expect(page.locator("#response-trend circle")).to_have_count(30)
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-dashboard-mobile.png"), full_page=True
            )
            page.get_by_role("button", name="Abrir o cerrar navegación").click()
            expect(page.locator("#nav-sidebar")).to_be_visible()
            sidebar = page.locator("#nav-sidebar")
            for group in ("General", "Gestión", "Configuración"):
                expect(sidebar.get_by_role("heading", name=group, exact=True)).to_be_visible()
            sidebar.get_by_role("button", name="Cerrar navegación", exact=True).click()
            expect(sidebar).not_to_be_visible()
            page.get_by_role("button", name="Abrir o cerrar navegación").click()
            expect(sidebar.get_by_role("link", name="LogicForms, inicio")).to_be_in_viewport()
            sidebar.screenshot(path=str(Path(tempfile.gettempdir()) / "forms-sidebar-mobile.png"))
            page.set_viewport_size({"width": 1440, "height": 1000})
            sidebar.get_by_role("link", name="Correos", exact=True).click()
            expect(sidebar.locator("a.active")).to_have_text("Correos")
            sidebar.screenshot(path=str(Path(tempfile.gettempdir()) / "forms-sidebar-desktop.png"))
            profile = sidebar.get_by_role("button", name="Abrir configuración de la cuenta")
            profile.click()
            expect(sidebar.get_by_role("navigation", name="Opciones de cuenta")).to_be_visible()
            sidebar.get_by_role("button", name="Oscuro", exact=True).click()
            expect(sidebar.get_by_role("button", name="Oscuro", exact=True)).to_have_attribute(
                "aria-pressed", "true"
            )
            profile.click()
            sidebar.screenshot(path=str(Path(tempfile.gettempdir()) / "forms-sidebar-dark.png"))
            browser.close()
        self.assertFalse(errors, errors)
