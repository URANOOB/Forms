import tempfile
from pathlib import Path

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.sync_api import expect, sync_playwright

from apps.forms.publication import publish_form
from apps.submissions.tests.test_public import fixture


class PublicAccessibilityBrowserTests(StaticLiveServerTestCase):
    def test_preferences_keyboard_error_links_footer_and_narrow_screen(self):
        form, *_ = fixture()
        form = publish_form(form.pk)
        errors = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(self.live_server_url + form.get_absolute_url())
            trigger = page.get_by_role("button", name="Accesibilidad", exact=True)
            trigger.focus()
            trigger.press("Enter")
            dialog = page.get_by_role("dialog", name="Opciones de accesibilidad")
            expect(dialog).to_be_visible()
            dialog.get_by_label("Extra grande", exact=True).check()
            dialog.get_by_label("Alto contraste", exact=True).check()
            dialog.get_by_label("Mayor espaciado", exact=True).check()
            dialog.press("Escape")
            expect(trigger).to_be_focused()
            page.reload()
            expect(page.locator("html")).to_have_attribute("data-public-text", "extra")
            expect(page.locator("body")).to_have_attribute("data-public-contrast", "high")
            page.locator("#welcome-start").click()
            page.locator("#submit-button").click()
            expect(page.locator("#error-summary")).to_be_visible()
            expect(page.locator("#id_answer_nombre")).to_have_attribute("aria-invalid", "true")
            page.locator('#error-summary a[href="#id_answer_nombre"]').click()
            expect(page.locator("#id_answer_nombre")).to_be_focused()
            page.locator("#id_answer_nombre").fill("Respuesta conservada")
            with page.expect_popup() as popup:
                page.get_by_role("link", name="¿Necesitas ayuda? (abre en otra pestaña)").click()
            help_page = popup.value
            expect(help_page.locator("#help-title")).to_be_visible()
            expect(page.locator("#id_answer_nombre")).to_have_value("Respuesta conservada")
            help_page.close()
            page.set_viewport_size({"width": 320, "height": 800})
            self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 320)
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-accessibility-narrow.png"),
                full_page=True,
            )
            trigger.click()
            dialog.get_by_role("button", name="Restablecer preferencias").click()
            dialog.press("Escape")
            expect(page.locator("html")).to_have_attribute("data-public-text", "normal")
            browser.close()
        self.assertFalse(errors, errors)
