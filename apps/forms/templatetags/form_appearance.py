from django import template

from apps.forms.appearance import header_image_url, theme_style

register = template.Library()
register.filter("theme_style", theme_style)
register.filter("header_image_url", header_image_url)
