from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.roles import ADMINISTRATOR, OPERATOR


class UsersInterfaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for role in (ADMINISTRATOR, OPERATOR):
            Group.objects.get_or_create(name=role)
        cls.admin = User.objects.create_superuser(
            username="ui-admin", password="Original-safe-829!"
        )
        cls.operator = User.objects.create_user(username="ui-operator", is_staff=True)
        cls.inactive = User.objects.create_user(
            username="ui-inactive", is_staff=True, is_active=False
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_filters_empty_values_and_metrics(self):
        url = reverse("admin:accounts_user_changelist")
        response = self.client.get(url, {"role": "", "is_active__exact": ""})
        self.assertContains(response, "Personas de la plataforma")
        self.assertEqual(response.context["user_metrics"]["total"], 3)
        response = self.client.get(url, {"role": OPERATOR, "is_active__exact": "0"})
        self.assertEqual(list(response.context["cl"].result_list), [self.inactive])
        self.assertEqual(response.context["user_metrics"]["total"], 3)

    def test_all_user_screens_render_and_edit_keeps_password(self):
        for route, args in (
            ("admin:accounts_user_add", []),
            ("admin:accounts_user_change", [self.operator.pk]),
            ("admin:auth_user_password_change", [self.operator.pk]),
            ("admin:accounts_user_history", [self.operator.pk]),
            ("admin:accounts_user_delete", [self.operator.pk]),
        ):
            with self.subTest(route=route):
                self.assertContains(self.client.get(reverse(route, args=args)), "users-page")
        password = self.admin.password
        response = self.client.post(
            reverse("admin:accounts_user_change", args=[self.admin.pk]),
            {
                "username": self.admin.username,
                "role": "Administrador",
                "is_active": "on",
                "_save": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.password, password)

    def test_bulk_delete_requires_confirmation_and_only_deletes_selected_user(self):
        url = reverse("admin:accounts_user_changelist")
        data = {"action": "delete_selected", "_selected_action": [str(self.inactive.pk)]}
        self.assertContains(self.client.post(url, {**data, "index": "0"}), "Confirmar eliminación")
        self.assertTrue(User.objects.filter(pk=self.inactive.pk).exists())
        self.assertEqual(self.client.post(url, {**data, "post": "yes"}).status_code, 302)
        self.assertFalse(User.objects.filter(pk=self.inactive.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.operator.pk).exists())

    def test_operator_cannot_access_user_management(self):
        self.client.force_login(self.operator)
        for route, args in (
            ("admin:accounts_user_changelist", []),
            ("admin:accounts_user_add", []),
            ("admin:accounts_user_change", [self.admin.pk]),
            ("admin:auth_user_password_change", [self.admin.pk]),
        ):
            self.assertEqual(self.client.get(reverse(route, args=args)).status_code, 403)
