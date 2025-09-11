import os
import django
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application

# Set the default settings module for Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE","algoresearch.settings.dev")

# Setup Django to avoid AppRegistryNotReady errors
django.setup()

# Import after Django setup to avoid AppRegistryNotReady errors
from dashboard.routing import websocket_urlpatterns

# Define the ASGI application
application = ProtocolTypeRouter({
    # Handle traditional HTTP requests
    "http": get_asgi_application(),
    
    # Handle WebSocket connections
    "websocket": AuthMiddlewareStack(
        URLRouter(
            websocket_urlpatterns
        )
    ),
})