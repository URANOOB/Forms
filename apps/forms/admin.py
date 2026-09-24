from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.views.decorators.cache import never_cache
from unfold.admin import ModelAdmin, TabularInline

from apps.accounts.models import legacy_form_container

from .builder_views import editor_view, new_editor_view
from .catalog_views import import_catalog_view
from .gallery import GalleryChangeList, filter_updated, gallery_context
from .models import (
    ConditionalRule,
    FieldOption,
    Form,
    FormField,
    FormImage,
    FormSection,
    FormVersion,
)
from .presets import PRESETS, create_preset_fields
from .publication import delete_form, publish_form, set_form_status


class PlatformAdmin(ModelAdmin):
    list_per_page = 25

    def has_delete_permission(self, request, obj=None):
        return False


class VersionInline(TabularInline):
    model = FormVersion
    fk_name = "form"
    fields = ["version_number", "status", "schema_version", "created_at", "published_at"]
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("forms.view_form")

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Form)
class FormAdmin(PlatformAdmin):
    list_display = ["name", "status", "active_version", "public_link", "updated_at"]
    change_form_template = "admin/forms/change_form.html"
    change_list_template = "admin/forms/gallery.html"
    list_fullwidth = True
    list_filter = ["status"]
    search_fields = ["name", "slug"]
    search_help_text = "Buscar formularios"
    list_select_related = ["workspace", "created_by", "active_version__form"]
    list_per_page = 25
    readonly_fields = ["id", "status", "active_version", "created_by", "created_at", "updated_at"]
    fields = [
        "name",
        "description",
        "status",
        "active_version",
        "created_by",
        "created_at",
        "updated_at",
    ]
    inlines = [VersionInline]
    actions = ["publish_forms", "pause_forms", "archive_forms", "delete_forms"]

    def get_urls(self):
        urls = [
            path(
                "import-catalog/",
                self.admin_site.admin_view(lambda request: import_catalog_view(request, self)),
                name="forms_form_import_catalog",
            )
        ]
        for operation in (
            "edit",
            "save",
            "publish",
            "pause",
            "resume",
            "unpublish",
            "preview",
            "image",
            "responses",
        ):

            def view(request, object_id, operation=operation):
                return editor_view(self, request, object_id, operation)

            suffix = "" if operation == "edit" else f"{operation}/"
            urls.append(
                path(
                    f"<uuid:object_id>/builder/{suffix}",
                    self.admin_site.admin_view(never_cache(view)),
                    name=f"forms_form_builder_{operation}",
                )
            )
        return urls + super().get_urls()

    def response_add(self, request, obj, post_url_continue=None):
        if self.has_change_permission(request, obj):
            return redirect("admin:forms_form_builder_edit", obj.pk)
        return super().response_add(request, obj, post_url_continue)

    def get_changelist(self, request, **kwargs):
        return GalleryChangeList

    def get_queryset(self, request):
        queryset = super().get_queryset(request).filter(deleted_at__isnull=True)
        if request.GET.get("owner") == "mine":
            queryset = queryset.filter(created_by=request.user)
        return filter_updated(queryset, request.GET.get("updated"))

    def get_ordering(self, request):
        return {"name": ["name", "id"], "oldest": ["updated_at", "id"]}.get(
            request.GET.get("sort"), ["-updated_at", "id"]
        )

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        if (
            hasattr(response, "context_data")
            and response.context_data
            and "cl" in response.context_data
        ):
            response.context_data.update(gallery_context(request, response.context_data["cl"]))
            response.context_data["has_change_permission"] = self.has_change_permission(request)
        return response

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        preset = PRESETS.get(request.GET.get("template"))
        if preset:
            initial.update(name=preset["name"], description=preset["description"])
        return initial

    def add_view(self, request, form_url="", extra_context=None):
        if request.method == "GET" or request.content_type == "application/json":
            return new_editor_view(self, request)
        context = dict(extra_context or {})
        context["selected_preset"] = PRESETS.get(request.GET.get("template"))
        return super().add_view(request, form_url, context)

    @admin.display(description="Enlace público")
    def public_link(self, obj):
        if obj.status != Form.Status.PUBLISHED:
            return "Disponible al publicar"
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">Abrir formulario ↗</a>',
            obj.get_absolute_url(),
        )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        obj = self.get_object(request, object_id)
        extra_context = dict(extra_context or {})
        if obj and self.has_view_permission(request, obj):
            extra_context["share_url"] = request.build_absolute_uri(obj.get_absolute_url())
            extra_context["is_published"] = obj.status == Form.Status.PUBLISHED
            extra_context["can_publish"] = obj.status != Form.Status.ARCHIVED
            if request.user.has_perm("submissions.view_submission"):
                extra_context["responses_url"] = (
                    reverse("admin:submissions_submission_changelist") + f"?form={obj.pk}"
                )
        return super().change_view(request, object_id, form_url, extra_context)

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
            obj.workspace = legacy_form_container()
            obj.slug = f"formulario-{obj.pk}"
            super().save_model(request, obj, form, change)
        else:
            current = Form.objects.select_for_update().get(pk=obj.pk)
            obj.status = current.status
            obj.active_version_id = current.active_version_id
            obj.slug = current.slug
            obj.save(update_fields=["name", "description", "updated_at"])
        if not change:
            version = FormVersion.objects.create(form=obj, version_number=1)
            create_preset_fields(version, request.GET.get("template"))

    @admin.action(description="Archivar formularios seleccionados", permissions=["change"])
    def archive_forms(self, request, queryset):
        self.apply_action(request, queryset, "archive")

    @admin.action(description="Eliminar formularios seleccionados", permissions=["change"])
    def delete_forms(self, request, queryset):
        forms = [form for form in queryset if self.has_change_permission(request, form)]
        if not forms:
            return None
        if request.POST.get("confirm_form_delete") != "yes":
            return TemplateResponse(
                request,
                "admin/forms/confirm_delete.html",
                {
                    **self.admin_site.each_context(request),
                    "opts": self.model._meta,
                    "title": "Eliminar formulario",
                    "forms_to_delete": forms,
                },
            )
        for form in forms:
            deleted = delete_form(form.pk)
            self.log_change(request, deleted, "Eliminó el formulario; respuestas conservadas.")
        self.message_user(
            request,
            "Formulario eliminado. Sus respuestas se conservan en Respuestas.",
            messages.SUCCESS,
        )
        return None

    @admin.action(description="Publicar y habilitar enlace público", permissions=["change"])
    def publish_forms(self, request, queryset):
        self.apply_action(request, queryset, "publish")

    @admin.action(description="Pausar recepción de respuestas", permissions=["change"])
    def pause_forms(self, request, queryset):
        self.apply_action(request, queryset, "pause")

    def apply_action(self, request, queryset, action):
        for form in queryset:
            if self.has_change_permission(request, form):
                try:
                    if action == "publish":
                        updated = publish_form(form.pk)
                    else:
                        updated = set_form_status(
                            form.pk, "PAUSED" if action == "pause" else "ARCHIVED"
                        )
                except ValidationError as error:
                    self.message_user(request, "; ".join(error.messages), messages.ERROR)
                else:
                    self.log_change(request, updated, f"Estado: {updated.get_status_display()}")
                    self.message_user(
                        request,
                        f"{updated.name}: {updated.get_status_display()}.",
                        messages.SUCCESS,
                    )

    def response_change(self, request, obj):
        if "_publish" in request.POST or "_pause" in request.POST:
            self.apply_action(request, [obj], "publish" if "_publish" in request.POST else "pause")
        return super().response_change(request, obj)


