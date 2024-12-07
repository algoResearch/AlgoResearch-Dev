import django
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'algoResearchs.settings')

# Call django.setup() before importing project-specific modules
django.setup()

from dashboard.routing import websocket_urlpatterns  # Ensure this comes after django.setup()

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            websocket_urlpatterns
        )
    ),
})