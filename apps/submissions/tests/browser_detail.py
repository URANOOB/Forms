"""Browser coverage for reading a response, navigation, review actions and attachments."""

import tempfile
import uuid
from pathlib import Path

from django.contrib.auth.models import Permission
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from playwright.sync_api import expect, sync_playwright

from apps.forms.models import FieldOption, FormField, FormSection
from apps.forms.publication import publish_form
from apps.submissions.models import Submission, SubmissionAnswer, SubmissionFile
from apps.submissions.tests.test_public import fixture


class DetailBrowserTests(StaticLiveServerTestCase):
    def test_response_reading_navigation_actions_and_mobile(self):
        form, version, name, choice, email = fixture()
        version.title = "Reporte de Casos Incidentes de Cáncer"
        version.save()
        name.section.title = "Sección 1"
        name.section.save()
        fields = [(name, "María Rodríguez"), (choice, "si"), (email, None)]

        def field(section, label, kind, value, configuration=None):
            result = FormField.objects.create(
                form_version=version,
                section=section,
                label=label,
                stable_key="field_" + uuid.uuid4().hex,
                field_type=kind,
                order=len(fields),
                configuration=configuration or {},
            )
            fields.append((result, value))
            return result

        field(name.section, "Número de documento", "NUMBER", 1312441240.0)
        field(name.section, "Fecha de nacimiento", "DATE", "1985-09-10")
        field(name.section, "Teléfono actualizado", "PHONE", "3101234567")
        field(
            name.section,
            "Dirección actualizada",
            "SHORT_TEXT",
            "Carrera 123 # 45-67 apartamento 302",
        )
        diagnosis = FormSection.objects.create(
            form_version=version, title="Diagnóstico confirmado", order=1
        )
        status = field(diagnosis, "Tipo de diagnóstico", "SINGLE_CHOICE", "confirmed")
        FieldOption.objects.create(field=status, label="Confirmado", value="confirmed")
        field(diagnosis, "Fecha de diagnóstico", "DATE", "2026-09-19")
        field(
            diagnosis,
            "Observaciones",
            "LONG_TEXT",
            "Documentación recibida para la revisión.\n"
            "Pendiente de comprobación por el equipo responsable.",
        )
        docs = FormSection.objects.create(form_version=version, title="Documentos", order=2)
        uploaded = field(docs, "Soporte de la solicitud", "DOCUMENT", [])
        publish_form(form.pk)
        response = Submission.objects.create(
            form=form, form_version=version, idempotency_key=uuid.uuid4()
        )
        for item, value in fields:
            answer = SubmissionAnswer.objects.create(submission=response, field=item, value=value)
            if item == uploaded:
                attachment = SubmissionFile.objects.create(
                    answer=answer,
                    file="fake/soporte.txt",
                    original_name="Soporte de la solicitud.txt",
                    size=28,
                )
        user = form.created_by
        user.user_permissions.add(
            *Permission.objects.filter(
                codename__in=[
                    "view_submission",
                    "change_submission",
                    "delete_submission",
                    "view_formversion",
                ]
            )
        )
        self.client.force_login(user)
        url = self.live_server_url + reverse(
            "admin:submissions_submission_detail", args=[response.pk]
        )
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
            page.route(
                "**" + attachment.get_absolute_url() + "*",
                lambda route: route.fulfill(
                    status=200,
                    content_type="text/plain",
                    headers={"Content-Disposition": 'attachment; filename="soporte.txt"'},
                    body="Documento de prueba recibido.",
                ),
            )
            page.goto(url)
            expect(page.locator(".response-detail-title h1")).to_have_text(version.title)
            expect(page.locator(".response-section[open]")).to_have_count(3)
            expect(page.locator(".response-details")).to_contain_text("1.312.441.240")
            expect(page.locator(".response-details")).to_contain_text("19 sep 2026")
            expect(page.locator(".response-details")).to_contain_text("No proporcionado")
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-response-detail-desktop.png"),
                full_page=True,
            )
            page.get_by_role("button", name="Contraer todo").click()
            expect(page.locator(".response-section[open]")).to_have_count(0)
            page.get_by_role("navigation", name="Contenido de la respuesta").get_by_role(
                "link", name="03 Documentos"
            ).click()
            expect(page.locator(".response-section[open]")).to_have_count(1)
            expect(page.locator(".response-section[open] summary")).to_be_focused()
            page.get_by_role("button", name="Vista previa de Soporte de la solicitud.txt").click()
            expect(page.locator(".response-document-body pre")).to_have_text(
                "Documento de prueba recibido."
            )
            page.get_by_role("button", name="Cerrar vista previa").click()
            page.get_by_role("button", name="Expandir todo").click()
            expect(page.locator(".response-section[open]")).to_have_count(3)
            expect(page.get_by_role("link", name="Eliminar respuesta")).not_to_be_visible()
            page.get_by_role("button", name="Más acciones").click()
            expect(page.get_by_role("link", name="Ver versión 1")).to_be_visible()
            with page.expect_download() as download:
                page.get_by_role("link", name="Descargar respuesta (CSV)").click()
            self.assertTrue(download.value.suggested_filename.endswith(".csv"))
            page.keyboard.press("Escape")
            page.get_by_role("button", name="Iniciar revisión", exact=True).click()
            expect(page.locator(".response-detail-meta .response-status")).to_have_text(
                "En revisión"
            )
            form_ui = page.locator("[data-review-form]")
            expect(form_ui.locator('[type="submit"]')).to_have_text("Validar respuesta")
            form_ui.locator("select").select_option("REJECTED")
            expect(form_ui.locator('[type="submit"]')).to_have_text("Rechazar respuesta")
            expect(form_ui.locator('[type="submit"]')).to_have_class("review-primary review-danger")
            expect(form_ui.locator("textarea")).to_have_attribute("required", "")
            form_ui.locator("textarea").fill("El archivo aportado no corresponde a la solicitud.")
            form_ui.locator('[type="submit"]').click()
            expect(page.locator(".response-detail-meta .response-status")).to_have_text("Rechazada")
            page.locator("#response-history summary").click()
            expect(page.locator("#response-history")).to_contain_text("El archivo aportado")
            expect(page.locator("#response-history li")).to_have_count(3)
            page.locator("#response-history summary").click()
            page.evaluate("document.documentElement.classList.add('dark')")
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-response-detail-dark.png"),
                full_page=True,
            )
            page.evaluate("document.documentElement.classList.remove('dark')")
            page.set_viewport_size({"width": 390, "height": 844})
            self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-response-detail-mobile.png"),
                full_page=True,
            )
            page.get_by_role("button", name="Abrir o cerrar navegación").click()
            expect(page.locator("#nav-sidebar")).to_be_visible()
            browser.close()
        self.assertFalse(errors, errors)
        response.refresh_from_db()
        self.assertEqual(response.status, "REJECTED")
        self.assertEqual(response.answers.get(field=name).value, "María Rodríguez")
