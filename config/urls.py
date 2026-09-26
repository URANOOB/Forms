from django.contrib import admin
from django.urls import include, path

from apps.accounts.platform import platform_activity, platform_search
from apps.forms.builder_views import form_image
from apps.submissions.views import public_form, response_file, thanks

from .views import home, public_information

admin.site.site_title = "Formularios institucionales"
admin.site.site_header = "Formularios"
admin.site.index_title = "Inicio"

handler404 = "config.views.page_not_found"

urlpatterns = [
    path("", home, name="home"),
    path("informacion/", public_information, name="public_information"),
    path("response-files/<uuid:file_id>/", response_file, name="response_file"),
    path("form-images/<uuid:image_id>/", form_image, name="form_image"),
    path("admin/platform-search/", admin.site.admin_view(platform_search), name="platform_search"),
    path(
        "admin/platform-activity/",
        admin.site.admin_view(platform_activity),
        name="platform_activity",
    ),
    path("admin/", admin.site.urls),
    path("webhooks/", include("apps.notifications.urls")),
    path("f/enviado/", thanks, name="submission_thanks"),
    path("f/<uuid:form_id>/", public_form, name="public_form"),
    path("f/<slug:workspace_slug>/<slug:slug>/", public_form, name="legacy_public_form"),
]
