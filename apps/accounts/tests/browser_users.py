import re
import tempfile
import uuid
from pathlib import Path

from django.contrib.auth.models import Group
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from playwright.sync_api import expect, sync_playwright

from apps.accounts.models import User
from apps.accounts.roles import ADMINISTRATOR, OPERATOR
from apps.submissions.models import Submission
from apps.submissions.tests.test_public import fixture


class UsersBrowserTests(StaticLiveServerTestCase):
    def test_create_filter_edit_password_delete_and_mobile(self):
        for role in (ADMINISTRATOR, OPERATOR):
            Group.objects.get_or_create(name=role)
        admin = User.objects.create_superuser(username="browser-admin", password=None)
        self.client.force_login(admin)
        errors = []
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
            page.on("pageerror", lambda error: errors.append(str(error)))
            url = self.live_server_url + reverse("admin:accounts_user_changelist")
            page.goto(url)
            expect(page.locator(".users-metrics article")).to_have_count(4)
            page.get_by_role("link", name="Crear usuario", exact=True).click()
            page.get_by_label("Nombre de usuario").fill("nuevo-browser")
            page.get_by_label("Dirección de correo electrónico").fill("new@example.com")
            page.locator("#id_password1").fill("Browser-safe-829!strong")
            page.locator("#id_password2").fill("Browser-safe-829!strong")
            page.get_by_role("button", name="Crear usuario", exact=True).click()
            expect(page.get_by_role("heading", name="Editar usuario", exact=True)).to_be_visible()
            page.locator("#id_first_name").fill("Persona")
            page.get_by_role("button", name="Guardar cambios", exact=True).click()
            page.get_by_role("combobox", name=re.compile("^Rol:")).press("Enter")
            page.get_by_role("combobox", name=re.compile("^Rol:")).press("End")
            page.get_by_role("combobox", name=re.compile("^Rol:")).press("Enter")
            page.get_by_role("button", name="Aplicar filtros").click()
            expect(page.locator(".users-table tbody tr")).to_have_count(1)
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-users-desktop.png"), full_page=True
            )
            page.get_by_role("link", name="Editar a nuevo-browser").click()
            page.get_by_role("link", name="Cambiar contraseña", exact=True).click()
            page.locator("#id_password1").fill("Changed-safe-829!strong")
            page.locator("#id_password2").fill("Changed-safe-829!strong")
            page.get_by_role("button", name="Guardar contraseña").click()
            expect(page.get_by_role("heading", name="Editar usuario", exact=True)).to_be_visible()
            login = browser.new_page()
            login.goto(self.live_server_url + reverse("admin:login"))
            login.locator("#id_username").fill("nuevo-browser")
            login.locator("#id_password").fill("Changed-safe-829!strong")
            login.locator('button[type="submit"]').click()
            expect(login).not_to_have_url(re.compile("/login/"))
            login.close()
            page.set_viewport_size({"width": 390, "height": 844})
            self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 390)
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-user-edit-mobile.png"), full_page=True
            )
            page.goto(url)
            self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 390)
            page.get_by_role("checkbox", name="Seleccionar a nuevo-browser", exact=True).check()
            page.get_by_role("combobox", name=re.compile("^Acción sobre")).click()
            page.get_by_role("option", name=re.compile("Eliminar")).click()
            page.get_by_role("button", name="Aplicar", exact=True).click()
            expect(page.get_by_role("button", name="Confirmar eliminación")).to_be_visible()
            page.get_by_role("button", name="Confirmar eliminación").click()
            expect(
                page.get_by_role("heading", name="Usuarios y permisos", exact=True)
            ).to_be_visible()
            browser.close()
        self.assertFalse(User.objects.filter(username="nuevo-browser").exists())
        self.assertFalse(errors, errors)

    def test_report_dropdowns_apply_filters_and_page_size(self):
        form, version, *_ = fixture()
        admin = form.created_by
        admin.is_superuser = True
        admin.save()
        Submission.objects.create(form=form, form_version=version, idempotency_key=uuid.uuid4())
        self.client.force_login(admin)
        errors = []
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
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(self.live_server_url + reverse("admin:submissions_submission_reports"))
            picker = page.get_by_role("combobox", name=re.compile("^Formulario:"))
            picker.click()
            page.get_by_role("option", name=form.name, exact=True).click()
            order = page.get_by_role("combobox", name=re.compile("^Ordenar por:"))
            order.press("Enter")
            order.press("End")
            order.press("Enter")
            page.get_by_role("button", name="Aplicar filtros").click()
            expect(page).to_have_url(re.compile(f"form={form.pk}.*orden=form"))
            page.get_by_role("combobox", name=re.compile("^Por página:")).click()
            page.get_by_role("option", name="10", exact=True).click()
            expect(page).to_have_url(re.compile("por_pagina=10"))
            page.get_by_role("combobox", name=re.compile("^Formulario:")).click()
            page.screenshot(
                path=str(Path(tempfile.gettempdir()) / "forms-reports-dropdown.png"), full_page=True
            )
            page.keyboard.press("Escape")
            page.set_viewport_size({"width": 390, "height": 844})
            self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 390)
            browser.close()
        self.assertFalse(errors, errors)
