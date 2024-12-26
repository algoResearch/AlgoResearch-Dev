from django import template
import mimetypes
from django import template
register = template.Library()

@register.filter
def file_mimetype(file_name):
    """
    Returns the MIME type of a file based on its name.
    """
    mime_type, _ = mimetypes.guess_type(file_name)
    return mime_type or "unknown"


@register.filter
def file_extension(filename, extensions):
    """
    Check if the file has one of the given extensions.
    Example: {{ file|file_extension:"jpg,png" }}
    """
    ext_list = extensions.split(',')
    return any(filename.lower().endswith(f".{ext}") for ext in ext_list)
