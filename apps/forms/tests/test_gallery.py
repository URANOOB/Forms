from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User, Workspace
from apps.forms.models import Form, FormField, FormSection, FormVersion


class GalleryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Equipo", slug="equipo")
        cls.user = User.objects.create_user(
            username="editor", is_staff=True, workspace=cls.workspace
        )
        cls.user.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="forms",
                codename__in=["add_form", "change_form", "view_form"],
            )
        )
        cls.other = User.objects.create_user(username="colega", workspace=cls.workspace)
        for author, name in [(cls.user, "Zulu"), (cls.other, "Alfa")]:
            form = Form.objects.create(
                workspace=cls.workspace, name=name, slug=name.lower(), created_by=author
            )
            version = FormVersion.objects.create(form=form, version_number=1)
            section = FormSection.objects.create(form_version=version, title="Contacto")
            FormField.objects.create(
                form_version=version,
                section=section,
                stable_key="nombre",
                label="Campo de vista previa",
                field_type="SHORT_TEXT",
            )
        cls.url = reverse("admin:forms_form_changelist")

    def setUp(self):
        self.client.force_login(self.user)

    def test_gallery_filter_sort_and_previews_use_real_records(self):
        response = self.client.get(
            self.url, {"status__exact": "", "owner": "", "sort": "name", "q": ""}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [card["form"].name for card in response.context["cards"]], ["Alfa", "Zulu"]
        )
        self.assertContains(response, "Campo de vista previa")
        response = self.client.get(self.url, {"owner": "mine", "sort": "name"})
        self.assertEqual([card["form"].name for card in response.context["cards"]], ["Zulu"])
        self.assertContains(response, "No hay formularios", count=0)
        response = self.client.get(self.url, {"q": "no-existe"})
        self.assertContains(response, "No hay formularios para mostrar")

    def test_template_get_does_not_create_and_post_creates_draft_with_fields(self):
        url = reverse("admin:forms_form_add") + "?template=contact"
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(Form.objects.count(), 2)
        response = self.client.post(
            url,
            {
                "name": "Mis contactos",
                "slug": "mis-contactos",
                "workspace": self.workspace.pk,
                "description": "",
                "versions-TOTAL_FORMS": "0",
                "versions-INITIAL_FORMS": "0",
            },
        )
        self.assertEqual(response.status_code, 302)
        form = Form.objects.get(slug="mis-contactos")
        self.assertEqual(form.created_by_id, self.user.pk)
        self.assertEqual(form.status, "DRAFT")
        self.assertEqual(
            set(form.versions.get().fields.values_list("stable_key", flat=True)),
            {"nombre", "correo", "telefono", "mensaje"},
        )

    def test_create_opens_builder_and_saves_template_without_metadata_form(self):
        url = reverse("admin:forms_form_add")
        page = self.client.get(url, {"template": "contact"})
        self.assertContains(page, 'id="builder"')
        self.assertNotContains(page, 'id="id_slug"')
        self.assertEqual(Form.objects.count(), 2)
        data = page.context["builder_data"]
        self.assertEqual(len(data["sections"][0]["fields"]), 4)
        create = {
            "creation_token": page.context["creation_token"],
            "workspace": str(self.workspace.pk),
            "title": "Mis contactos",
        }
        response = self.client.post(url, create, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        result = response.json()
        retry = self.client.post(url, create, content_type="application/json")
        self.assertEqual(retry.json()["version"], result["version"])
        self.assertEqual(Form.objects.count(), 3)
        data.update(
            version=result["version"], fingerprint=result["fingerprint"], title="Mis contactos"
        )
        saved = self.client.post(
            result["editor_url"] + "save/", data, content_type="application/json"
        )
        self.assertEqual(saved.status_code, 200)
        form = Form.objects.get(name="Mis contactos")
        self.assertEqual(form.workspace_id, self.workspace.pk)
        self.assertEqual(form.status, "DRAFT")
        self.assertTrue(form.slug.startswith("formulario-"))
        self.assertEqual(form.versions.get().fields.count(), 4)
        self.assertEqual(
            self.client.post(url, create, content_type="application/json").status_code, 409
        )

    def test_new_builder_workspace_and_token_cannot_be_forged(self):
        url = reverse("admin:forms_form_add")
        page = self.client.get(url)
        foreign = Workspace.objects.create(name="Ajeno", slug="ajeno")
        data = {"creation_token": page.context["creation_token"], "workspace": str(foreign.pk)}
        self.assertEqual(
            self.client.post(url, data, content_type="application/json").status_code, 400
        )
        data.update(workspace=str(self.workspace.pk), creation_token="invalid")
        self.assertEqual(
            self.client.post(url, data, content_type="application/json").status_code, 400
        )
        self.assertEqual(Form.objects.count(), 2)
        admin = User.objects.create_superuser(username="super", password=None)
        self.client.force_login(admin)
        page = self.client.get(url)
        self.assertContains(page, 'id="builder"')
        self.assertEqual(page.context["selected_workspace"], "")
        self.assertEqual(len(page.context["workspaces"]), 2)

    def test_viewer_has_no_creation_or_state_change_controls(self):
        self.user.user_permissions.set(
            Permission.objects.filter(content_type__app_label="forms", codename="view_form")
        )
        response = self.client.get(self.url)
        self.assertNotContains(response, 'id="template-grid"')
        self.assertNotContains(response, 'value="publish_forms"')
        response = self.client.post(reverse("admin:forms_form_add") + "?template=contact", {})
        self.assertEqual(response.status_code, 403)
