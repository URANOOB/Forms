"""Possible matches are advisory; never reject or overwrite a person's response."""

import math
import unicodedata

from apps.forms.duplicates import DUPLICATE_TYPES

from .models import Submission, SubmissionActivity, SubmissionAnswer


def normalized_identity(value, field_type):
    if isinstance(value, dict):
        value = value.get("selected")
    if field_type == "NUMBER" and isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            return ""
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    # Preserve email punctuation and option values; document formats may differ.
    if field_type in {"EMAIL", "SINGLE_CHOICE"}:
        return text
    return "".join(char for char in text if char.isalnum())


def matching_responses(form, values, *, exclude=None):
    keys = form.duplicate_fields
    if not keys or any(not values.get(key) for key in keys):
        return Submission.objects.none()
    candidates = (
        SubmissionAnswer.objects.filter(
            submission__form=form,
            submission__deleted_at__isnull=True,
            field__stable_key__in=keys,
            field__field_type__in=DUPLICATE_TYPES,
        )
        .exclude(submission_id=exclude)
        .values_list("submission_id", "field__stable_key", "field__field_type", "value")
        .order_by("submission_id")
    )
    # Stream only identity answers, including historical versions and edited values.
    matched = []
    previous, identity = None, {}
    for submission_id, key, kind, value in candidates.iterator(chunk_size=1000):
        if previous is not None and submission_id != previous:
            if all(identity.get(key) == values[key] for key in keys):
                matched.append(previous)
            identity = {}
        previous = submission_id
        identity[key] = normalized_identity(value, kind)
    if previous is not None and all(identity.get(key) == values[key] for key in keys):
        matched.append(previous)
    return Submission.objects.filter(pk__in=matched)


def duplicates_for(submission):
    if not submission.form.duplicate_fields:
        return Submission.objects.none()
    values = {
        answer.field.stable_key: normalized_identity(answer.value, answer.field.field_type)
        for answer in submission.answers.select_related("field").filter(
            field__stable_key__in=submission.form.duplicate_fields,
            field__field_type__in=DUPLICATE_TYPES,
        )
    }
    return matching_responses(submission.form, values, exclude=submission.pk)


def flag_duplicate(submission):
    if not duplicates_for(submission).exists():
        return
    submission.attention = Submission.Attention.DUPLICATE
    submission.attention_note = (
        "Posible duplicado: los campos de identificación coinciden con otra respuesta "
        "de este formulario. Revisa las respuestas coincidentes antes de decidir."
    )
    submission.save(update_fields=["attention", "attention_note"])
    SubmissionActivity.objects.create(
        submission=submission,
        event_type="duplicate_detected",
        description=submission.attention_note,
    )
