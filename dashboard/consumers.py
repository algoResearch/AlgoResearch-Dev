import os
import json
from asgiref.sync import async_to_sync
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.files.base import ContentFile
import logging
import datetime

logger = logging.getLogger(__name__)

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group_name = f'chat_{self.conversation_id}'

        logger.info(f"User {self.scope['user']} connected to {self.room_group_name}")

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        logger.info(f"User {self.scope['user']} disconnected from {self.room_group_name}")

        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket
    async def receive(self, text_data=None, bytes_data=None):
        if text_data:
            text_data_json = json.loads(text_data)
            message = text_data_json.get('message', None)

            logger.info(f"Received WebSocket message: {message}")

            if message:
                # Broadcast the decrypted message to the group (only via WebSocket)
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'message': message,  # Already decrypted
                        'sender': self.scope['user'].username,
                        'sender_profile_picture': self.scope['user'].profile_picture.url if self.scope['user'].profile_picture else '/static/img/default-profile.jpg',
                        'timestamp': datetime.datetime.now().isoformat()  # Add timestamp
                    }
                )

    # Handle the event and send message to WebSocket clients
    async def chat_message(self, event):
        message = event['message']
        sender = event['sender']
        sender_profile_picture = event['sender_profile_picture']
        timestamp = event['timestamp']

        logger.info(f"Broadcasting message from {sender}: {message}")

        # Send the message to WebSocket clients
        await self.send(text_data=json.dumps({
            'message': message,
            'sender': sender,
            'sender_profile_picture': sender_profile_picture,
            'timestamp': timestamp  # Ensure timestamp is rendered properly
        }))
        
class FileTransferConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        self.file_data = bytearray()  # Store incoming file chunks
        self.file_metadata = None

    async def receive(self, text_data=None, bytes_data=None):
        if text_data:
            message = json.loads(text_data)
            if message.get('type') == 'file_metadata':
                self.file_metadata = message['metadata']  # Store file metadata
                self.file_data = bytearray()  # Reset file data buffer

        if bytes_data:
            # Append incoming binary data (file chunks)
            self.file_data.extend(bytes_data)

            # If all chunks received, save the file
            if len(self.file_data) >= self.file_metadata['filesize']:
                await self.save_file()

    @database_sync_to_async
    def save_file(self):
        filename = self.file_metadata['filename']
        file_content = ContentFile(self.file_data)

        # Define the upload path
        upload_path = os.path.join('media', 'uploads')

        # Ensure the directory exists
        if not os.path.exists(upload_path):
            os.makedirs(upload_path)

        # Save the file in the uploads directory
        file_path = os.path.join(upload_path, filename)
        with open(file_path, 'wb') as f:
            f.write(file_content.read())
        print(f'File saved at {file_path}')

        return file_path