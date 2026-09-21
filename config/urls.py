from django.contrib import admin
from django.urls import path

from apps.forms.builder_views import form_image
from apps.submissions.views import public_form, response_file, thanks

admin.site.site_title = "Formularios institucionales"
admin.site.site_header = "Formularios"
admin.site.index_title = "Inicio"

urlpatterns = [
    path("response-files/<uuid:file_id>/", response_file, name="response_file"),
    path("form-images/<uuid:image_id>/", form_image, name="form_image"),
    path("admin/", admin.site.urls),
    path("f/enviado/", thanks, name="submission_thanks"),
    path("f/<uuid:form_id>/", public_form, name="public_form"),
    path("f/<slug:workspace_slug>/<slug:slug>/", public_form, name="legacy_public_form"),
]
