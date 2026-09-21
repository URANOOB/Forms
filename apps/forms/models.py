import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.db.models import Q
from django.urls import reverse


def validate_object(value):
    if not isinstance(value, dict):
        raise ValidationError("Debe ser un objeto JSON.")


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class Form(UUIDModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Borrador"
        PUBLISHED = "PUBLISHED", "Publicado"
        PAUSED = "PAUSED", "Pausado"
        ARCHIVED = "ARCHIVED", "Archivado"

    workspace = models.ForeignKey(
        "accounts.Workspace", on_delete=models.PROTECT, verbose_name="espacio de trabajo"
    )
    name = models.CharField("nombre", max_length=200)
    slug = models.SlugField(max_length=180)
    description = models.TextField("descripción", blank=True)
    status = models.CharField("estado", max_length=12, choices=Status, default=Status.DRAFT)
    active_version = models.ForeignKey(
        "FormVersion",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="active_for_forms",
        editable=False,
        verbose_name="versión activa",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="creado por"
    )
    created_at = models.DateTimeField("creado el", auto_now_add=True)
    updated_at = models.DateTimeField("actualizado el", auto_now=True)
    deleted_at = models.DateTimeField("eliminado el", null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "formulario"
        verbose_name_plural = "formularios"
        constraints = [
            models.UniqueConstraint(fields=["workspace", "slug"], name="form_workspace_slug"),
            models.CheckConstraint(
                condition=Q(status__in=["DRAFT", "PUBLISHED", "PAUSED", "ARCHIVED"]),
                name="form_valid_status",
            ),
            models.CheckConstraint(
                condition=~Q(status="PUBLISHED") | Q(active_version__isnull=False),
                name="published_form_has_version",
            ),
        ]
        indexes = [models.Index(fields=["workspace", "status"])]

    def clean(self):
        super().clean()
        if self.active_version_id:
            version = self.active_version
            if version.form_id != self.pk or version.status != FormVersion.Status.PUBLISHED:
                raise ValidationError({"active_version": "Debe ser una versión publicada propia."})
        if self.status == self.Status.PUBLISHED and not self.active_version_id:
            raise ValidationError({"status": "Publicar requiere una versión activa."})

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("public_form", kwargs={"form_id": self.pk})


class FormVersion(UUIDModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Borrador"
        PUBLISHED = "PUBLISHED", "Publicada"
        ARCHIVED = "ARCHIVED", "Archivada"

    form = models.ForeignKey(Form, on_delete=models.PROTECT, related_name="versions")
    version_number = models.PositiveIntegerField("versión")
    status = models.CharField("estado", max_length=12, choices=Status, default=Status.DRAFT)
    published_at = models.DateTimeField("publicada el", null=True, blank=True)
    created_at = models.DateTimeField("creada el", auto_now_add=True)
    schema_version = models.PositiveIntegerField("versión del esquema", default=1)
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)

    welcome = models.JSONField(default=dict, blank=True, validators=[validate_object])
    appearance = models.JSONField(default=dict, blank=True, validators=[validate_object])
    welcome_image = models.ForeignKey(
        "FormImage", on_delete=models.PROTECT, null=True, blank=True, related_name="welcome_versions"
    )

    class Meta:
        ordering = ["form", "-version_number"]
        verbose_name = "versión"
        verbose_name_plural = "versiones"
        constraints = [
            models.UniqueConstraint(fields=["form", "version_number"], name="form_version_number"),
            models.UniqueConstraint(
                fields=["form"], condition=Q(status="DRAFT"), name="one_draft_per_form"
            ),
            models.CheckConstraint(
                condition=Q(version_number__gte=1, schema_version__gte=1),
                name="positive_version_numbers",
            ),
            models.CheckConstraint(
                condition=Q(status="DRAFT", published_at__isnull=True)
                | Q(status="PUBLISHED", published_at__isnull=False)
                | Q(status="ARCHIVED"),
                name="version_publication_consistent",
            ),
        ]

    def clean(self):
        super().clean()
        if self.welcome_image_id and self.welcome_image.form_id != self.form_id:
            raise ValidationError({"welcome_image": "La imagen debe pertenecer a este formulario."})

    def save(self, *args, **kwargs):
        if type(self).objects.filter(pk=self.pk).exclude(status=self.Status.DRAFT).exists():
            raise ValidationError("Las versiones publicadas o archivadas son inmutables.")
        original = type(self).objects.filter(pk=self.pk).first()
        if original and original.form_id != self.form_id:
            raise ValidationError("Una versión no puede trasladarse a otro formulario.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if type(self).objects.filter(pk=self.pk).exclude(status=self.Status.DRAFT).exists():
            raise ValidationError("Las versiones publicadas o archivadas no pueden eliminarse.")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.form} · v{self.version_number}"


class VersionContent(UUIDModel):
    """Protege escrituras ordinarias; bulk/update no son APIs de edición del esquema."""

    class Meta:
        abstract = True

    def get_version(self):
        raise NotImplementedError

    def assert_draft(self):
        version = self.get_version()
        if version and not FormVersion.objects.filter(pk=version.pk, status="DRAFT").exists():
            raise ValidationError("Crea un nuevo borrador para modificar una versión publicada.")
        if not self._state.adding:
            original = type(self).objects.get(pk=self.pk)
            if original.get_version().status != FormVersion.Status.DRAFT:
                raise ValidationError("No puedes mover contenido de una versión publicada.")
            if version and original.get_version().pk != version.pk:
                raise ValidationError("El contenido debe copiarse, no moverse entre versiones.")

    def clean(self):
        super().clean()
        for name in ("configuration", "validation"):
            if hasattr(self, name) and not isinstance(getattr(self, name), dict):
                raise ValidationError({name: "Debe ser un objeto JSON."})

    @transaction.atomic
    def save(self, *args, **kwargs):
        version = self.get_version()
        if version:
            FormVersion.objects.select_for_update().get(pk=version.pk)
        self.assert_draft()
        self.full_clean()
        return super().save(*args, **kwargs)

    @transaction.atomic
    def delete(self, *args, **kwargs):
        version = self.get_version()
        if version:
            FormVersion.objects.select_for_update().get(pk=version.pk)
        self.assert_draft()
        return super().delete(*args, **kwargs)


class FormSection(VersionContent):
    form_version = models.ForeignKey(FormVersion, on_delete=models.CASCADE, related_name="sections")
    title = models.CharField("título", max_length=200)
    description = models.TextField("descripción", blank=True)
    order = models.PositiveIntegerField("orden", default=0)
    configuration = models.JSONField(default=dict, blank=True, validators=[validate_object])

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "sección"
        verbose_name_plural = "secciones"
        indexes = [models.Index(fields=["form_version", "order"])]

    def get_version(self):
        return self.form_version if self.form_version_id else None

    def __str__(self):
        return self.title


class FormImage(UUIDModel):
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name="images")
    file = models.FileField(upload_to="form-images/%Y/%m/")
    created_at = models.DateTimeField(auto_now_add=True)

    def get_absolute_url(self):
        return reverse("form_image", args=[self.pk])


class FormField(VersionContent):
    class Type(models.TextChoices):
        SHORT_TEXT = "SHORT_TEXT", "Respuesta corta"
        LONG_TEXT = "LONG_TEXT", "Párrafo"
        EMAIL = "EMAIL", "Correo electrónico"
        PHONE = "PHONE", "Teléfono"
        NUMBER = "NUMBER", "Número"
        DATE = "DATE", "Fecha"
        TIME = "TIME", "Hora"
        SINGLE_CHOICE = "SINGLE_CHOICE", "Varias opciones"
        MULTIPLE_CHOICE = "MULTIPLE_CHOICE", "Casillas"
        LINEAR_SCALE = "LINEAR_SCALE", "Escala lineal"
        RATING = "RATING", "Calificación"
        GRID_SINGLE = "GRID_SINGLE", "Cuadrícula de varias opciones"
        GRID_MULTIPLE = "GRID_MULTIPLE", "Cuadrícula de casillas"
        BOOLEAN = "BOOLEAN", "Sí / No"
        FILE = "FILE", "Subir archivos"
        DOCUMENT = "DOCUMENT", "Documento"
        HEADING = "HEADING", "Encabezado"
        INFORMATION = "INFORMATION", "Información"
        IMAGE = "IMAGE", "Imagen"

    # FK explícita permite unicidad de stable_key en toda la versión, entre secciones.
    form_version = models.ForeignKey(FormVersion, on_delete=models.CASCADE, related_name="fields")
    section = models.ForeignKey(FormSection, on_delete=models.CASCADE, related_name="fields")
    stable_key = models.CharField(
        max_length=100,
        validators=[
            RegexValidator(r"^[a-z][a-z0-9_]*$", "Usa letras minúsculas, números y guion bajo.")
        ],
    )
    label = models.CharField("etiqueta", max_length=240)
    help_text = models.TextField("ayuda", blank=True)
    field_type = models.CharField("tipo", max_length=20, choices=Type)
    required = models.BooleanField("obligatorio", default=False)
    placeholder = models.CharField(max_length=240, blank=True)
    order = models.PositiveIntegerField("orden", default=0)
    configuration = models.JSONField(default=dict, blank=True, validators=[validate_object])
    validation = models.JSONField(default=dict, blank=True, validators=[validate_object])
    image = models.ForeignKey(FormImage, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "campo"
        verbose_name_plural = "campos"
        indexes = [models.Index(fields=["section", "order"])]
        constraints = [
            models.UniqueConstraint(
                fields=["form_version", "stable_key"], name="field_key_per_version"
            )
        ]

    def get_version(self):
        return self.form_version if self.form_version_id else None

    def clean(self):
        super().clean()
        if self.section_id and self.section.form_version_id != self.form_version_id:
            raise ValidationError({"section": "La sección debe pertenecer a la misma versión."})
        if self.image_id and self.image.form_id != self.form_version.form_id:
            raise ValidationError({"image": "La imagen debe pertenecer a este formulario."})
        if (
            self.field_type in {self.Type.HEADING, self.Type.INFORMATION, self.Type.IMAGE}
            and self.required
        ):
            raise ValidationError({"required": "Un campo informativo no admite respuestas."})

    def __str__(self):
        return self.label


class FieldOption(VersionContent):
    field = models.ForeignKey(FormField, on_delete=models.CASCADE, related_name="options")
    label = models.CharField("etiqueta", max_length=240)
    value = models.CharField("valor", max_length=150)
    order = models.PositiveIntegerField("orden", default=0)
    is_active = models.BooleanField("activa", default=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "opción"
        verbose_name_plural = "opciones"
        indexes = [models.Index(fields=["field", "order"])]
        constraints = [
            models.UniqueConstraint(fields=["field", "value"], name="option_field_value")
        ]

    def get_version(self):
        return self.field.form_version if self.field_id else None

    def clean(self):
        super().clean()
        if self.field_id and self.field.field_type not in {
            FormField.Type.SINGLE_CHOICE,
            FormField.Type.MULTIPLE_CHOICE,
        }:
            raise ValidationError({"field": "Sólo los campos de selección admiten opciones."})

    def __str__(self):
        return self.label


class ConditionalRule(VersionContent):
    class Operator(models.TextChoices):
        EQUALS = "EQUALS", "Igual a"
        NOT_EQUALS = "NOT_EQUALS", "Distinto de"
        CONTAINS = "CONTAINS", "Contiene"
        GREATER_THAN = "GREATER_THAN", "Mayor que"
        LESS_THAN = "LESS_THAN", "Menor que"
        IS_EMPTY = "IS_EMPTY", "Está vacío"
        IS_NOT_EMPTY = "IS_NOT_EMPTY", "No está vacío"

    class Action(models.TextChoices):
        SHOW = "SHOW", "Mostrar"
        HIDE = "HIDE", "Ocultar"
        REQUIRE = "REQUIRE", "Hacer obligatorio"
        OPTIONAL = "OPTIONAL", "Hacer opcional"

    class Combinator(models.TextChoices):
        AND = "AND", "Todas"
        OR = "OR", "Alguna"

    form_version = models.ForeignKey(FormVersion, on_delete=models.CASCADE, related_name="rules")
    source_field = models.ForeignKey(
        FormField, on_delete=models.CASCADE, related_name="source_rules"
    )
    operator = models.CharField(max_length=20, choices=Operator)
    expected_value = models.JSONField(null=True, blank=True)
    action = models.CharField(max_length=12, choices=Action)
    target_field = models.ForeignKey(
        FormField, on_delete=models.CASCADE, null=True, blank=True, related_name="target_rules"
    )
    target_section = models.ForeignKey(
        FormSection, on_delete=models.CASCADE, null=True, blank=True, related_name="target_rules"
    )
    group_key = models.CharField("grupo", max_length=100, null=True, blank=True)
    group_operator = models.CharField(
        "operador de grupo", max_length=3, choices=Combinator, default=Combinator.AND
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "regla condicional"
        verbose_name_plural = "reglas condicionales"
        indexes = [models.Index(fields=["form_version", "order"])]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(target_field__isnull=False, target_section__isnull=True)
                    | Q(target_field__isnull=True, target_section__isnull=False)
                ),
                name="rule_exactly_one_target",
            )
        ]

    def get_version(self):
        return self.form_version if self.form_version_id else None

    def clean(self):
        super().clean()
        for name in ("source_field", "target_field", "target_section"):
            if getattr(self, f"{name}_id"):
                if getattr(self, name).form_version_id != self.form_version_id:
                    raise ValidationError({name: "Debe pertenecer a la misma versión."})
        if self.source_field_id and self.source_field_id == self.target_field_id:
            raise ValidationError("Un campo no puede condicionarse a sí mismo.")
        if self.source_field_id and self.source_field.section_id == self.target_section_id:
            raise ValidationError("La condición no puede controlar su propia sección.")
        if self.source_field_id and self.source_field.field_type in {
            FormField.Type.HEADING,
            FormField.Type.INFORMATION,
            FormField.Type.IMAGE,
        }:
            raise ValidationError({"source_field": "Debe ser un campo con respuesta."})
        if self.target_section_id and self.action in {self.Action.REQUIRE, self.Action.OPTIONAL}:
            raise ValidationError({"action": "La obligatoriedad se configura sobre campos."})
        if self.form_version_id and self.group_key:
            peers = type(self).objects.filter(
                form_version_id=self.form_version_id, group_key=self.group_key
            )
            for peer in peers.exclude(pk=self.pk):
                if (
                    peer.group_operator,
                    peer.action,
                    peer.target_field_id,
                    peer.target_section_id,
                ) != (
                    self.group_operator,
                    self.action,
                    self.target_field_id,
                    self.target_section_id,
                ):
                    raise ValidationError(
                        "Las condiciones de un grupo deben compartir acción y destino."
                    )

    def __str__(self):
        return f"{self.get_action_display()} · {self.get_operator_display()} · {self.pk}"
