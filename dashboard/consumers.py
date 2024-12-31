import json
import base64
import os
import logging
import mimetypes
from asgiref.sync import async_to_sync
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.files.base import ContentFile
from django.conf import settings
import asyncio  # Ensure asyncio is imported at the top of the file
from .models import Conversation, Message
from dashboard.generate_key import encrypt_message, decrypt_message
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group_name = f'chat_{self.conversation_id}'
        self.typing_users = set()  # Initialize typing_users for this instance

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
        try:
            if text_data:
                text_data_json = json.loads(text_data)
                message_type = text_data_json.get('type')

                if message_type == 'message':
                    await self.handle_new_message(text_data_json)
                elif message_type == 'edit_message':
                    await self.handle_edit_message(text_data_json)
                elif message_type == 'unsend_message':
                    await self.handle_unsend_message(text_data_json)
                elif message_type == 'delete_conversation':
                    await self.handle_delete_conversation()
                elif message_type == 'typing':
                    await self.handle_typing(text_data_json)
        except Exception as e:
            logger.error(f"Error in receive: {e}")
            await self.send(text_data=json.dumps({'type': 'error', 'message': 'Invalid message format.'}))

    async def handle_new_message(self, data):
        try:
            # Extract message content and attachment details
            message_content = data.get('message', '').strip()
            attachment = data.get('attachment', None)

            # Ensure that either text or attachment exists
            if not message_content and not attachment:
                await self.send(text_data=json.dumps({'type': 'error', 'message': 'Message cannot be empty.'}))
                return

            # For database, use a placeholder if only an attachment exists
            db_content = message_content or '[Attachment]'
            saved_message = await self.save_message(db_content)

            # Handle file attachment if provided
            attachment_url = None
            attachment_type = None
            if attachment:
                file_name = attachment.get('name')
                file_content = attachment.get('content')

                if file_name and file_content:
                    await self.save_attachment(saved_message, file_name, file_content)
                    attachment_url = saved_message.attachment.url
                    mime_type, _ = mimetypes.guess_type(saved_message.attachment.path)
                    attachment_type = mime_type or 'unknown'

            # Decrypt content for display
            decrypted_content = await self.get_decrypted_message_content(saved_message)

            # Prepare message data for the group
            message_data = {
                'type': 'chat_message',
                'message': decrypted_content if message_content else '',  # Include decrypted content if present
                'sender': self.scope['user'].username,
                'sender_profile_picture': self.scope['user'].profile_picture.url
                if self.scope['user'].profile_picture else '/static/img/default-profile.jpg',
                'timestamp': saved_message.timestamp.isoformat(),
                'attachment_url': attachment_url,
                'attachment_type': attachment_type,
            }

            # Broadcast the message to the WebSocket group
            await self.channel_layer.group_send(self.room_group_name, message_data)

        except Exception as e:
            logger.error(f"Error handling new message: {e}")
            await self.send(text_data=json.dumps({'type': 'error', 'message': 'Failed to handle new message.'}))

    async def handle_edit_message(self, data):
        try:
            message_id = data['message_id']
            new_content = data['new_content']

            updated_message = await self.edit_message(message_id, new_content)

            # Broadcast the updated message to the group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'edit_message',
                    'message_id': updated_message.id,
                    'content': updated_message.get_decrypted_content(),
                    'is_edited': True,
                }
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")

    async def handle_unsend_message(self, data):
        try:
            message_id = data['message_id']

            unsent_message = await self.unsend_message(message_id)

            # Notify the group that the message was unsent
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'unsend_message',
                    'message_id': unsent_message.id,
                }
            )
        except Exception as e:
            logger.error(f"Error unsending message: {e}")

    async def handle_delete_conversation(self):
        try:
            deleted_conversation_id = await self.delete_conversation()

            # Notify the group that the conversation was deleted
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'delete_conversation',
                    'conversation_id': deleted_conversation_id,
                }
            )
        except Exception as e:
            logger.error(f"Error deleting conversation: {e}")

    typing_users = {}

    async def handle_typing(self, data):
        is_typing = data.get('is_typing', False)
        username = self.scope['user'].username

        if is_typing:
            self.typing_users[username] = datetime.now()
        else:
            self.typing_users.pop(username, None)

        # Clean up expired typing indicators
        now = datetime.now()
        self.typing_users = {
            user: timestamp for user, timestamp in self.typing_users.items()
            if now - timestamp < timedelta(seconds=20)
        }

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_typing',
                'typing_users': list(self.typing_users.keys())
            }
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event.get('message', ''),
            'sender': event.get('sender'),
            'sender_profile_picture': event.get('sender_profile_picture', '/static/img/default-profile.jpg'),
            'timestamp': event.get('timestamp'),
            'attachment_url': event.get('attachment_url'),
            'attachment_type': event.get('attachment_type', 'unknown'),
        }))

    @database_sync_to_async
    def save_message(self, content):
        """
        Save the message content to the database.
        """
        conversation = Conversation.objects.get(id=self.conversation_id)
        message = Message.objects.create(
            content=content,
            sender=self.scope['user'],
            conversation=conversation,
        )
        return message

    @database_sync_to_async
    def save_attachment(self, message, file_name, file_content):
        """
        Decode and save the attachment file.
        """
        file_data = base64.b64decode(file_content)
        message.attachment.save(file_name, ContentFile(file_data), save=True)
        message.save()

    @database_sync_to_async
    def get_decrypted_message_content(self, message):
        """
        Decrypt the message content for display.
        """
        return message.get_decrypted_content()

    @database_sync_to_async
    def edit_message(self, message_id, new_content):
        message = Message.objects.get(id=message_id)
        if message.sender == self.scope['user']:
            message.content = message._encrypt_content(new_content)
            message.is_edited = True
            message.save()
        return message

    @database_sync_to_async
    def unsend_message(self, message_id):
        message = Message.objects.get(id=message_id)
        if message.sender == self.scope['user']:
            message.is_deleted = True
            message.content = '[Message was unsent]'
            message.save()
        return message

    @database_sync_to_async
    def delete_conversation(self):
        conversation = Conversation.objects.get(id=self.conversation_id)
        conversation_id = conversation.id
        if conversation.user1 == self.scope['user'] or conversation.user2 == self.scope['user']:
            conversation.messages.all().delete()
            conversation.delete()
        return conversation_id
    
class FileTransferConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        self.file_path = None

    async def receive(self, text_data=None, bytes_data=None):
        if text_data:
            data = json.loads(text_data)
            if data.get('type') == 'file_metadata':
                file_name = data['metadata']['filename']
                upload_dir = os.path.join(settings.MEDIA_ROOT, 'uploads')
                os.makedirs(upload_dir, exist_ok=True)
                self.file_path = os.path.join(upload_dir, file_name)
                self.file = open(self.file_path, 'wb')  # Open file for writing

        if bytes_data:
            if self.file:
                self.file.write(bytes_data)

        # Close file after all chunks are received
        if self.file and text_data and json.loads(text_data).get('type') == 'file_complete':
            self.file.close()
            await self.send(json.dumps({'status': 'success', 'file_path': self.file_path}))

    @database_sync_to_async
    def save_file(self):
        # Save the file in the specified directory
        file_name = self.file_metadata['filename']
        upload_path = os.path.join(settings.MEDIA_ROOT, 'uploads', file_name)

        os.makedirs(os.path.dirname(upload_path), exist_ok=True)  # Ensure the directory exists
        with open(upload_path, 'wb') as f:
            f.write(self.file_data)

        return upload_path
    