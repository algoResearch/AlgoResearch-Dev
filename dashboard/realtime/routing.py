# dashboard/realtime/routing.py
from django.urls import path

from dashboard.realtime.consumers import ChatConsumer, FileTransferConsumer, NotificationConsumer

websocket_urlpatterns = [
    # WebSocket for chat messages
    path("ws/chat/<int:conversation_id>/", ChatConsumer.as_asgi()),

    # WebSocket for file uploads
    path("ws/upload/", FileTransferConsumer.as_asgi()),

    # WebSocket for user-specific notifications
    # We’ll infer the user from auth / lt_user, not from the URL.
    path("ws/notifications/", NotificationConsumer.as_asgi()),
]
