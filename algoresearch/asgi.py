# algoresearch/asgi.py
import os
import django
from django.conf import settings
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "algoresearch.settings.dev")
django.setup()

from dashboard.realtime.routing import websocket_urlpatterns  # noqa

django_asgi = get_asgi_application()
ws_app = AuthMiddlewareStack(URLRouter(websocket_urlpatterns))

# Only enforce strict origin checks outside of dev
if not settings.DEBUG:
    ws_app = AllowedHostsOriginValidator(ws_app)

application = ProtocolTypeRouter({
    "http": django_asgi,
    "websocket": ws_app,
})