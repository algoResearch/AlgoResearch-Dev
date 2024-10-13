import os
import django
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from dashboard.routing import websocket_urlpatterns

# Set the default settings module for Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'algoResearchs.settings')

# Initialize Django before importing other modules
django.setup()

# Define the ASGI application with HTTP and WebSocket support
application = ProtocolTypeRouter({
    "http": get_asgi_application(),  # Handles traditional HTTP requests
    "websocket": AuthMiddlewareStack(
        URLRouter(
            websocket_urlpatterns  # Routes WebSocket requests to the consumer
        )
    ),
})