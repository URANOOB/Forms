"""Read-only data for the response workspace's selected case."""

from .presentation import response_sections
from .summary import load_summary_data, summary_for


def history_for(submission):
    reviews = list(submission.reviews.select_related("actor")[:30])
    activities = list(
        submission.activity.exclude(
            event_type__in=["review_started", "reopened", "validated", "rejected"]
        ).select_related("actor")[:30]
    )
    history = [
        {
            "created_at": review.created_at,
            "title": "Señal de revisión"
            if review.previous_status == review.status
            else f"{review.get_previous_status_display()} → {review.get_status_display()}",
            "actor": review.actor,
            "actor_deleted": review.actor_id is None,
            "description": review.note,
        }
        for review in reviews
    ]
    history.extend(
        {
            "created_at": activity.created_at,
            "title": {
                "email_sent": "Notificación enviada",
                "email_delivery": "Entrega de correo",
                "note_added": "Nota interna añadida",
                "document_viewed": "Documento visualizado",
                "document_downloaded": "Documento descargado",
                "trashed": "Respuesta enviada a la papelera",
                "restored": "Respuesta restaurada",
            }.get(activity.event_type, activity.event_type),
            "actor": activity.actor,
            "description": activity.description,
        }
        for activity in activities
    )
    history.append(
        {
            "created_at": submission.submitted_at,
            "title": "Respuesta recibida",
            "actor": None,
            "description": "Envío del formulario",
        }
    )
    history.sort(key=lambda event: event["created_at"], reverse=True)
    return history


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
    return {
        "item": submission,
        "card": summary_for(submission),
        "sections": sections,
        "documents": documents,
        "history": history_for(submission),
        "notes": list(submission.notes.select_related("author")[:30]),
        "can_review": model_admin.has_change_permission(request, submission),
        "can_note": model_admin.has_change_permission(request, submission),
        "can_act": model_admin.has_change_permission(request, submission),
    }
