import re
import uuid

from django.core.exceptions import ValidationError
from django.urls import reverse


FONTS = {
    "inter": ("Inter", "Inter, sans-serif"),
    "arial": ("Arial", "Arial, sans-serif"),
    "verdana": ("Verdana", "Verdana, sans-serif"),
    "georgia": ("Georgia", "Georgia, serif"),
    "times": ("Times New Roman", "'Times New Roman', serif"),
}
DEFAULTS = {
    "background": "plain", "color": "#5943e9", "background_color": "#eeecfc",
    "heading_font": "inter", "heading_size": 24,
    "question_font": "inter", "question_size": 16,
    "text_font": "inter", "text_size": 14,
    "header_image": None,
}
PATTERNS = {"plain", "blue_dots", "gray_grid", "notebook", "gray_dots", "gray_cubes", "pink_diamonds", "green_blocks"}
COLORS = ["#db4437", "#673ab7", "#3f51b5", "#4285f4", "#03a9f4", "#00bcd4", "#ff5722", "#ff9800", "#009688", "#4caf50", "#607d8b", "#9e9e9e", "#5943e9"]
BACKGROUND_COLORS = [
    ("#ffffff", "Blanco"), ("#f3f4f6", "Gris claro"), ("#eeecfc", "Lavanda"),
    ("#e8f0fe", "Azul claro"), ("#e0f7fa", "Celeste"), ("#e8f5e9", "Verde claro"),
    ("#e0f2f1", "Menta"), ("#fff8e1", "Crema"), ("#fff3e0", "Durazno"),
    ("#fce4ec", "Rosa claro"), ("#f3e5f5", "Lila"), ("#efebe9", "Arena"),
]
TYPOGRAPHY = [
    {"key": "heading", "label": "Encabezado", "sizes": [18, 20, 24, 28, 32, 36, 40, 48]},
    {"key": "question", "label": "Pregunta", "sizes": [12, 14, 16, 18, 20, 24]},
    {"key": "text", "label": "Texto", "sizes": [11, 12, 14, 16, 18, 20]},
]


def theme_context():
    return {
        "theme_typography": TYPOGRAPHY, "theme_fonts": [(key, value[0]) for key, value in FONTS.items()],
        "theme_colors": COLORS,
        "theme_background_colors": BACKGROUND_COLORS,
        "theme_config": {
            "defaults": DEFAULTS, "fonts": {key: value[1] for key, value in FONTS.items()},
            "image_url_template": reverse("form_image", args=[uuid.UUID(int=0)]).replace(str(uuid.UUID(int=0)), "{id}"),
        },
    }


def validate_appearance(data, form):
    result = {**DEFAULTS, **{key: value for key, value in data.items() if key in DEFAULTS}}
    if not isinstance(result["background"], str) or result["background"] not in PATTERNS:
        raise ValidationError("Selecciona un fondo disponible para el formulario.")
    for key in ("color", "background_color"):
        if not isinstance(result[key], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", result[key]):
            raise ValidationError("Selecciona un color válido.")
    for group in TYPOGRAPHY:
        font, size = result[f"{group['key']}_font"], result[f"{group['key']}_size"]
        if not isinstance(font, str) or font not in FONTS or type(size) is not int or size not in group["sizes"]:
            raise ValidationError("Selecciona una fuente y un tamaño disponibles.")
    if result["header_image"]:
        try:
            image = form.images.get(pk=result["header_image"])
        except (ValueError, TypeError, ValidationError, form.images.model.DoesNotExist):
            raise ValidationError("La imagen de encabezado no pertenece a este formulario.") from None
        result["header_image"] = str(image.pk)
    else:
        result["header_image"] = None
    return result


def header_image_url(appearance):
    try:
        image_id = uuid.UUID(str((appearance or {}).get("header_image")))
    except (ValueError, TypeError, AttributeError):
        return ""
    return reverse("form_image", args=[image_id])


def theme_style(appearance):
    data = {**DEFAULTS, **(appearance or {})}
    styles = []
    for key in ("color", "background_color"):
        value = data.get(key)
        if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            value = DEFAULTS[key]
        styles.append(f"--form-{key.replace('_', '-')}: {value}")
    for group in TYPOGRAPHY:
        key = group["key"]
        font = FONTS.get(str(data.get(f"{key}_font")), FONTS[DEFAULTS[f"{key}_font"]])[1]
        size = data.get(f"{key}_size")
        if type(size) is not int or size not in group["sizes"]:
            size = DEFAULTS[f"{key}_size"]
        styles.extend([f"--form-{key}-font: {font}", f"--form-{key}-size: {size}px"])
    return "; ".join(styles)
