from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def ensure_session_key(context):
    """
    Return the current session key, forcing session creation if needed.
    """
    request = context.get("request")
    if not request:
        return ""

    session = getattr(request, "session", None)
    if not session:
        return ""

    if not session.session_key:
        session.save()
    return session.session_key or ""
