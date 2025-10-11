from django import template

register = template.Library()

@register.filter
def split_lines(value):
    """Split text into lines for rendering as list items"""
    if value:
        return [line.strip() for line in value.split('\n') if line.strip()]
    return []