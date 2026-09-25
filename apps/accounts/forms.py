from django import forms
from unfold.forms import UserChangeForm, UserCreationForm
from unfold.widgets import UnfoldAdminSelectWidget

from .models import User
from .roles import ADMINISTRATOR, OPERATOR, ROLE_CHOICES, assign_role


def role_field():
    return forms.ChoiceField(
        label="Rol",
        choices=ROLE_CHOICES,
        initial=OPERATOR,
        widget=UnfoldAdminSelectWidget,
        help_text=(
            "Administrador: acceso completo, incluidos usuarios y permisos. "
            "Operador: gestiona formularios y respuestas; sin purgado definitivo "
            "ni gestión de usuarios o permisos."
        ),
    )


class RoleFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance._state.adding:
            self.initial["role"] = ADMINISTRATOR if self.instance.is_superuser else OPERATOR

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = True
        user.is_superuser = self.cleaned_data["role"] == ADMINISTRATOR
        if commit:
            user.save()
            self.save_m2m()
        return user

    def _save_m2m(self):
        super()._save_m2m()
        assign_role(self.instance, self.cleaned_data["role"])


class PlatformUserChangeForm(RoleFormMixin, UserChangeForm):
    role = role_field()

    class Meta(UserChangeForm.Meta):
        model = User
        fields = ("username", "password", "first_name", "last_name", "email", "is_active")


class PlatformUserCreationForm(RoleFormMixin, UserCreationForm):
    role = role_field()
    usable_password = None

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "first_name", "last_name", "is_active")
