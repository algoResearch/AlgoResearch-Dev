# custom_filters.py
from django import template
from django.utils import timezone

register = template.Library()

@register.filter
def formatted_timestamp(value):
    if value:
        return timezone.localtime(value).strftime("Completed at %Y-%m-%d %H:%M:%S")
    return ""
