from .models import FieldOption, FormField, FormSection

# Datos del catálogo; las plantillas crean borradores y nunca publican automáticamente.
PRESETS = {
    "attendance": {
        "name": "Confirmación de asistencia",
        "theme": "sand",
        "banner": "event",
        "description": "Confirma tu participación en nuestro próximo encuentro.",
        "fields": [
            ("nombre", "Nombre completo", "SHORT_TEXT", True),
            ("correo", "Correo electrónico", "EMAIL", True),
            (
                "asistencia",
                "¿Asistirás al evento?",
                "SINGLE_CHOICE",
                True,
                ["Sí", "No", "Por confirmar"],
            ),
        ],
    },
    "event": {
        "name": "Inscripción a un evento",
        "theme": "peach",
        "banner": "event",
        "description": "Inscríbete y comparte tus datos para participar en el evento.",
        "fields": [
            ("nombre", "Nombre completo", "SHORT_TEXT", True),
            ("correo", "Correo electrónico", "EMAIL", True),
            ("organizacion", "Organización", "SHORT_TEXT", False),
            ("telefono", "Teléfono de contacto", "PHONE", False),
        ],
    },
    "contact": {
        "name": "Datos de contacto",
        "theme": "mint",
        "banner": "contact",
        "description": "Comparte tus datos para que podamos comunicarnos contigo.",
        "fields": [
            ("nombre", "Nombre completo", "SHORT_TEXT", True),
            ("correo", "Correo electrónico", "EMAIL", True),
            ("telefono", "Teléfono", "PHONE", False),
            ("mensaje", "Mensaje", "LONG_TEXT", False),
        ],
    },
    "registration": {
        "name": "Registro de pacientes",
        "theme": "blue",
        "banner": "registration",
        "description": "Completa la información personal para iniciar tu registro.",
        "fields": [
            ("nombre", "Nombre completo", "SHORT_TEXT", True),
            ("documento", "Número de documento", "SHORT_TEXT", True),
            ("correo", "Correo electrónico", "EMAIL", False),
            ("telefono", "Teléfono de contacto", "PHONE", True),
        ],
    },
    "feedback": {
        "name": "Encuesta de satisfacción",
        "theme": "lavender",
        "banner": "feedback",
        "description": "Tu opinión nos ayuda a mejorar la atención.",
        "fields": [
            (
                "experiencia",
                "¿Cómo fue tu experiencia?",
                "SINGLE_CHOICE",
                True,
                ["Excelente", "Buena", "Regular", "Mala"],
            ),
            ("comentarios", "¿Qué podemos mejorar?", "LONG_TEXT", False),
            ("recomendar", "¿Recomendarías nuestro servicio?", "BOOLEAN", False),
        ],
    },
}


def create_preset_fields(version, preset_key):
    preset = PRESETS.get(preset_key)
    if not preset:
        return
    section = FormSection.objects.create(form_version=version, title="Información general")
    for order, (key, label, kind, required, *choices) in enumerate(preset["fields"]):
        field = FormField.objects.create(
            form_version=version,
            section=section,
            stable_key=key,
            label=label,
            field_type=kind,
            required=required,
            order=order,
        )
        if choices:
            for index, label in enumerate(choices[0]):
                FieldOption.objects.create(
                    field=field, label=label, value=str(index + 1), order=index
                )
