import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from .storage import response_file_path, response_file_storage


class Submission(models.Model):
    class Attention(models.TextChoices):
        NONE = "", "Sin incidencias"
        ATTENTION = "ATTENTION", "Requiere atención"
        ILLEGIBLE = "ILLEGIBLE", "Documento ilegible"
        INCOMPLETE = "INCOMPLETE", "Incompleta"
        DUPLICATE = "DUPLICATE", "Duplicado"

    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Recibida"
        UNDER_REVIEW = "UNDER_REVIEW", "En revisión"
        VALIDATED = "VALIDATED", "Validada"
        REJECTED = "REJECTED", "Rechazada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    form = models.ForeignKey(
        "forms.Form",
        on_delete=models.PROTECT,
        related_name="submissions",
        verbose_name="formulario",
    )
    form_version = models.ForeignKey(
        "forms.FormVersion",
        on_delete=models.PROTECT,
        related_name="submissions",
        verbose_name="versión",
    )
    status = models.CharField("estado", max_length=16, choices=Status, default=Status.SUBMITTED)
    review_revision = models.PositiveIntegerField(default=0, editable=False)
    attention = models.CharField(max_length=16, choices=Attention, blank=True, default="")
    attention_note = models.TextField(blank=True, max_length=2000)
    submitted_at = models.DateTimeField("fecha de envío", default=timezone.now, editable=False)
    idempotency_key = models.UUIDField(unique=True, editable=False)

    class Meta:
        verbose_name = "respuesta"
        verbose_name_plural = "respuestas"
        ordering = ["-submitted_at", "-id"]
        indexes = [
            models.Index(fields=["form", "submitted_at"]),
            models.Index(fields=["form", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    status__in=["SUBMITTED", "UNDER_REVIEW", "VALIDATED", "REJECTED"]
                ),
                name="submission_valid_status",
            )
        ]

    def clean(self):
        super().clean()
        if self.form_version_id and self.form_version.form_id != self.form_id:
            raise ValidationError("La versión no pertenece al formulario.")

    def __str__(self):
        return f"Respuesta {str(self.pk)[:8]}"


class SubmissionReview(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="reviews")
    previous_status = models.CharField(max_length=16, choices=Submission.Status)
    status = models.CharField(max_length=16, choices=Submission.Status)
    note = models.TextField("comentario", blank=True, max_length=2000)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(status="REJECTED") | ~models.Q(note=""),
                name="rejected_review_has_reason",
            )
        ]


class SubmissionAnswer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.ForeignKey(Submission, on_delete=models.PROTECT, related_name="answers")
    field = models.ForeignKey("forms.FormField", on_delete=models.PROTECT)
    value = models.JSONField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["submission", "field"], name="one_answer_per_submission_field"
            )
        ]

    def clean(self):
        super().clean()
        if self.field_id and self.submission_id:
            if self.field.form_version_id != self.submission.form_version_id:
                raise ValidationError("El campo no pertenece a la versión de la respuesta.")

    def __str__(self):
        return f"Dato {str(self.pk)[:8]}"


class SubmissionFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    answer = models.ForeignKey(SubmissionAnswer, on_delete=models.PROTECT, related_name="files")
    file = models.FileField(
        storage=response_file_storage, upload_to=response_file_path, max_length=300
    )
    original_name = models.CharField(max_length=255)
    size = models.PositiveBigIntegerField()
    uploaded_at = models.DateTimeField(default=timezone.now, null=True, editable=False)

    def get_absolute_url(self):
        return reverse("response_file", args=[self.pk])
