from django.urls import re_path
from dashboard.realtime.consumers import ChatConsumer, FileTransferConsumer, NotificationConsumer

# Define WebSocket URL patterns
websocket_urlpatterns = [
    # WebSocket for chat messages
    re_path(r'ws/chat/(?P<conversation_id>\d+)/$', ChatConsumer.as_asgi()),
    
    # WebSocket for file uploads
    re_path(r'ws/upload/$', FileTransferConsumer.as_asgi()),
    
    # WebSocket for user-specific notifications
    re_path(r'ws/notifications/user_(?P<user_id>\d+)/$', NotificationConsumer.as_asgi()),
]