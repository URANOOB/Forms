"""Run explicitly with uv run --with playwright python manage.py test this module."""

import tempfile
from pathlib import Path

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from playwright.sync_api import expect, sync_playwright

from apps.forms.models import FormField, FormSection
from apps.forms.publication import publish_form
from apps.submissions.models import Submission
from apps.submissions.tests.test_public import fixture


class PublicAuditBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        self.form, self.version, self.name, self.choice, self.email = fixture()
        self.numeric = FormField.objects.create(
            form_version=self.version,
            section=self.name.section,
            stable_key="cantidad",
            label="Cantidad",
            field_type="NUMBER",
            order=3,
            required=True,
        )
        skipped = FormSection.objects.create(form_version=self.version, title="Omitida", order=1)
        FormField.objects.create(
            form_version=self.version,
            section=skipped,
            stable_key="omitida",
            label="Omitida",
            field_type="SHORT_TEXT",
            required=True,
        )
        final = FormSection.objects.create(form_version=self.version, title="Confirmación", order=2)
        self.upload = FormField.objects.create(
            form_version=self.version,
            section=final,
            stable_key="archivo",
            label="Soporte",
            field_type="FILE",
            configuration={"extensions": ["txt"], "max_files": 2},
        )
        section = self.name.section
        section.configuration = {"next_section": str(final.pk)}
        section.save()
        self.form = publish_form(self.form.pk)

    def test_public_validation_navigation_mobile_and_success(self):
        errors = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(self.live_server_url + self.form.get_absolute_url())
            page.locator("#welcome-start").click()
            expect(page.locator("#section-progress")).to_have_text("Sección 1 de 2")
            page.locator("#next-button").click()
            expect(page.locator("#error-summary")).to_be_focused()
            page.locator('#error-summary a[href="#id_answer_nombre"]').click()
            expect(page.locator("#id_answer_nombre")).to_be_focused()
            page.locator("#id_answer_nombre").fill("Ana de prueba")
            page.locator("#id_answer_contactar").select_option("si")
            expect(page.locator("#id_answer_correo")).to_be_visible()
            page.locator("#id_answer_contactar").select_option("no")
            expect(page.locator("#id_answer_correo")).to_be_disabled()
            page.locator("#id_answer_cantidad").fill("9007199254740993")
            page.locator("#next-button").click()
            expect(page.locator("#error-summary")).to_be_focused()
            page.locator('#error-summary a[href="#id_answer_cantidad"]').click()
            expect(page.locator("#id_answer_cantidad")).to_be_focused()
            expect(page.locator("#section-progress")).to_have_text("Sección 1 de 2")
            page.locator("#id_answer_cantidad").fill("123")
            page.locator("#next-button").click()
            expect(page.locator("#section-progress")).to_have_text("Sección 2 de 2")
            transfer = page.evaluate_handle("""() => {
                const transfer = new DataTransfer();
                transfer.items.add(new File(['Prueba'], 'test.txt', {type: 'text/plain'}));
                return transfer;
            }""")
            page.locator(".file-dropzone").dispatch_event("drop", {"dataTransfer": transfer})
            expect(page.locator(".file-state")).to_have_text("Pendiente de confirmación")
            page.locator("#submit-button").click()
            expect(page.locator("#error-summary")).to_be_focused()
            page.locator('#error-summary a[href="#id_answer_archivo"]').click()
            expect(page.locator("#id_answer_archivo")).to_be_focused()
            page.get_by_role("button", name="Quitar test.txt", exact=True).click()
            self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 390)
            page.screenshot(path=str(Path(tempfile.gettempdir()) / "forms-audit-public-mobile.png"))
            page.set_viewport_size({"width": 1440, "height": 900})
            page.locator("#back-button").click()
            expect(page.locator("#id_answer_nombre")).to_have_value("Ana de prueba")
            page.locator("#next-button").click()
            page.locator("#submit-button").click()
            expect(page).to_have_url(
                self.live_server_url + "/f/enviado/?version=" + str(self.version.pk)
            )
            self.assertEqual(errors, [])
            browser.close()
        self.assertEqual(Submission.objects.count(), 1)
        submission = Submission.objects.get()
        self.assertFalse(submission.answers.filter(field__stable_key="omitida").exists())
        self.assertFalse(submission.answers.filter(field=self.email).exists())
        self.assertEqual(submission.answers.get(field=self.numeric).value, 123)

    def test_server_error_links_navigate_to_radio_group(self):
        # Turn the dropdown into a required radio group before publication in a fresh fixture.
        form, version, name, choice, _ = fixture("radios", "radios")
        choice.configuration = {"widget": "radio"}
        choice.required = True
        choice.save()
        form = publish_form(form.pk)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(self.live_server_url + form.get_absolute_url())
            page.locator("#welcome-start").click()
            page.locator("#id_answer_nombre").fill("Ana")
            # Submit without client validation to exercise the server error summary.
            page.locator("#public-form").evaluate("form => form.submit()")
            link = page.locator('#error-summary a[href="#id_answer_contactar_0"]')
            expect(link).to_be_visible()
            link.click()
            expect(page.locator('[name="answer_contactar"]').first).to_be_focused()
            browser.close()

    @override_settings(SUBMISSION_MAX_BYTES=4_000_000)
    def test_aggregate_upload_limit_preserves_input_before_network_submission(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(self.live_server_url + self.form.get_absolute_url())
            page.locator("#welcome-start").click()
            page.locator("#id_answer_nombre").fill("Ana")
            page.locator("#id_answer_cantidad").fill("123")
            page.locator("#next-button").click()
            transfer = page.evaluate_handle("""() => {
                const transfer = new DataTransfer();
                for (let i = 0; i < 2; i++) transfer.items.add(
                    new File(['a'.repeat(2000000)], `${i}.txt`, {type: 'text/plain'})
                );
                return transfer;
            }""")
            page.locator(".file-dropzone").dispatch_event("drop", {"dataTransfer": transfer})
            for button in page.locator(".file-confirm").all():
                button.click()
            page.locator("#submit-button").click()
            expect(page.locator("#error-summary")).to_contain_text("respuesta completa")
            expect(page.locator("#error-summary")).to_be_focused()
            expect(page.locator("#id_answer_nombre")).to_have_value("Ana")
            browser.close()
        self.assertEqual(Submission.objects.count(), 0)

    def test_response_panel_ignores_stale_fetch_and_keeps_loading_current_request(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(self.live_server_url)
            page.set_content("""<div id="response-panel-host">Initial</div>
                <article class="response-work-item" data-response-id="a">
                <a href="/a/" data-panel-url="/a/panel/">A</a></article>
                <article class="response-work-item" data-response-id="b">
                <a href="/b/" data-panel-url="/b/panel/">B</a></article>""")
            page.evaluate("""() => {
                window.pending = {};
                window.fetch = url => new Promise(resolve => { pending[url] = resolve; });
                window.finish = (url, text) => pending[url]({ok: true, redirected: false,
                    headers: new Headers({'content-type': 'text/html'}),
                    text: () => Promise.resolve(text)});
            }""")
            script = Path(__file__).resolve().parents[3] / "static/forms/response-workspace.js"
            page.add_script_tag(path=str(script))
            page.get_by_role("link", name="A", exact=True).click()
            page.get_by_role("link", name="B", exact=True).click()
            page.evaluate("finish('/a/panel/', 'Stale A')")
            expect(page.locator("#response-panel-host")).to_have_text("Initial")
            expect(page.locator("#response-panel-host")).to_have_attribute("aria-busy", "true")
            page.evaluate("finish('/b/panel/', 'Current B')")
            expect(page.locator("#response-panel-host")).to_have_text("Current B")
            expect(page.locator(".response-work-item.is-selected")).to_have_attribute(
                "data-response-id", "b"
            )
            browser.close()
