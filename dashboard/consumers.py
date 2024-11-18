import os
import json
import logging
import datetime
import uuid
from asgiref.sync import async_to_sync
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.files.base import ContentFile
from django.conf import settings
from django.apps import apps  # Lazy import models

logger = logging.getLogger(__name__)
class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group_name = f'chat_{self.conversation_id}'
        self.file_data = bytearray()  # To store incoming file chunks
        self.file_metadata = None  # To store metadata about the file being uploaded

        # Add the user to the room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        # Remove the user from the room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data=None, bytes_data=None):
    # Handle text data (message, file metadata, or read receipt)
        if text_data:
            try:
                text_data_json = json.loads(text_data)

                # Handle message sending
                if text_data_json.get('type') == 'message':
                    message = text_data_json['message']
                    # Save the message to the database
                    await self.save_message(message)

                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'chat_message',
                            'message': message,
                            'sender': self.scope['user'].username,
                            'sender_profile_picture': self.scope['user'].profile_picture.url if self.scope['user'].profile_picture else '/static/img/default-profile.jpg',
                            'timestamp': datetime.datetime.now().isoformat(),
                        }
                    )
                if text_data_json.get('type') == 'typing':
                    is_typing = text_data_json.get('is_typing', False)

                    # Broadcast typing state to the group
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'user_typing',
                            'username': self.scope['user'].username,
                            'is_typing': is_typing
                        }
                    )

                # Handle read receipt
                if text_data_json.get('type') == 'read_receipt':
                    message_id = text_data_json['message_id']
                    receipt_data = await self.mark_message_as_read(message_id)
                    if receipt_data:
                        await self.channel_layer.group_send(
                            self.room_group_name,
                            {
                                'type': 'message_read',
                                'message_id': receipt_data['message_id'],
                                'read_at': receipt_data['read_at'],
                            }
                        )

                # Handle file metadata
                if text_data_json.get('type') == 'file_metadata':
                    self.file_metadata = text_data_json['metadata']
                    self.file_data = bytearray()  # Reset file buffer

            except json.JSONDecodeError:
                logger.error("Error decoding JSON")
    
        # Handle binary data (file chunks)
        elif bytes_data:
            self.file_data.extend(bytes_data)  # Append incoming binary data (file chunks)

            # If all chunks received, save the file
            if len(self.file_data) >= self.file_metadata['filesize']:
                file_path = await self.save_file(self.file_data)
                self.file_data = bytearray()  # Reset the buffer

                # Save the file path (attachment_url) in the database
                await self.save_message(attachment_url=file_path)

                # Broadcast the file to the group
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'message': None,  # No text, only the file
                        'sender': self.scope['user'].username,
                        'sender_profile_picture': self.scope['user'].profile_picture.url if self.scope['user'].profile_picture else '/static/img/default-profile.jpg',
                        'timestamp': datetime.datetime.now().isoformat(),
                        'attachment_url': file_path,
                        'filetype': self.file_metadata['filetype']  # Send the file type to the frontend
                    }
                )
    @database_sync_to_async
    def save_message(self, content=None, attachment_url=None):
        Conversation = apps.get_model('dashboard', 'Conversation')
        Message = apps.get_model('dashboard', 'Message')
    
        conversation = Conversation.objects.get(id=self.conversation_id)

    # Ensure attachment URL is stored correctly without MEDIA_URL
        if attachment_url:
            attachment_url = attachment_url.lstrip('/')

        message = Message.objects.create(
            conversation=conversation,
            sender=self.scope['user'],
            content=content if content else '',
            attachment=attachment_url,
            is_read=False
        )
        return message
    
    @database_sync_to_async
    def mark_message_as_read(self, message_id):
        Message = apps.get_model('dashboard', 'Message')
        message = Message.objects.get(id=message_id)

        if message.sender != self.scope['user'] and message.read_at is None:  # Only mark as read if the user is not the sender
            message.read_at = datetime.datetime.now()
            message.save()

            # Return the timestamp for WebSocket broadcasting
            return {
                'message_id': message.id,
                'read_at': message.read_at.isoformat()  # Send timestamp to WebSocket
            }
        return None

    @database_sync_to_async
    def save_file(self, file_data):
        ext = '.jpg' if self.file_metadata['filetype'].startswith('image') else '.pdf'
        file_name = f"{uuid.uuid4()}{ext}"
        file_path = os.path.join(settings.MEDIA_ROOT, 'attachments', file_name)

        # Ensure the 'attachments' directory exists
        if not os.path.exists(os.path.join(settings.MEDIA_ROOT, 'attachments')):
            os.makedirs(os.path.join(settings.MEDIA_ROOT, 'attachments'))

        # Save the file to the file system
        with open(file_path, 'wb') as file:
            file.write(file_data)

        # Return the relative file path (for saving in the database)
        return f"attachments/{file_name}"

    async def chat_message(self, event):
        # Send message or file to WebSocket client
        await self.send(text_data=json.dumps({
            'message': event.get('message', ''),
            'sender': event['sender'],
            'sender_profile_picture': event['sender_profile_picture'],
            'timestamp': event['timestamp'],
            'attachment_url': event.get('attachment_url', None),
            'filetype': event.get('filetype', None)
        }))

    async def user_typing(self, event):
        # Broadcast the typing state to WebSocket clients
        await self.send(text_data=json.dumps({
            'type': 'typing',
            'username': event['username'],
            'is_typing': event['is_typing']
        }))

    async def message_read(self, event):
        # Format the read_at timestamp to match the format used for the "sent" timestamp
        read_at_time = datetime.datetime.fromisoformat(event['read_at']).strftime("%b %d, %Y %I:%M %p")

        # Send the read receipt event with the formatted read_at timestamp
        await self.send(text_data=json.dumps({
            'type': 'read_receipt',
            'message_id': event['message_id'],
            'read_at': read_at_time
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
            self.file_data.extend(bytes_data)  # Append incoming binary data

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

        return file_path