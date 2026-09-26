from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group
from django.db.models import Count, Q
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


class UserStatusFilter(admin.SimpleListFilter):
    title = "estado"
    parameter_name = "is_active__exact"

    def lookups(self, request, model_admin):
        return (("1", "Activos"), ("0", "Inactivos"))

    def queryset(self, request, queryset):
        if self.value() in ("0", "1"):
            return queryset.filter(is_active=self.value() == "1")
        return queryset


@admin.register(User)
class UserAdmin(SuperuserOnlyMixin, DjangoUserAdmin, ModelAdmin):
    change_list_template = "admin/accounts/users/list.html"
    change_form_template = "admin/accounts/users/form.html"
    add_form_template = "admin/accounts/users/form.html"
    change_user_password_template = "admin/accounts/users/password.html"
    delete_confirmation_template = "admin/accounts/users/delete.html"
    delete_selected_confirmation_template = "admin/accounts/users/delete.html"
    object_history_template = "admin/accounts/users/history.html"
    list_per_page = 25
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
    list_filter = [RoleFilter, UserStatusFilter]
    filter_horizontal = ()
    readonly_fields = ["last_login", "date_joined"]

    @admin.display(description="Rol", ordering="is_superuser")
    def role_label(self, obj):
        return ADMINISTRATOR if obj.is_superuser else OPERATOR

    def get_queryset(self, request):
        return visible_users(super().get_queryset(request))

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        context = getattr(response, "context_data", None)
        if context is None or "cl" not in context:
            return response
        changelist = context["cl"]
        context["user_metrics"] = self.get_queryset(request).aggregate(
            total=Count("pk"),
            active=Count("pk", filter=Q(is_active=True)),
            administrators=Count("pk", filter=Q(is_superuser=True)),
            operators=Count("pk", filter=Q(is_superuser=False)),
        )
        context["user_role_choices"] = ROLE_CHOICES
        context["selected_user_role"] = request.GET.get("role", "")
        context["selected_user_active"] = request.GET.get("is_active__exact", "")
        page = changelist.page_num
        context["user_previous_url"] = (
            changelist.get_query_string({"p": page - 1}) if page > 1 else None
        )
        context["user_next_url"] = (
            changelist.get_query_string({"p": page + 1})
            if page < changelist.paginator.num_pages and not changelist.show_all
            else None
        )
        context["user_sort_links"] = {
            name: changelist.get_query_string(
                {"o": str(index) if request.GET.get("o") != str(index) else f"-{index}"},
                remove=["p"],
            )
            for index, name in enumerate(changelist.list_display)
            if name in {"username", "email", "role_label", "is_active"}
        }
        return response


admin.site.unregister(Group)
