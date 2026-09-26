"""Browser regression coverage; all email delivery is synthetic."""

import re
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
    def test_recipients_save_validation_and_mobile_layout(self):
        setup_case(self)
        self.user.user_permissions.set(
            Permission.objects.filter(codename__in=["view_submission", "change_form"])
        )
        from apps.submissions.tests.test_public import fixture

        other, *_ = fixture("second", "second")
        other.name = "Otro formulario"
        other.save()
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
                self.live_server_url + reverse("admin:notifications_emailnotification_changelist")
            )
            page.get_by_role("link", name="Destinatarios", exact=True).click()
            page.get_by_role("combobox", name=re.compile("^Formulario:")).click()
            page.get_by_role("option", name=self.form.name, exact=True).click()
            page.get_by_role("button", name="Ver configuración").click()
            addresses = page.get_by_label("Destinatarios", exact=True)
            addresses.fill("equipo@example.com; jefe@example.com; EQUIPO@example.com")
            page.get_by_role("button", name="Guardar destinatarios").click()
            expect(addresses).to_have_value("equipo@example.com\njefe@example.com")
            expect(
                page.get_by_text("Destinatarios guardados para las nuevas respuestas.")
            ).to_be_visible()
            page.reload()
            expect(addresses).to_have_value("equipo@example.com\njefe@example.com")
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-recipients-desktop.png"),
                full_page=True,
            )
            addresses.fill("incorrecto")
            page.get_by_role("button", name="Guardar destinatarios").click()
            expect(page.get_by_role("alert")).to_contain_text("direcciones deben ser válidas")
            page.set_viewport_size({"width": 390, "height": 844})
            self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 390)
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-recipients-mobile.png"),
                full_page=True,
            )
            page.get_by_role("combobox", name=re.compile("^Formulario:")).click()
            page.get_by_role("option", name=other.name, exact=True).click()
            page.get_by_role("button", name="Ver configuración").click()
            expect(addresses).to_have_value("")
            page.get_by_role("combobox", name=re.compile("^Formulario:")).click()
            page.get_by_role("option", name=self.form.name, exact=True).click()
            page.get_by_role("button", name="Ver configuración").click()
            expect(addresses).to_have_value("equipo@example.com\njefe@example.com")
            addresses.fill("")
            page.get_by_label("Avisar cuando llegue una nueva respuesta").uncheck()
            page.get_by_role("button", name="Guardar destinatarios").click()
            expect(addresses).to_have_value("")
            expect(
                page.get_by_label("Avisar cuando llegue una nueva respuesta")
            ).not_to_be_checked()
            browser.close()

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
            state_picker = page.get_by_role("combobox", name=re.compile("^Estado:"))
            state_picker.click()
            expect(page.get_by_role("listbox", name="Estado", exact=True)).to_be_visible()
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-email-dropdown-desktop.png"),
                full_page=True,
            )
            state_picker.press("End")
            state_picker.press("Enter")
            expect(state_picker).to_have_accessible_name("Estado: Omitido")
            state_picker.click()
            state_picker.press("Home")
            state_picker.press("ArrowDown")
            state_picker.press("Escape")
            expect(state_picker).to_have_accessible_name("Estado: Omitido")
            expect(state_picker).to_be_focused()
            state_picker.click()
            page.get_by_role("option", name="Entregado", exact=True).click()
            expect(state_picker).to_have_accessible_name("Estado: Entregado")
            state_picker.click()
            expect(page.get_by_role("option", name="Entregado", exact=True)).to_have_attribute(
                "aria-selected", "true"
            )
            page.get_by_role("heading", name="Correos", exact=True).click()
            expect(state_picker).to_have_attribute("aria-expanded", "false")
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
            state_picker.click()
            dropdown = page.locator("#response-select-menu")
            expect(dropdown).to_be_visible()
            bounds = dropdown.bounding_box()
            self.assertGreaterEqual(bounds["x"], 0)
            self.assertLessEqual(bounds["x"] + bounds["width"], 390)
            self.assertGreaterEqual(bounds["y"], 0)
            self.assertLessEqual(bounds["y"] + bounds["height"], 844)
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-email-dropdown-mobile.png"),
                full_page=True,
            )
            state_picker.press("Escape")
            page.evaluate("document.documentElement.classList.add('dark')")
            state_picker.click()
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-email-dropdown-dark.png"),
                full_page=True,
            )
            state_picker.press("Tab")
            expect(dropdown).not_to_be_visible()
            page.evaluate("document.documentElement.classList.remove('dark')")
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
