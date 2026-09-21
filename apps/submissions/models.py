import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.urls import reverse

from .storage import response_file_path, response_file_storage


class Submission(models.Model):
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
    file = models.FileField(storage=response_file_storage, upload_to=response_file_path, max_length=300)
    original_name = models.CharField(max_length=255)
    size = models.PositiveBigIntegerField()

    def get_absolute_url(self):
        return reverse("response_file", args=[self.pk])
