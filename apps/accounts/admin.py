from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import User


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
        return False


@admin.register(User)
class UserAdmin(SuperuserOnlyMixin, DjangoUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    fieldsets = DjangoUserAdmin.fieldsets
    add_fieldsets = DjangoUserAdmin.add_fieldsets
    list_display = ["username", "email", "is_staff", "is_active"]


admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(SuperuserOnlyMixin, DjangoGroupAdmin, ModelAdmin):
    pass
