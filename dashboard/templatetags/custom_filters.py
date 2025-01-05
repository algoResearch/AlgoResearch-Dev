from django import template
import mimetypes
from datetime import timedelta

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
