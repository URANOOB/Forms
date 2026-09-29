"""Real browser checks for idle expiry and editing across tabs."""

import re

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse
from playwright.sync_api import expect, sync_playwright

from apps.accounts.models import User
from apps.submissions.tests.test_public import fixture


@override_settings(SESSION_IDLE_TIMEOUT_SECONDS=8)
class IdleSessionBrowserTests(StaticLiveServerTestCase):
    def login_context(self, browser):
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
        return context

    def test_notification_polling_does_not_keep_idle_page_open(self):
        self.client.force_login(User.objects.create_superuser(username="idle-admin"))
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = self.login_context(browser)
            page = context.new_page()
            page.goto(self.live_server_url + reverse("admin:accounts_user_changelist"))
            expect(page.locator("#platform-session")).to_have_count(1)
            page.evaluate("""() => setInterval(() => {
                fetch(document.getElementById('platform-topbar').dataset.activityUrl);
            }, 500)""")
            expect(page).to_have_url(re.compile(r"/admin/login/\?expired=1"), timeout=15000)
            expect(
                page.get_by_text("Tu sesión se cerró por inactividad.", exact=False)
            ).to_be_visible()
            self.assertEqual(
                context.request.get(self.live_server_url + reverse("session_activity")).status, 401
            )
            browser.close()

    def test_typing_keeps_both_tabs_active_then_expires_unsaved_editor(self):
        form, *_ = fixture()
        self.client.force_login(User.objects.create_superuser(username="idle-admin"))
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = self.login_context(browser)
            editor, other = context.new_page(), context.new_page()
            other.goto(self.live_server_url + reverse("admin:accounts_user_changelist"))
            editor.goto(
                self.live_server_url + reverse("admin:forms_form_builder_edit", args=[form.pk])
            )
            editor.bring_to_front()
            dialogs = []
            editor.on("dialog", lambda dialog: (dialogs.append(dialog.type), dialog.dismiss()))
            for i in range(6):
                editor.locator("#form-title").fill(f"Cambios pendientes {i}")
                editor.wait_for_timeout(1800)
            expect(editor.locator("#save-status")).to_have_text("Cambios sin guardar")
            expect(other).not_to_have_url(re.compile("/login/"))
            expect(editor).to_have_url(re.compile(r"/admin/login/\?expired=1"), timeout=15000)
            expect(other).to_have_url(re.compile(r"/admin/login/\?expired=1"), timeout=15000)
            self.assertEqual(dialogs, [])
            browser.close()
