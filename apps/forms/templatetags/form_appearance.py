import re
from copy import deepcopy

from django import template

from apps.forms.appearance import header_image_url, theme_style

register = template.Library()
register.filter("theme_style", theme_style)
register.filter("header_image_url", header_image_url)


@register.filter
def public_accessible_theme(appearance):
    """Scale public typography with browser preferences; keep authoring styles intact."""
    styles = theme_style(appearance)
    styles = re.sub(
        r"(--form-\w+-size:) (\d+)px",
        lambda match: f"{match[1]} {int(match[2]) / 16:g}rem",
        styles,
    )
    color = re.search(r"--form-color: (#[0-9a-fA-F]{6})", styles).group(1)
    channels = [int(color[index : index + 2], 16) for index in (1, 3, 5)]

    def luminance(rgb):
        linear = [v / 3294.6 if v <= 10 else ((v / 255 + 0.055) / 1.055) ** 2.4 for v in rgb]
        return sum(v * weight for v, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    # Extra margin for the very light question surfaces, not just pure white.
    while 1.05 / (luminance(channels) + 0.05) < 5:
        channels = [int(value * 0.9) for value in channels]
    accent = "#" + "".join(f"{value:02x}" for value in channels)
    return f"{styles}; --accessible-accent: {accent}"


@register.filter
def public_accessible_input(bound):
    widget = deepcopy(bound.field.widget)
    if widget.template_name == "public/widgets/grid.html":
        widget.template_name = "public/widgets/accessible_grid.html"
    elif widget.template_name == "public/widgets/scale.html":
        widget.template_name = "public/widgets/accessible_scale.html"
    descriptions = [f"{bound.auto_id}_error"]
    if bound.help_text or bound.name.endswith("__extra") or "data-digits-only" in widget.attrs:
        descriptions.append(f"{bound.auto_id}_helptext")
    if widget.attrs.get("data-max-files"):
        descriptions.append(f"{bound.auto_id}_upload_hint")
    return bound.as_widget(widget=widget, attrs={"aria-describedby": " ".join(descriptions)})
