"""uv run --with playwright python manage.py test apps.submissions.tests.browser_review --noinput"""

import tempfile
import uuid
from pathlib import Path

from django.contrib.auth.models import Permission
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from playwright.sync_api import expect, sync_playwright

from apps.forms.models import FormField
from apps.forms.publication import publish_form
from apps.submissions.models import Submission, SubmissionAnswer
from apps.submissions.tests.test_public import fixture


class ReviewBrowserTests(StaticLiveServerTestCase):
    def test_work_list_scrolls_after_five_complete_responses(self):
        form, version, name, *_ = fixture()
        for index in range(7):
            response = Submission.objects.create(
                form=form,
                form_version=version,
                status="SUBMITTED" if index < 5 else "UNDER_REVIEW",
                idempotency_key=uuid.uuid4(),
            )
            SubmissionAnswer.objects.create(
                submission=response,
                field=name,
                value=f"Persona de prueba {index}"
                + (" con un nombre largo" * 4 if index == 4 else ""),
            )
        user = form.created_by
        user.is_superuser = True
        user.save()
        self.client.force_login(user)
        url = self.live_server_url + reverse("admin:submissions_submission_changelist")
        errors = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1600, "height": 1100})
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
            items = page.locator(".response-work-items")
            expect(items.locator(".response-work-item")).to_have_count(7)
            for width in (1600, 1024, 390):
                page.set_viewport_size({"width": width, "height": 1100})
                items.evaluate("el => el.scrollTop = 0")
                page.wait_for_function("""() => {
                    const list = document.querySelector('.response-work-items');
                    const rows = list.querySelectorAll('.response-work-item');
                    const box = list.getBoundingClientRect();
                    return Math.abs(rows[4].getBoundingClientRect().bottom - box.bottom) <= 1
                        && rows[5].getBoundingClientRect().top > box.bottom
                        && list.scrollHeight > list.clientHeight;
                }""")
                page.screenshot(
                    path=str(Path(tempfile.gettempdir()) / f"forms-response-five-{width}.png"),
                    full_page=True,
                )
                items.focus()
                header_top = page.locator(".response-list-heading").bounding_box()["y"]
                page.keyboard.press("End")
                page.wait_for_function("""() => {
                    const list = document.querySelector('.response-work-items');
                    return list.scrollTop > 0
                        && Math.abs(list.scrollHeight - list.clientHeight - list.scrollTop) <= 1;
                }""")
                self.assertAlmostEqual(
                    page.locator(".response-list-heading").bounding_box()["y"], header_top, delta=1
                )
                self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            last = items.locator(".response-item-open").last
            title = last.locator("strong").inner_text()
            last.click()
            expect(page.locator("#response-panel-host .response-case-header")).to_contain_text(
                title
            )
            for status, count in (("SUBMITTED", 5), ("UNDER_REVIEW", 2), ("VALIDATED", 0)):
                page.goto(url + f"?response_status={status}")
                expect(items.locator(".response-work-item")).to_have_count(count)
                self.assertTrue(items.evaluate("el => el.scrollHeight <= el.clientHeight"))
                expect(items).not_to_have_attribute("tabindex", "0")
            browser.close()
        self.assertFalse(errors, errors)

    def test_board_review_flow_and_responsive_layout(self):
        form, version, name, *_ = fixture()
        form.name = "Solicitud de acompañamiento"
        form.save()
        doc = FormField.objects.create(
            form_version=version,
            section=name.section,
            stable_key="documento",
            field_type="SHORT_TEXT",
            label="Documento",
            order=4,
        )
        user = form.created_by
        user.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="submissions",
                codename__in=[
                    "view_submission",
                    "change_submission",
                    "delete_submission",
                ],
            )
        )
        user.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="forms",
                codename__in=["view_form", "change_form"],
            )
        )
        publish_form(form.pk)
        responses = {}
        for status, person in zip(
            Submission.Status.values,
            ["María Rodríguez", "Carlos Pérez", "Ana Torres", "Luis Gómez"],
        ):
            response = Submission.objects.create(
                form=form,
                form_version=version,
                status=status,
                idempotency_key=uuid.uuid4(),
            )
            SubmissionAnswer.objects.create(submission=response, field=name, value=person)
            SubmissionAnswer.objects.create(submission=response, field=doc, value="1023984521")
            responses[status] = response
        selected = responses["SUBMITTED"]
        self.client.force_login(user)
        cookie = self.client.cookies["sessionid"].value
        list_url = self.live_server_url + reverse("admin:submissions_submission_changelist")
        errors = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1600, "height": 1000})
            context.add_cookies(
                [{"name": "sessionid", "value": cookie, "url": self.live_server_url}]
            )
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(list_url + "?view=board")
            expect(page.locator(".response-column")).to_have_count(4)
            expect(page.locator(".response-card")).to_have_count(4)
            expect(page.locator(".response-card").first).to_contain_text("María Rodríguez")
            expect(page.locator(".response-card").first).to_contain_text("•••• 4521")
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-response-board-desktop.png")
            )
            page.get_by_role("link", name="Tabla", exact=True).click()
            expect(page.locator("#result_list")).to_be_visible()
            page.locator("#response-select-all").check()
            expect(page.locator("#response-selection-count")).to_have_text("4 seleccionadas")
            with page.expect_download() as download:
                page.locator("#response-export-selected").click()
            self.assertEqual(download.value.suggested_filename, "respuestas.csv")
            page.screenshot(path=str(Path(tempfile.gettempdir()) / "forms-response-table.png"))
            page.get_by_role("link", name="Estado", exact=True).click()

            def open_action(status):
                page.locator(f'[popovertarget="response-menu-{selected.pk}"]').click()
                page.locator(
                    f'#response-menu-{selected.pk} [data-review-target="{status}"]'
                ).click()

            def change(status, note=""):
                open_action(status)
                dialog = page.locator("#review-dialog")
                dialog.locator("select").select_option(status)
                dialog.locator("textarea").fill(note)
                with page.expect_response(lambda response: "/review/" in response.url):
                    dialog.locator('[type="submit"]').click()
                expect(dialog).not_to_be_visible()
                expect(
                    page.locator(
                        f'.response-column[data-status="{status}"] '
                        f'[popovertarget="response-menu-{selected.pk}"]'
                    )
                ).to_be_visible()

            change("UNDER_REVIEW")
            open_action("REJECTED")
            dialog = page.locator("#review-dialog")
            dialog.locator("select").select_option("REJECTED")
            expect(dialog.locator("textarea")).to_have_attribute("required", "")
            dialog.locator('[type="submit"]').click()
            expect(dialog).to_be_visible()
            dialog.locator("textarea").fill("   ")
            dialog.locator('[type="submit"]').click()
            expect(dialog.locator("#review-error")).to_have_text("Indica el motivo del rechazo.")
            dialog.locator("textarea").fill("Falta adjuntar el documento requerido.")
            dialog.locator('[type="submit"]').click()
            expect(dialog).not_to_be_visible()
            change("UNDER_REVIEW", "Documentación recibida.")
            change("VALIDATED", "Información comprobada.")
            page.goto(
                self.live_server_url
                + reverse(
                    "admin:submissions_submission_detail",
                    args=[selected.pk],
                )
            )
            expect(page.locator(".review-history")).to_contain_text("Falta adjuntar")
            expect(page.locator(".review-history li")).to_have_count(5)
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-response-review-detail.png")
            )
            page.goto(list_url + "?view=board")
            page.set_viewport_size({"width": 390, "height": 844})
            expect(page.locator(".response-column")).to_have_count(4)
            self.assertTrue(
                page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            )
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-response-board-mobile.png"),
                full_page=True,
            )
            page.evaluate("document.documentElement.classList.add('dark')")
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-response-board-dark.png"),
                full_page=True,
            )
            page.set_viewport_size({"width": 1600, "height": 1000})
            page.goto(
                self.live_server_url + reverse("admin:forms_form_builder_edit", args=[form.pk])
            )
            page.locator("#builder-settings").click()
            page.locator("[data-summary-title]").select_option("nombre")
            page.locator('[data-summary-field="0"]').select_option("documento")
            page.locator('[data-summary-mask="0"]').check()
            with page.expect_response(lambda response: "/save/" in response.url):
                page.locator('#builder-settings-panel [data-action="save"]').click()
            page.reload()
            page.locator("#builder-settings").click()
            expect(page.locator("[data-summary-title]")).to_have_value("nombre")
            expect(page.locator('[data-summary-mask="0"]')).to_be_checked()
            browser.close()
        self.assertFalse(errors, errors)
        selected.refresh_from_db()
        self.assertEqual(selected.status, "VALIDATED")
        self.assertEqual(selected.reviews.count(), 4)
