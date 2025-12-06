# dashboard/realtime/routing.py
from django.urls import path

from dashboard.realtime.consumers import ChatConsumer, FileTransferConsumer, NotificationConsumer

websocket_urlpatterns = [
    path("ws/chat/<int:conversation_id>/", ChatConsumer.as_asgi()),
    path("ws/upload/", FileTransferConsumer.as_asgi()),
    path("ws/notifications/", NotificationConsumer.as_asgi()),
]