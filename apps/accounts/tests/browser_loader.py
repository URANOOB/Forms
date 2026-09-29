"""Loading animation lifecycle and real response-panel integration."""

import tempfile
import uuid
from pathlib import Path

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from playwright.sync_api import expect, sync_playwright

from apps.accounts.models import User
from apps.submissions.models import Submission, SubmissionAnswer
from apps.submissions.tests.test_public import fixture


class LoaderBrowserTests(StaticLiveServerTestCase):
    def test_response_loading_and_concurrent_operations(self):
        form, version, name, *_ = fixture()
        for index in range(2):
            submission = Submission.objects.create(
                form=form, form_version=version, idempotency_key=uuid.uuid4()
            )
            SubmissionAnswer.objects.create(
                submission=submission, field=name, value=f"Persona de prueba {index}"
            )
        self.client.force_login(User.objects.create_superuser(username="loader-admin"))
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 1400, "height": 1000})
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
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(self.live_server_url + reverse("admin:submissions_submission_changelist"))
            loader = page.locator("#platform-loader")
            expect(loader).to_be_hidden()
            held = []
            page.route("**/panel/", lambda route: held.append(route))
            page.locator(".response-item-open").last.click()
            expect(loader).to_be_visible()
            expect(loader).to_contain_text("Cargando respuesta")
            expect(loader.locator("svg")).to_be_visible()
            page.wait_for_function("lottie.getRegisteredAnimations().some(a => a.currentFrame > 1)")
            page.screenshot(path=str(Path(tempfile.gettempdir()) / "forms-loader-desktop.png"))
            held.pop().continue_()
            expect(loader).to_be_hidden()
            detail_url = page.locator(".response-item-open").first.get_attribute("href")
            page.locator(".response-item-open").first.click()
            expect(loader).to_be_visible()
            held.pop().abort()
            page.wait_for_url(self.live_server_url + detail_url)
            page.wait_for_load_state()
            expect(loader).to_be_hidden()

            # Completion of one operation must not hide another operation's indicator.
            page.evaluate(
                "() => { window.stopOne = platformLoader.start(); "
                "window.stopTwo = platformLoader.start(); }"
            )
            expect(loader).to_be_visible()
            page.evaluate("stopOne(); stopOne()")
            expect(loader).to_be_visible()
            page.emulate_media(reduced_motion="reduce")
            page.wait_for_function("lottie.getRegisteredAnimations().every(a => a.isPaused)")
            page.set_viewport_size({"width": 390, "height": 844})
            expect(loader).to_be_in_viewport()
            page.screenshot(path=str(Path(tempfile.gettempdir()) / "forms-loader-mobile.png"))
            page.evaluate("stopTwo()")
            expect(loader).to_be_hidden()
            page.evaluate("platformLoader.start()()")
            page.wait_for_timeout(350)
            expect(loader).to_be_hidden()
            self.assertFalse(errors, errors)
            browser.close()

    def test_text_fallback_when_player_cannot_load(self):
        self.client.force_login(User.objects.create_superuser(username="loader-fallback"))
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context()
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
            page.route("**/lottie_light-5.13.0.min.js", lambda route: route.abort())
            page.goto(self.live_server_url + reverse("admin:accounts_user_changelist"))
            page.evaluate("""() => {
                const modal = document.createElement('dialog');
                modal.id = 'loader-test-dialog';
                document.body.append(modal);
                modal.showModal();
            }""")
            page.evaluate("() => { window.stopLoading = platformLoader.start('Guardando…'); }")
            expect(page.locator("#platform-loader")).to_have_text("Guardando…")
            expect(page.locator("#platform-loader")).to_be_visible()
            expect(page.locator("#loader-test-dialog #platform-loader")).to_have_count(1)
            page.evaluate("stopLoading()")
            expect(page.locator("#platform-loader")).to_be_hidden()
            browser.close()
