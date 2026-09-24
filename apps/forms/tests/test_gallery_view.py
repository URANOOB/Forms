import uuid
from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.forms.models import Form, FormVersion
from apps.forms.publication import publish_form
from apps.submissions.models import Submission
from apps.submissions.tests.test_public import fixture


class GalleryViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.form, cls.version, *_ = fixture()
        cls.user = cls.form.created_by
        cls.user.first_name, cls.user.last_name = "Will", "Galeano"
        cls.user.save()
        cls.user.user_permissions.add(
            *Permission.objects.filter(
                codename__in=[
                    "view_form",
                    "change_form",
                    "add_form",
                    "view_submission",
                ]
            )
        )
        cls.url = reverse("admin:forms_form_changelist")

    def setUp(self):
        self.client.force_login(self.user)

    def make_form(self, name, **kwargs):
        return Form.objects.create(
            workspace=self.form.workspace,
            created_by=kwargs.pop("created_by", self.user),
            name=name,
            slug="form-" + uuid.uuid4().hex,
            **kwargs,
        )

    def test_cards_count_all_versions_and_display_real_author(self):
        publish_form(self.form.pk)
        other_version = FormVersion.objects.create(form=self.form, version_number=2)
        for version in [self.version, self.version, other_version]:
            Submission.objects.create(
                form=self.form, form_version=version, idempotency_key=uuid.uuid4()
            )
        self.make_form("Sin respuestas")
        response = self.client.get(self.url)
        cards = {card["form"].pk: card for card in response.context["cards"]}
        self.assertEqual(cards[self.form.pk]["response_count"], 3)
        self.assertEqual(cards[self.form.pk]["owner_name"], "Will Galeano")
        self.assertContains(response, "3 respuestas")
        self.assertContains(response, "0 respuestas")
        self.assertContains(response, "2 formularios encontrados")
        self.assertNotContains(response, 'class="gallery-pagination"')
        self.assertContains(response, "Actualizado hace")

    def test_search_owner_status_sort_and_clear_keep_search(self):
        other = User.objects.create_user(username="otra-persona")
        self.make_form("Solicitud Alfa")
        self.make_form("Solicitud Beta", created_by=other)
        self.make_form("Solicitud Archivada", status="ARCHIVED")
        response = self.client.get(
            self.url,
            {
                "q": "Solicitud",
                "owner": "mine",
                "status__exact": "DRAFT",
                "sort": "name",
                "updated": "week",
            },
        )
        self.assertEqual([c["form"].name for c in response.context["cards"]], ["Solicitud Alfa"])
        self.assertEqual(response.context["gallery_filter_count"], 4)
        self.assertEqual(
            parse_qs(urlparse(response.context["gallery_clear_url"]).query), {"q": ["Solicitud"]}
        )

    @patch("apps.forms.gallery.timezone.now")
    def test_date_filter_includes_calendar_boundaries_and_ignores_unknown_period(self, now):
        now.return_value = timezone.make_aware(datetime(2026, 9, 23, 12))
        cases = [
            ("Hoy", 0),
            ("Séptimo día", 6),
            ("Octavo día", 7),
            ("Día treinta", 29),
            ("Antiguo", 30),
        ]
        Form.objects.filter(pk=self.form.pk).update(deleted_at=now.return_value)
        for label, days in cases:
            form = self.make_form(label)
            Form.objects.filter(pk=form.pk).update(
                updated_at=now.return_value.replace(hour=0) - timedelta(days=days)
            )
        for period, expected in [
            ("today", {"Hoy"}),
            ("week", {"Hoy", "Séptimo día"}),
            ("month", {"Hoy", "Séptimo día", "Octavo día", "Día treinta"}),
            ("unknown", {label for label, _ in cases}),
        ]:
            with self.subTest(period=period):
                response = self.client.get(self.url, {"updated": period})
                self.assertEqual(response.status_code, 200)
                self.assertEqual({c["form"].name for c in response.context["cards"]}, expected)

    def test_pagination_retains_search_and_filters(self):
        for index in range(27):
            self.make_form(f"Solicitud {index:02d}")
        params = {"q": "Solicitud", "owner": "mine", "updated": "week", "sort": "name"}
        first = self.client.get(self.url, params)
        self.assertEqual(len(first.context["cards"]), 25)
        self.assertContains(first, "27 formularios encontrados")
        next_query = parse_qs(urlparse(first.context["gallery_next_url"]).query)
        self.assertEqual(
            next_query, {**{key: [value] for key, value in params.items()}, "p": ["2"]}
        )
        second = self.client.get(self.url, {**params, "p": 2})
        self.assertEqual(len(second.context["cards"]), 2)
        self.assertEqual(second.context["gallery_next_url"], "")
        self.assertContains(second, "Página 2 de 2")
        self.assertIn("p=1", second.context["gallery_previous_url"])

    def test_metadata_does_not_add_one_query_per_card(self):
        with CaptureQueriesContext(connection) as single:
            self.client.get(self.url)
        for index in range(10):
            form = self.make_form(f"Formulario {index}")
            FormVersion.objects.create(form=form, version_number=1)
        with CaptureQueriesContext(connection) as multiple:
            response = self.client.get(self.url)
        self.assertEqual(len(response.context["cards"]), 11)
        self.assertLessEqual(len(multiple), len(single))

    def test_readonly_empty_and_deleted_forms(self):
        self.user.user_permissions.set(Permission.objects.filter(codename="view_form"))
        self.make_form("Eliminado", deleted_at=timezone.now())
        response = self.client.get(self.url)
        self.assertNotContains(response, 'class="create-form-button"')
        self.assertNotContains(response, 'value="delete_forms"')
        self.assertNotContains(response, ">Ver respuestas</a>")
        self.assertEqual(len(response.context["cards"]), 1)
        response = self.client.get(self.url, {"q": "nunca-existe"})
        self.assertContains(response, "0 formularios encontrados")
        self.assertContains(response, "No hay formularios para mostrar")
