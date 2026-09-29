"""Explicit Chromium regressions for editor state and cross-tab draft ownership."""

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core import signing
from django.urls import reverse
from playwright.sync_api import expect, sync_playwright

from apps.accounts.models import User
from apps.forms.models import FormField, FormSection
from apps.forms.publication import publish_form
from apps.submissions.models import Submission
from apps.submissions.runtime import TOKEN_SALT
from apps.submissions.tests.test_public import fixture


class SeptemberBrowserTests(StaticLiveServerTestCase):
    def test_condition_picker_only_offers_reachable_destinations(self):
        form, version, name, choice, email = fixture()
        second = FormSection.objects.create(form_version=version, title="Decisión", order=1)
        third = FormSection.objects.create(form_version=version, title="Destino", order=2)
        for field in (choice, email):
            field.section = second
            field.save()
        target = FormField.objects.create(
            form_version=version,
            section=third,
            stable_key="destino",
            label="Destino",
            field_type="SHORT_TEXT",
        )
        self.client.force_login(User.objects.create_superuser(username="editor"))
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
            page.goto(
                self.live_server_url + reverse("admin:forms_form_builder_edit", args=[form.pk])
            )
            card = page.locator(f'[data-field="{choice.pk}"]')
            targets = card.locator('[data-action="choose-branch-target"]')
            values = targets.evaluate_all("items => items.map(item => item.dataset.target)")
            self.assertEqual(set(values), {f"f:{email.pk}", f"s:{third.pk}", f"f:{target.pk}"})
            self.assertNotIn(f"s:{name.section_id}", values)
            browser.close()

    def test_original_tab_fork_preserves_both_submissions(self):
        self.check_original_tab_fork()

    def test_offline_fork_survives_reload_and_preserves_both_submissions(self):
        self.check_original_tab_fork(offline=True)

    def test_fork_without_web_locks_preserves_both_submissions(self):
        self.check_original_tab_fork(no_locks=True)

    def check_original_tab_fork(self, offline=False, no_locks=False):
        form, *_ = fixture()
        form = publish_form(form.pk)
        url = self.live_server_url + form.get_absolute_url()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context()
            if no_locks:
                context.add_init_script(
                    "Object.defineProperty(navigator, 'locks', {value: undefined})"
                )
            first = context.new_page()
            first.goto(url)
            if first.locator("#welcome-start").is_visible():
                first.locator("#welcome-start").click()
            first.locator("#id_answer_nombre").fill("Original A")
            expect(first.locator("#draft-status")).to_contain_text("Borrador guardado")

            # Crucial difference from the existing test: A is never reloaded.
            second = context.new_page()
            second.goto(url)
            second.locator("#draft-continue").click()
            expect(second.locator("#id_answer_nombre")).to_have_value("Original A")
            second.locator("#id_answer_nombre").fill("Respuesta B")
            second.wait_for_function(
                "Object.values(localStorage).some(raw => "
                "JSON.parse(raw).answers.answer_nombre?.[0] === 'Respuesta B')"
            )
            if offline:
                context.set_offline(True)
            first.locator("#id_answer_nombre").fill("Respuesta A")
            expect(first.locator("#draft-status")).to_contain_text("por separado")
            drafts = first.evaluate("Object.values(localStorage).map(JSON.parse)")
            answers = sorted(d["answers"]["answer_nombre"][0] for d in drafts)
            if offline:
                self.assertEqual(sum(d["token"] == "" for d in drafts), 1)
                context.set_offline(False)
                first.reload()
                first.locator("#draft-continue").click()
                expect(first.locator("#id_answer_nombre")).to_have_value("Respuesta A")
                drafts = first.evaluate("Object.values(localStorage).map(JSON.parse)")
            nonces = {signing.loads(d["token"], salt=TOKEN_SALT)["nonce"] for d in drafts}
            self.assertEqual(len(nonces), 2)
            self.assertEqual(answers, ["Respuesta A", "Respuesta B"])
            first.locator("#submit-button").click()
            first.wait_for_url("**/f/enviado/**")
            second.locator("#submit-button").click()
            second.wait_for_url("**/f/enviado/**")
            remaining = second.evaluate("Object.keys(localStorage).length")
            browser.close()
        submissions = Submission.objects.count()
        saved = list(
            Submission.objects.filter(answers__field__stable_key="nombre").values_list(
                "answers__value", flat=True
            )
        )
        self.assertEqual(submissions, 2)
        self.assertEqual(len(nonces), 2)
        self.assertEqual(remaining, 0)
        self.assertEqual(set(saved), {"Respuesta A", "Respuesta B"})

    def test_two_tabs_keep_independent_drafts_and_discard_only_their_own(self):
        form, *_ = fixture()
        form = publish_form(form.pk)
        url = self.live_server_url + form.get_absolute_url()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context()
            first, second = context.new_page(), context.new_page()
            for page in (first, second):
                page.goto(url)
                if page.locator("#welcome-start").is_visible():
                    page.locator("#welcome-start").click()
            first.locator("#id_answer_nombre").fill("Primera pestaña")
            expect(first.locator("#draft-status")).to_contain_text("Borrador guardado")
            second.locator("#id_answer_nombre").fill("Segunda pestaña")
            expect(second.locator("#draft-status")).to_contain_text("por separado")
            self.assertNotEqual(
                first.locator('[name="submission_token"]').input_value(),
                second.locator('[name="submission_token"]').input_value(),
            )
            drafts = second.evaluate("Object.values(localStorage).map(JSON.parse)")
            self.assertEqual(
                {d["answers"]["answer_nombre"][0] for d in drafts},
                {"Primera pestaña", "Segunda pestaña"},
            )
            with first.expect_navigation(wait_until="networkidle"):
                first.locator("#draft-discard").click()
            drafts = second.evaluate("Object.values(localStorage).map(JSON.parse)")
            self.assertEqual(
                [d["answers"]["answer_nombre"][0] for d in drafts], ["Segunda pestaña"]
            )
            second.reload()
            second.locator("#draft-continue").click()
            expect(second.locator("#id_answer_nombre")).to_have_value("Segunda pestaña")
            # Two tabs explicitly resume the same draft, then diverge.
            third = context.new_page()
            third.goto(url)
            third.locator("#draft-continue").click()
            expect(third.locator("#id_answer_nombre")).to_have_value("Segunda pestaña")
            second.locator("#id_answer_nombre").fill("Cambio segunda")
            third.locator("#id_answer_nombre").fill("Cambio tercera")
            third.wait_for_function("""() => {
                const drafts = Object.values(localStorage).map(JSON.parse);
                return ['Cambio segunda', 'Cambio tercera'].every(answer =>
                    drafts.some(draft => draft.token &&
                        draft.answers.answer_nombre?.[0] === answer));
            }""")
            drafts = third.evaluate("Object.values(localStorage).map(JSON.parse)")
            self.assertEqual(
                {d["answers"]["answer_nombre"][0] for d in drafts},
                {"Cambio segunda", "Cambio tercera"},
            )
            self.assertEqual(
                len({signing.loads(d["token"], salt=TOKEN_SALT)["nonce"] for d in drafts}), 2
            )
            reopened = context.new_page()
            reopened.goto(url)
            expect(reopened.locator("#draft-choice-label")).to_be_visible()
            expect(reopened.locator("#draft-choice option")).to_have_count(2)
            choices = reopened.locator("#draft-choice option").evaluate_all(
                "items => items.map(item => item.value)"
            )
            for choice in choices:
                reopened.locator("#draft-choice").select_option(choice)
                reopened.locator("#draft-continue").click()
                expect(reopened.locator("#id_answer_nombre")).not_to_have_value("")
                reopened.reload()
            browser.close()

    def test_settings_are_dirty_undoable_and_saved_before_published_preview(self):
        form, *_ = fixture()
        form = publish_form(form.pk)
        self.client.force_login(User.objects.create_superuser(username="editor"))
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
            page.goto(
                self.live_server_url + reverse("admin:forms_form_builder_edit", args=[form.pk])
            )
            page.locator("#builder-settings").click()
            for selector, value in [
                ('[data-notification="notify_internal_on_submission"]', None),
                ("[data-summary-title]", "nombre"),
                ("[data-duplicate-field]", "nombre"),
            ]:
                control = page.locator(selector).first
                if value is None:
                    control.uncheck()
                else:
                    control.select_option(value)
                expect(page.locator("#save-status")).to_have_text("Cambios sin guardar")
                page.locator('[data-action="undo"]').click()
                expect(page.locator("#save-status")).to_have_text("Formulario guardado")
                page.locator('[data-action="redo"]').click()
                expect(page.locator("#save-status")).to_have_text("Cambios sin guardar")
                with page.expect_popup() as popup:
                    page.locator('[data-action="preview"]').click()
                popup.value.close()
                expect(page.locator("#save-status")).to_have_text("Formulario guardado")
            browser.close()
        form.refresh_from_db()
        self.assertFalse(form.email_settings.notify_internal_on_submission)
        self.assertEqual(form.response_summary["title"], "nombre")
        self.assertEqual(form.duplicate_fields, ["nombre"])
