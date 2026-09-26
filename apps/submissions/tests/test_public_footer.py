from django.test import TestCase, override_settings
from django.urls import reverse


class PublicFooterTests(TestCase):
    @override_settings(
        PUBLIC_INSTITUTION_NAME="LogicForms", PUBLIC_SUPPORT_EMAIL="", PUBLIC_PRIVACY_URL=""
    )
    def test_information_is_public_and_no_fictitious_contact_is_rendered(self):
        response = self.client.get(reverse("public_information"))
        self.assertContains(response, "Información y ayuda")
        for section in ("privacidad", "accesibilidad", "ayuda"):
            self.assertContains(response, f'id="{section}"')
        self.assertContains(response, "LogicForms")
        self.assertNotContains(response, "mailto:")
        self.assertContains(response, 'target="_blank" rel="noopener"')

    @override_settings(
        PUBLIC_INSTITUTION_NAME="Entidad de prueba",
        PUBLIC_SUPPORT_EMAIL="support@example.com",
        PUBLIC_PRIVACY_URL="https://example.com/privacy",
    )
    def test_institution_contact_and_official_privacy_are_configurable(self):
        response = self.client.get(reverse("public_information"))
        self.assertContains(response, "Entidad de prueba")
        self.assertContains(response, "mailto:support@example.com")
        self.assertContains(response, "https://example.com/privacy")
