from django import template
import mimetypes
from datetime import timedelta
from django.utils.html import format_html
import re
from django.utils.safestring import mark_safe
import json
register = template.Library()

@register.filter
def startswith(value, arg):
    """Check if the given value starts with the provided argument."""
    return value.startswith(arg) if value else False
@register.filter(name='underscore_to_hyphen')
def underscore_to_hyphen(value):
    """Replaces underscores with hyphens."""
    if isinstance(value, str):
        return value.replace("_", "-")
    return value

@register.filter
def readonly_if_no_edit(can_edit):
    return "" if can_edit else "readonly"


@register.filter(name='add_class')
def add_class(field, css_class):
    return field.as_widget(attrs={**field.field.widget.attrs, 'class': css_class})

@register.filter(name='disable_if')
def disable_if(condition, attr="disabled"):
    return attr if condition else ""

@register.filter(name='negate')
def negate(value):
    return not value

@register.filter(name='capreplace')
def capreplace(value):
    """Replace underscores with spaces and capitalize each word."""
    if isinstance(value, str):
        return " ".join(word.capitalize() for word in value.split("_"))
    return value


@register.filter
def file_mimetype(file_name):
    """
    Returns the MIME type of a file based on its name.
    """
    mime_type, _ = mimetypes.guess_type(file_name)
    return mime_type or "unknown"


@register.filter
def json_loads(value):
    """Loads a JSON string and returns a Python object."""
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
    

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

@register.filter(name='replace')
def replace(value, args):
    """ Custom replace filter: {{ text|replace:'old,new' }} """
    try:
        old, new = args.split(',')
        return value.replace(old, new)
    except ValueError:
        return value  # Return original if incorrect arguments


@register.filter(name='replace_underscore')
def replace_underscore(value):
    """Replaces underscores with spaces."""
    if isinstance(value, str):
        return value.replace("_", " ")
    return value


@register.filter
def get_key(dictionary, key):
    """Fetch a dictionary key safely in a Django template."""
    return dictionary.get(key, {})


@register.filter
def split_string(value, delimiter=","):
    """Splits a string by the given delimiter (default: comma)"""
    if isinstance(value, str):
        return value.split(delimiter)
    return []
