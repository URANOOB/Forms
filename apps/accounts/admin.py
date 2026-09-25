from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm

from .forms import PlatformUserChangeForm, PlatformUserCreationForm
from .models import User
from .roles import ADMINISTRATOR, OPERATOR, ROLE_CHOICES, visible_users


class RoleFilter(admin.SimpleListFilter):
    title = "rol"
    parameter_name = "role"

    def lookups(self, request, model_admin):
        return ROLE_CHOICES

    def queryset(self, request, queryset):
        if self.value() in (ADMINISTRATOR, OPERATOR):
            return queryset.filter(is_superuser=self.value() == ADMINISTRATOR)
        return queryset


class SuperuserOnlyMixin:
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)


@admin.register(User)
class UserAdmin(SuperuserOnlyMixin, DjangoUserAdmin, ModelAdmin):
    form = PlatformUserChangeForm
    add_form = PlatformUserCreationForm
    change_password_form = AdminPasswordChangeForm
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Información personal", {"fields": ("first_name", "last_name", "email")}),
        ("Acceso a la plataforma", {"fields": ("role", "is_active")}),
        ("Fechas importantes", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "first_name",
                    "last_name",
                    "password1",
                    "password2",
                    "role",
                    "is_active",
                ),
            },
        ),
    )
    list_display = ["username", "email", "role_label", "is_active"]
    list_filter = [RoleFilter, "is_active"]
    filter_horizontal = ()
    readonly_fields = ["last_login", "date_joined"]

    @admin.display(description="Rol", ordering="is_superuser")
    def role_label(self, obj):
        return ADMINISTRATOR if obj.is_superuser else OPERATOR

    def get_queryset(self, request):
        return visible_users(super().get_queryset(request))


admin.site.unregister(Group)
