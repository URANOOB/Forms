"""uv run --with playwright python manage.py test apps.forms.tests.browser_gallery --noinput"""

import tempfile
import uuid
from pathlib import Path

from django.contrib.auth.models import Permission
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from playwright.sync_api import expect, sync_playwright

from apps.forms.models import Form
from apps.forms.publication import publish_form
from apps.submissions.models import Submission
from apps.submissions.tests.test_public import fixture


class GalleryBrowserTests(StaticLiveServerTestCase):
    def test_gallery_search_filters_layouts_and_actions(self):
        form, version, *_ = fixture()
        form.name = "Formulario de ingreso y seguimiento de pacientes"
        form.save()
        user = form.created_by
        user.first_name, user.last_name = "Will", "Galeano"
        user.save()
        user.user_permissions.add(
            *Permission.objects.filter(
                codename__in=["view_form", "change_form", "add_form", "view_submission"]
            )
        )
        publish_form(form.pk)
        Submission.objects.bulk_create(
            [
                Submission(form=form, form_version=version, idempotency_key=uuid.uuid4())
                for _ in range(18)
            ]
        )
        self.client.force_login(user)
        url = self.live_server_url + reverse("admin:forms_form_changelist")
        errors = []
        for index in range(7):
            Form.objects.create(
                workspace=form.workspace,
                created_by=user,
                name=f"Solicitud {index + 1:02d}",
                slug=f"solicitud-{index}",
            )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1600, "height": 1000})
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
            page.goto(url + "?q=ingreso")
            expect(page.get_by_role("heading", name="Formularios", exact=True)).to_have_count(1)
            expect(page.locator(".form-card")).to_have_count(1)
            expect(page.locator(".card-context")).to_have_text("18 respuestas · Will Galeano")
            expect(page.locator(".gallery-result-count")).to_contain_text("1 formulario encontrado")
            expect(page.get_by_label("Propietario", exact=True)).not_to_be_visible()
            expect(page.get_by_role("button", name="Buscar", exact=True)).to_have_count(0)
            width = page.locator(".form-card").bounding_box()["width"]
            self.assertGreaterEqual(width, 600)
            self.assertLessEqual(width, 740)
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-gallery-single.png"), full_page=True
            )
            page.set_viewport_size({"width": 390, "height": 844})
            self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-gallery-single-mobile.png"),
                full_page=True,
            )
            page.set_viewport_size({"width": 1600, "height": 1000})
            page.goto(url)
            expect(page.locator(".form-card")).to_have_count(8)
            columns = page.locator(".form-grid").evaluate(
                "el => getComputedStyle(el).gridTemplateColumns.split(' ').length"
            )
            self.assertEqual(columns, 4)
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-gallery-grid.png"), full_page=True
            )
            page.get_by_label("Buscar formularios", exact=True).fill("ingreso")
            page.get_by_label("Buscar formularios", exact=True).press("Enter")
            expect(page.locator(".form-card")).to_have_count(1)
            page.locator(".gallery-filter-menu > summary").click()
            page.get_by_label("Propietario", exact=True).select_option("mine")
            page.get_by_label("Estado", exact=True).select_option("PUBLISHED")
            page.get_by_label("Fecha de actualización", exact=True).select_option("week")
            page.get_by_label("Orden", exact=True).select_option("name")
            page.screenshot(path=str(Path(tempfile.gettempdir()) / "forms-gallery-filters.png"))
            page.get_by_role("button", name="Aplicar", exact=True).click()
            expect(page.locator(".form-card")).to_have_count(1)
            expect(page.locator(".gallery-filter-count")).to_have_text("4")
            expect(page.get_by_label("Buscar formularios", exact=True)).to_have_value("ingreso")
            page.locator(".gallery-filter-menu > summary").click()
            page.get_by_role("link", name="Limpiar filtros", exact=True).click()
            expect(page.locator(".gallery-filter-count")).to_have_count(0)
            expect(page.get_by_label("Buscar formularios", exact=True)).to_have_value("ingreso")
            page.get_by_label("Buscar formularios", exact=True).fill("no-existe")
            page.get_by_label("Buscar formularios", exact=True).press("Enter")
            expect(page.locator(".gallery-empty")).to_be_visible()
            page.get_by_role("link", name="Limpiar filtros", exact=True).click()
            expect(page.locator(".form-card")).to_have_count(8)
            page.get_by_role("button", name="Ver como lista", exact=True).click()
            expect(page.locator("#form-grid")).to_have_attribute("data-layout", "list")
            page.reload()
            expect(page.locator("#form-grid")).to_have_attribute("data-layout", "list")
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-gallery-list.png"), full_page=True
            )
            card = page.locator(".form-card").filter(
                has=page.locator(".card-title", has_text="Formulario de ingreso")
            )
            card.locator(".card-menu > summary").click()
            expect(card.get_by_role("button", name="Pausar recepción")).to_be_visible()
            page.keyboard.press("Escape")
            expect(card.locator(".card-menu > summary")).to_be_focused()
            card.get_by_role("link", name="18 respuestas").click()
            expect(
                page.get_by_role("heading", name="Respuestas recibidas", exact=True)
            ).to_have_count(1)
            expect(page.locator(".response-list-heading")).to_contain_text("18 respuestas")
            page.go_back()
            page.set_viewport_size({"width": 390, "height": 844})
            self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            page.get_by_role("button", name="Ver como tarjetas", exact=True).click()
            self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            page.locator(".gallery-filter-menu > summary").click()
            bounds = page.locator(".gallery-filter-panel").bounding_box()
            self.assertGreaterEqual(bounds["x"], 0)
            self.assertLessEqual(bounds["x"] + bounds["width"], 390)
            page.keyboard.press("Escape")
            page.screenshot(path=str(Path(tempfile.gettempdir()) / "forms-gallery-mobile.png"))
            page.get_by_role("button", name="Abrir o cerrar navegación").click()
            expect(page.locator("#nav-sidebar")).to_be_visible()
            page.set_viewport_size({"width": 1600, "height": 1000})
            page.goto(url)
            expect(page.get_by_role("heading", name="Formularios", exact=True)).to_have_count(1)
            page.evaluate("document.documentElement.classList.add('dark')")
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-gallery-dark.png"), full_page=True
            )
            browser.close()
        self.assertFalse(errors, errors)
