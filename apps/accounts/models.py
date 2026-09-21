import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class Workspace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField("nombre", max_length=180)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField("activo", default=True)
    created_at = models.DateTimeField("creado el", auto_now_add=True)
    updated_at = models.DateTimeField("actualizado el", auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "espacio de trabajo"
        verbose_name_plural = "espacios de trabajo"

    def __str__(self):
        return self.name


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="espacio de trabajo",
    )

    class Meta(AbstractUser.Meta):
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"


def legacy_form_container():
    """Internal FK compatibility only; no longer a tenancy or permission boundary."""
    workspace, _ = Workspace.objects.get_or_create(
        slug="formularios", defaults={"name": "Formularios"}
    )
    return workspace
