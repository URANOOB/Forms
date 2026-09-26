from django.conf import settings


def public_footer(request):
    return {
        "public_institution_name": settings.PUBLIC_INSTITUTION_NAME,
        "public_support_email": settings.PUBLIC_SUPPORT_EMAIL,
        "public_privacy_url": settings.PUBLIC_PRIVACY_URL,
    }