class SchemaAdmin(PlatformAdmin):
    parent_fields = ("form_version",)
    readonly_fields = ["id"]
    actions = None

    def get_version(self, obj):
        return obj if isinstance(obj, FormVersion) else obj.get_version()

    def has_change_permission(self, request, obj=None):
        if obj:
            version = self.get_version(obj)
            if version.status != FormVersion.Status.DRAFT or version.form.deleted_at:
                return False
        return super().has_change_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        return [*self.readonly_fields, *(self.parent_fields if obj else ())]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        related = db_field.remote_field.model
        if related in (Form, FormVersion, FormSection, FormField, FormImage):
            queryset = related.objects.all()
            parent = {Form: "", FormVersion: "form__", FormImage: "form__"}.get(
                related, "form_version__form__"
            )
            queryset = queryset.filter(**{f"{parent}deleted_at__isnull": True})
            if related == FormVersion:
                queryset = queryset.filter(status="DRAFT").select_related("form")
            elif related in (FormSection, FormField):
                queryset = queryset.filter(form_version__status="DRAFT")
            if self.model == FieldOption and related == FormField:
                queryset = queryset.filter(field_type__in=["SINGLE_CHOICE", "MULTIPLE_CHOICE"])
            kwargs["queryset"] = queryset
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(FormVersion)
class FormVersionAdmin(SchemaAdmin):
    parent_fields = ("form", "version_number")
    list_display = ["form", "version_number", "status", "published_at"]
    list_filter = ["status"]
    search_fields = ["form__name", "form__slug"]
    list_select_related = ["form", "form__workspace"]
    readonly_fields = ["id", "status", "published_at", "created_at", "schema_version"]

    def has_add_permission(self, request):
        # Las versiones se crean desde el constructor.
        return False


@admin.register(FormSection)
class FormSectionAdmin(SchemaAdmin):
    list_display = ["title", "form_version", "order"]
    search_fields = ["title", "form_version__form__name"]
    list_select_related = ["form_version", "form_version__form"]


@admin.register(FormField)
class FormFieldAdmin(SchemaAdmin):
    list_display = ["label", "stable_key", "field_type", "required", "section", "order"]
    list_filter = ["field_type", "required"]
    search_fields = ["label", "stable_key", "form_version__form__name"]
    list_select_related = ["section", "form_version", "form_version__form"]

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        # Evitar invalidar opciones y reglas existentes cambiando el tipo en este admin básico.
        return [*fields, *(["field_type", "stable_key"] if obj else [])]


@admin.register(FieldOption)
class FieldOptionAdmin(SchemaAdmin):
    parent_fields = ("field",)
    list_display = ["label", "value", "field", "order", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["label", "value", "field__label"]
    list_select_related = ["field", "field__form_version", "field__form_version__form"]


@admin.register(ConditionalRule)
class ConditionalRuleAdmin(SchemaAdmin):
    list_display = [
        "source_field",
        "operator",
        "action",
        "target_field",
        "target_section",
        "group_key",
        "group_operator",
        "order",
    ]
    list_filter = ["operator", "action", "group_operator"]
    search_fields = ["source_field__label", "group_key", "form_version__form__name"]
    list_select_related = [
        "source_field",
        "target_field",
        "target_section",
        "form_version",
        "form_version__form",
    ]
