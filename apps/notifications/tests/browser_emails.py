"""Browser regression coverage; all email delivery is synthetic."""

import tempfile
from pathlib import Path

from django.contrib.auth.models import Permission
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import expect, sync_playwright

from apps.notifications.models import EmailDeliveryEvent
from apps.notifications.models import EmailNotification as Email
from apps.notifications.tests.test_notifications import setup_case


@override_settings(EMAIL_NOTIFICATIONS_ENABLED=False)
class EmailBrowserTests(StaticLiveServerTestCase):
    def test_filters_detail_timeline_and_responsive_layout(self):
        setup_case(self)
        self.user.user_permissions.set(Permission.objects.filter(codename="view_submission"))
        for index in range(12):
            item = Email.objects.create(
                form=self.form,
                form_name="Afiliación al programa",
                submission=self.submission,
                event_type="SUBMISSION_VALIDATED",
                recipient_kind="RESPONDENT",
                recipient_email=f"persona{index}@example.com",
                status="DELIVERED" if index else "FAILED",
                idempotency_key=f"browser-{index}",
                sent_at=timezone.now(),
                delivered_at=timezone.now() if index else None,
                attempts=1,
                provider_message_id=f"provider-{index}",
            )
        EmailDeliveryEvent.objects.create(
            notification=item,
            provider_event_id="msg-browser",
            provider_message_id=item.provider_message_id,
            event_type="email.delivered",
            occurred_at=timezone.now(),
        )
        self.client.force_login(self.user)
        errors = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1600, "height": 1050})
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
            page.goto(
                self.live_server_url + reverse("admin:notifications_emailnotification_changelist")
            )
            expect(page.locator(".email-metrics article")).to_have_count(4)
            expect(page.locator(".email-results tbody tr")).to_have_count(10)
            page.get_by_role("link", name="Siguiente", exact=True).click()
            expect(page.locator(".email-results tbody tr")).to_have_count(2)
            page.get_by_label("Estado", exact=True).select_option("DELIVERED")
            page.get_by_label("Buscar", exact=True).fill("persona11@")
            page.get_by_role("button", name="Aplicar filtros").click()
            expect(page.locator(".email-results tbody tr")).to_have_count(1)
            page.get_by_role("link", name="Ver correo a pe***@example.com", exact=True).click()
            panel = page.get_by_role("complementary", name="Detalle del correo")
            expect(panel).to_be_visible()
            expect(panel).to_contain_text("provider-11")
            expect(panel).to_contain_text("Correo entregado")
            expect(panel).not_to_contain_text("persona11@example.com")
            expect(panel.get_by_role("link", name="Ver respuesta")).to_have_attribute(
                "href", reverse("admin:submissions_submission_detail", args=[self.submission.pk])
            )
            expect(panel.locator("iframe, textarea")).to_have_count(0)
            expect(panel.get_by_role("button", name="Reintentar")).to_have_count(0)
            page.get_by_label("Buscar", exact=True).fill("")
            page.get_by_role("button", name="Aplicar filtros").click()
            page.get_by_role(
                "link", name="Ver correo a pe***@example.com", exact=True
            ).first.click()
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-emails-desktop.png"), full_page=True
            )
            page.set_viewport_size({"width": 390, "height": 844})
            panel.scroll_into_view_if_needed()
            expect(panel).to_be_visible()
            self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 390)
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-emails-mobile.png"), full_page=True
            )
            panel.get_by_role("link", name="Cerrar detalle").click()
            expect(panel).to_have_count(0)
            self.assertEqual(errors, [])
            browser.close()

    def test_builder_settings_show_only_email_and_persist(self):
        setup_case(self)
        self.user.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="forms", codename__in=["view_form", "change_form"]
            )
        )
        # A real response belongs to a published version; editing creates a new one.
        from apps.forms.publication import publish_form

        publish_form(self.form.pk)
        self.client.force_login(self.user)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
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
                self.live_server_url + reverse("admin:forms_form_builder_edit", args=[self.form.pk])
            )
            page.get_by_role("button", name="Configuración", exact=True).click()
            section = page.locator("#email-notification-settings")
            expect(section).to_be_visible()
            expect(section.locator("select option")).to_have_count(2)
            section.get_by_label("Correo del respondiente", exact=True).select_option("correo")
            section.get_by_label("Avisar cuando llegue una nueva respuesta").uncheck()
            page.locator('#builder-settings-panel [data-action="save"]').click()
            expect(page.locator("#save-status")).to_have_text("Formulario guardado")
            page.reload()
            page.get_by_role("button", name="Configuración", exact=True).click()
            expect(section.get_by_label("Correo del respondiente", exact=True)).to_have_value(
                "correo"
            )
            expect(
                section.get_by_label("Avisar cuando llegue una nueva respuesta")
            ).not_to_be_checked()
            browser.close()
