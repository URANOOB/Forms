from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth.models import Group
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.roles import ADMINISTRATOR, OPERATOR


class AdminSafetyTests(TestCase):
    def setUp(self):
        Group.objects.get_or_create(name=ADMINISTRATOR)
        Group.objects.get_or_create(name=OPERATOR)
        self.admin = User.objects.create_superuser(username="only-admin")
        self.client.force_login(self.admin)

    def test_last_admin_cannot_be_demoted_or_disabled(self):
        url = reverse("admin:accounts_user_change", args=[self.admin.pk])
        for role, active in [(OPERATOR, True), (ADMINISTRATOR, False)]:
            result = self.client.post(
                url,
                {
                    "username": self.admin.username,
                    "role": role,
                    **({"is_active": "on"} if active else {}),
                },
            )
            self.assertContains(result, "Debe quedar al menos un administrador activo")
            self.admin.refresh_from_db()
            self.assertTrue(self.admin.is_superuser and self.admin.is_active)

    def test_last_admin_individual_and_bulk_deletion_are_blocked(self):
        response = self.client.post(
            reverse("admin:accounts_user_delete", args=[self.admin.pk]), {"post": "yes"}
        )
        self.assertContains(response, "Debe quedar al menos un administrador activo")
        response = self.client.post(
            reverse("admin:accounts_user_changelist"),
            {
                "action": "delete_selected",
                "_selected_action": [str(self.admin.pk)],
                "post": "yes",
            },
        )
        self.assertContains(response, "Debe quedar al menos un administrador activo")
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_another_active_staff_admin_allows_change(self):
        User.objects.create_superuser(username="recovery-admin")
        response = self.client.post(
            reverse("admin:accounts_user_change", args=[self.admin.pk]),
            {
                "username": self.admin.username,
                "role": OPERATOR,
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_superuser)


class ConcurrentAdminSafetyTests(TransactionTestCase):
    def test_simultaneous_self_demotions_leave_one_administrator(self):
        Group.objects.get_or_create(name=ADMINISTRATOR)
        Group.objects.get_or_create(name=OPERATOR)
        admins = [User.objects.create_superuser(username=f"admin{i}") for i in range(2)]
        clients = [Client(), Client()]
        for client, user in zip(clients, admins):
            client.force_login(user)
        ready = Barrier(2)

        def demote(index):
            close_old_connections()
            try:
                ready.wait(timeout=10)
                user = admins[index]
                return (
                    clients[index]
                    .post(
                        reverse("admin:accounts_user_change", args=[user.pk]),
                        {
                            "username": user.username,
                            "role": OPERATOR,
                            "is_active": "on",
                        },
                    )
                    .status_code
                )
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(demote, range(2)))
        self.assertEqual(sorted(statuses), [200, 302])
        self.assertEqual(
            User.objects.filter(is_superuser=True, is_active=True, is_staff=True).count(), 1
        )
