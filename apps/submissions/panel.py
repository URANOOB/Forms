"""Read-only data for the response workspace's selected case."""

from .presentation import response_sections
from .summary import load_summary_data, summary_for


def panel_context(submission, request, model_admin):
    if not hasattr(submission, "summary_answers"):
        load_summary_data([submission])
    sections = response_sections(submission)
    documents = [
        {**file, "field": answer["label"]}
        for section in sections
        for answer in section["answers"]
        for file in answer["files"]
    ]
    reviews = list(submission.reviews.select_related("actor")[:30])
    activities = list(
        submission.activity.exclude(event_type__in=["review_started", "reopened", "validated", "rejected"])
        .select_related("actor")[:30]
    )
    history = [
        {
            "created_at": review.created_at,
            "title": "Señal de revisión" if review.previous_status == review.status else f"{review.get_previous_status_display()} → {review.get_status_display()}",
            "actor": review.actor,
            "description": review.note,
        }
        for review in reviews
    ]
    history.extend(
        {
            "created_at": activity.created_at,
            "title": {
                "note_added": "Nota interna añadida",
                "document_viewed": "Documento visualizado",
                "document_downloaded": "Documento descargado",
            }.get(activity.event_type, activity.event_type),
            "actor": activity.actor,
            "description": activity.description,
        }
        for activity in activities
    )
    history.append({
        "created_at": submission.submitted_at,
        "title": "Respuesta recibida",
        "actor": None,
        "description": "Envío del formulario",
    })
    history.sort(key=lambda event: event["created_at"], reverse=True)
    return {
        "item": submission,
        "card": summary_for(submission),
        "sections": sections,
        "documents": documents,
        "history": history,
        "notes": list(submission.notes.select_related("author")[:30]),
        "can_review": model_admin.has_change_permission(request, submission),
        "can_note": model_admin.has_change_permission(request, submission),
        "can_act": model_admin.has_change_permission(request, submission)
        and (
            submission.status != "UNDER_REVIEW"
            or not submission.assigned_to_id
            or submission.assigned_to_id == request.user.pk
            or request.user.is_superuser
        ),
    }
