from django import template
import mimetypes
from datetime import timedelta
from django.utils.html import format_html
import re
from django.utils.safestring import mark_safe
register = template.Library()

@register.filter
def startswith(value, arg):
    """Check if the given value starts with the provided argument."""
    return value.startswith(arg) if value else False

@register.filter
def file_mimetype(file_name):
    """
    Returns the MIME type of a file based on its name.
    """
    mime_type, _ = mimetypes.guess_type(file_name)
    return mime_type or "unknown"



@register.filter
def time_difference(curr_timestamp, prev_timestamp):
    if not curr_timestamp or not prev_timestamp:
        return float('inf')  # Treat as a large difference
    return abs((curr_timestamp - prev_timestamp).total_seconds())


@register.filter
def file_extension(filename, extensions):
    """
    Check if the file has one of the given extensions.
    Example: {{ file|file_extension:"jpg,png" }}
    """
    ext_list = extensions.split(',')
    return any(filename.lower().endswith(f".{ext}") for ext in ext_list)

@register.filter
def highlight_mentions(content, org_id):
    def replace_mention(match):
        username = match.group(1)
        # Return a placeholder link; the frontend fetch will resolve it
        return f'<a href="#" class="mention" data-username="{username}">@{username}</a>'
    return mark_safe(re.sub(r'@(\w+)', replace_mention, content))


@register.filter
def get_item(dictionary, key):
    """Custom template filter to get a value from a dictionary by key"""
    if isinstance(dictionary, dict):
        return dictionary.get(key, False)  # Return False if the key is missing
    return False


@register.filter
def split_string(value, delimiter=","):
    """Splits a string by the given delimiter (default: comma)"""
    if isinstance(value, str):
        return value.split(delimiter)
    return []
