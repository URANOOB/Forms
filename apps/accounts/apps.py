from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    verbose_name = "Institución"

    def ready(self):
        from . import sessions  # noqa: F401
