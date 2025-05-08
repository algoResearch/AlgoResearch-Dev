from django import template
import mimetypes
from datetime import timedelta
from django.utils.html import format_html
import re
from django.utils.safestring import mark_safe
from decimal import Decimal, InvalidOperation

import json
import os
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
def extract_employee_id(description):
    """
    Extracts [ID: xxxx] from description string
    """
    if not description:
        return None
    match = re.search(r'\[ID:\s*(\d+)\]', description)
    if match:
        return match.group(1)
    return None

# In custom_filters.py
@register.filter
def safe_sidebar_color(user):
    if hasattr(user, 'sidebar_color') and user.sidebar_color:
        return user.sidebar_color
    if hasattr(user, 'organization') and getattr(user.organization, 'sidebar_color', None):
        return user.organization.sidebar_color
    return "#115600"
@register.filter
def safe_hover_color(user):
    if hasattr(user, 'hover_color') and user.hover_color:
        return user.hover_color
    if hasattr(user, 'organization') and getattr(user.organization, 'hover_color', None):
        return user.organization.hover_color
    return "#495057"

@register.filter
def underscore_to_space(value):
    """Replaces underscores with spaces and title-cases the string."""
    if isinstance(value, str):
        return value.replace("_", " ").title()
    return value

@register.filter
def readonly_if_no_edit(can_edit):
    return "" if can_edit else "readonly"


@register.filter
def get_range(value):
    """Returns a range from 0 to value"""
    try:
        return range(int(value))
    except:
        return []
@register.filter
def get_nested(dictionary, keys):
    """Get a nested dictionary item using a 'key1,key2' style string."""
    try:
        key1, key2 = keys.split(',')
        return dictionary.get(key1, {}).get(key2)
    except Exception:
        return None


@register.filter
def index(sequence, position):
    """Returns the item at the given position in a list"""
    try:
        return sequence[position]
    except (IndexError, TypeError):
        return ""


@register.filter
def clean_template(value):
    """Trim whitespace and return the value as a string."""
    if value is None:
        return ""
    return str(value).strip()

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
def prettify_section(value):
    """Replaces underscores with spaces and title-cases the result."""
    return value.replace('_', ' ').title()


@register.simple_tag
def get_section_template(section_templates, section):
    return "partials/irb_sections/" + section_templates.get(section, "")

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
def subtract(val, arg):
    try:
        return Decimal(val) - Decimal(arg)
    except (ValueError, TypeError, InvalidOperation):
        return Decimal("0.00")

@register.filter
def floatval(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0
    
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
def as_integer_range(value):
    """Convert an integer into a range usable in for-loops."""
    try:
        return range(int(value))
    except (ValueError, TypeError):
        return range(0)

@register.filter
def basename(value):
    return os.path.basename(value.name) if hasattr(value, 'name') else os.path.basename(str(value))



@register.filter
def get_section(financials, section):
    return financials.filter(section=section).first()

@register.filter
def div(value, arg):
    try:
        return float(value) / float(arg) if float(arg) != 0 else 0
    except:
        return 0

@register.filter
def mul(value, arg):
    try:
        return float(value) * float(arg)
    except:
        return 0
    
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
@register.filter
def dict_get(d, key):
    """Get a value from a dictionary safely."""
    if isinstance(d, dict):
        return d.get(key, "")
    return ""
