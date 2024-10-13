from django.urls import re_path
from dashboard.consumers import ChatConsumer, FileTransferConsumer

# Define WebSocket URL patterns
websocket_urlpatterns = [
    # WebSocket URL for chat conversations
    re_path(r'ws/chat/(?P<conversation_id>\d+)/$', ChatConsumer.as_asgi()),

    # WebSocket URL for file uploads
    re_path(r'ws/upload/$', FileTransferConsumer.as_asgi()),
]
