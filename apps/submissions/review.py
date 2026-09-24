"""Review workflow shared by the response board and response detail."""

from django import forms
from django.core.exceptions import ValidationError

from .models import Submission, SubmissionReview

STATUS_HELP = {
    "SUBMITTED": "Nuevas respuestas pendientes de revisar.",
    "UNDER_REVIEW": "Respuestas cuya información se está comprobando.",
    "VALIDATED": "Información revisada y aceptada.",
    "REJECTED": "Respuestas no aceptadas, con el motivo registrado.",
}
TRANSITIONS = {
    "SUBMITTED": [("UNDER_REVIEW", "Iniciar revisión")],
    "UNDER_REVIEW": [("VALIDATED", "Validar respuesta"), ("REJECTED", "Rechazar respuesta")],
    "VALIDATED": [("UNDER_REVIEW", "Reabrir revisión")],
    "REJECTED": [("UNDER_REVIEW", "Reabrir revisión")],
}


class AttentionForm(forms.Form):
    attention = forms.ChoiceField(
        label="Señal", choices=Submission.Attention.choices, required=False
    )
    attention_note = forms.CharField(
        label="Detalle de la incidencia",
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("attention") and not cleaned.get("attention_note"):
            self.add_error("attention_note", "Explica la incidencia para orientar la revisión.")
        return cleaned


class ReviewForm(forms.Form):
    status = forms.ChoiceField(label="Acción")
    note = forms.CharField(
        label="Comentario",
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Obligatorio al rechazar. En las demás acciones es opcional.",
    )
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)

    def __init__(self, submission, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = TRANSITIONS[submission.status]
        self.fields["revision"].initial = submission.review_revision

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("status") == "REJECTED" and not cleaned.get("note"):
            self.add_error("note", "Indica el motivo del rechazo.")
        return cleaned

    @property
    def action_label(self):
        choices = self.fields["status"].choices
        return dict(choices).get(self["status"].value(), choices[0][1])

    @property
    def is_rejection(self):
        return self["status"].value() == "REJECTED"


def record_review(submission, status, note, actor):
    """Caller must hold the submission's row lock inside a transaction."""
    if status not in dict(TRANSITIONS[submission.status]):
        raise ValidationError("Esta acción no está disponible para el estado actual.")
    note = note.strip()
    if status == Submission.Status.REJECTED and not note:
        raise ValidationError("Indica el motivo del rechazo.")
    if len(note) > 2000:
        raise ValidationError("El comentario admite hasta 2.000 caracteres.")
    review = SubmissionReview.objects.create(
        submission=submission,
        previous_status=submission.status,
        status=status,
        note=note,
        actor=actor,
    )
    submission.status = status
    submission.review_revision += 1
    submission.save(update_fields=["status", "review_revision"])
    return review
