import json
import base64
import uuid
import os
import logging
import mimetypes
from django.db.models import Q, F, Avg, Max, Min, Count, Case, When, IntegerField, BooleanField, ExpressionWrapper
from dashboard.Tasks import generate_video_thumbnail
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import moviepy
from moviepy import editor
from moviepy.editor import VideoFileClip
from django.db import transaction
from asgiref.sync import async_to_sync, sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
import re
from django.core.files.base import ContentFile
from django.conf import settings
from django.utils import timezone
import asyncio  # Ensure asyncio is imported at the top of the file
from .models import Conversation, Message, MutedConversation, User, Notification
from dashboard.generate_key import encrypt_message, decrypt_message
from datetime import datetime, timedelta
import logging
logger = logging.getLogger(__name__)

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group_name = f'chat_{self.conversation_id}'
        self.typing_users = set()

        # Join the room group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        # Leave the room group
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            if text_data:
                data = json.loads(text_data)
                message_type = data.get('type')

                if message_type == 'message':
                    await self.handle_new_message(data)
                elif message_type == 'edit_message':
                    await self.handle_edit_message(data)
                elif message_type == 'unsend_message':
                    await self.handle_unsend_message(data)
                elif message_type == 'delete_conversation':
                    await self.handle_delete_conversation()
                elif message_type == 'typing':
                    await self.handle_typing(data)
                else:
                    raise ValueError(f"Unknown message type: {message_type}")
        except json.JSONDecodeError:
            logger.error("Invalid JSON received.")
            await self.send_error("Invalid message format.")
        except Exception as e:
            logger.error(f"Error in receive: {e}")
            await self.send_error("Failed to process the message.")

    # Helper method for sending error messages
    async def send_error(self, message):
        await self.send(text_data=json.dumps({'type': 'error', 'message': message}))

    @database_sync_to_async
    def is_user_muted(self, user, conversation_id):
        # Check if the user has muted the conversation
        return MutedConversation.objects.filter(user=user, conversation_id=conversation_id).exists()

    async def handle_new_message(self, data):
        try:
            # Extract message content and attachment
            message_content = data.get('message', '').strip()
            attachment = data.get('attachment')

            if not message_content and not attachment:
                await self.send_error("Message or attachment required.")
                return

            # Save the message
            saved_message = await self.save_message(message_content or '[Attachment]')

            # Handle mentions
            mentioned_usernames = await self.extract_mentions(message_content)
            mentioned_users = await self.get_users_by_usernames(mentioned_usernames)
            await self.update_mentions_for_message(saved_message, mentioned_users)

            # Generate hyperlinks for mentions in the message
            hyperlinked_message = await self.generate_hyperlinked_message(message_content, mentioned_users)

            # Handle attachments
            attachment_url, attachment_type, thumbnail_url = None, None, None
            if attachment:
                attachment_url, attachment_type, thumbnail_url = await self.handle_attachment(saved_message, attachment)

            # Notify all recipients
            recipients_metadata = await self.get_recipient_and_metadata(saved_message)
            notified_users = set()  # Track users already notified

            # Notify general recipients
            for recipient_user, org_id, conversation_id in recipients_metadata:
                if recipient_user == self.scope['user']:
                    continue  # Skip notifying the sender

                # Skip muted users or conversations
                if await self.is_user_muted(recipient_user, conversation_id):
                    continue

                await self.notify_user(
                    recipient_user,
                    org_id,
                    conversation_id,
                    saved_message,
                    mentioned=False  # General recipients
                )
                notified_users.add(recipient_user.id)

            # Notify mentioned users explicitly
            for mentioned_user in mentioned_users:
                if mentioned_user.id in notified_users:
                    continue  # Skip if already notified

                await self.notify_user(
                    mentioned_user,
                    org_id=None,
                    conversation_id=self.conversation_id,
                    message=saved_message,
                    mentioned=True  # Special notification for mentioned users
                )
                notified_users.add(mentioned_user.id)

            # Broadcast the message to the group with mentions hyperlinked
            message_data = {
                'type': 'chat_message',
                'message': hyperlinked_message,  # Message with mentions as hyperlinks
                'sender': self.scope['user'].username,
                'sender_profile_picture': self.get_user_profile_picture(),
                'timestamp': saved_message.timestamp.isoformat(),
                'mentioned_users': mentioned_usernames,
                'attachment_url': attachment_url or '',
                'attachment_type': attachment_type or '',
                'thumbnail_url': thumbnail_url or '',
            }
            await self.channel_layer.group_send(self.room_group_name, message_data)

        except Exception as e:
            logger.error(f"Error handling new message: {e}")
            await self.send_error("Failed to send the message.")

    @database_sync_to_async
    def get_user_organization_id(self):
        """
        Retrieve the organization ID for the current user or conversation.
        """
        user = self.scope['user']
        if hasattr(user, 'organization') and user.organization:
            return user.organization.id
        else:
            # Fallback to the organization associated with the conversation
            conversation = Conversation.objects.get(id=self.conversation_id)
            if conversation.organization:
                return conversation.organization.id
        return None  # Return None if no organization is found

    async def generate_hyperlinked_message(self, message_content, mentioned_users):
        """
        Replace mentions in the message content with hyperlinks, including organization context.
        """
        # Retrieve organization ID from the current user or conversation context
        org_id = await self.get_user_organization_id()

        for user in mentioned_users:
            mention_pattern = f"@{user.username}"
            # Include the organization ID in the URL
            profile_url = f"/{org_id}/friend-info/{user.id}/"  # Adjust to match your URL structure
            hyperlink = f'<a href="{profile_url}" class="mention">@{user.username}</a>'
            message_content = message_content.replace(mention_pattern, hyperlink)

        return message_content

    async def handle_attachment(self, message, attachment):
        try:
            file_name = attachment.get('name')
            file_content = attachment.get('content')
            if file_name and file_content:
                await self.save_attachment(message, file_name, file_content)
                attachment_url = message.attachment.url
                mime_type, _ = mimetypes.guess_type(message.attachment.path)
                attachment_type = mime_type or 'unknown'
                thumbnail_url = None

                if mime_type and mime_type.startswith('video/'):
                    thumbnail_url = await self.generate_thumbnail(message)

                return attachment_url, attachment_type, thumbnail_url
        except Exception as e:
            logger.error(f"Error processing attachment: {e}")
            return None, None, None

    async def handle_edit_message(self, data):
        try:
            message_id = data.get('message_id')
            new_content = data.get('content', '').strip()

            if not message_id or not isinstance(message_id, int):
                await self.send_error("Invalid message ID.")
                return

            if not new_content:
                await self.send_error("Message content cannot be empty.")
                return

            # Fetch and update the message
            message = await self.get_message(message_id)
            if not message:
                await self.send_error("Message not found or permission denied.")
                return

            mentioned_usernames = await self.extract_mentions(new_content)
            mentioned_users = await self.get_users_by_usernames(mentioned_usernames)
            await self.update_mentions_for_message(message, mentioned_users)

            message.content = new_content
            message.edited_at = timezone.now()
            message.is_edited = True
            await database_sync_to_async(message.save)()

            # Broadcast the edited message
            await self.broadcast_edit(message)

        except Exception as e:
            logger.error(f"Error handling edit message: {e}")
            await self.send_error("Failed to edit the message.")

    async def extract_mentions(self, content):
        mention_pattern = r'@(\w+)'
        return re.findall(mention_pattern, content)

    @database_sync_to_async
    def get_users_by_usernames(self, usernames):
        return list(User.objects.filter(username__in=usernames))

    @database_sync_to_async
    def update_mentions_for_message(self, message, mentioned_users):
        message.mentions.set(mentioned_users)

    async def broadcast_edit(self, message):
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'edit_message',
                'message_id': message.id,
                'content': message.content,
                'is_edited': True,
                'mentioned_users': [user.username for user in message.mentions.all()],
                'timestamp': message.edited_at.isoformat(),
            },
        )
    async def notify_user(self, user, org_id, conversation_id, message, mentioned=False):
        """
        Send notifications to users, with custom messages for mentioned users.
        """
        decrypted_content = await self.get_decrypted_message_content(message)

        # Custom message for mentioned users
        if mentioned and user.id == self.scope['user'].id:
            
            notification_message = f"{self.scope['user'].username} mentioned you in the group chat '{message.conversation.name or 'a group chat'}'."
        else:
            # Generic notification for others
            notification_message = f"{self.scope['user'].username}: {decrypted_content[:50]}{'...' if len(decrypted_content) > 50 else ''}"
        logger.debug(f"Sending notification to {user.username}: {notification_message}")
        await self.channel_layer.group_send(
            f"user_{user.id}",
            {
                'type': 'notification_message',
                'message': notification_message,
                'org_id': org_id,
                'conversation_id': conversation_id,
                'sender': f"{self.scope['user'].first_name} {self.scope['user'].last_name}".strip() or self.scope['user'].username,
                'sender_profile_picture': self.get_user_profile_picture(),
                'conversation_url': f"/{org_id}/admin/conversation/{conversation_id}/",  # 👈 Use correct URL format
            }
        )
    def get_user_profile_picture(self):
        user = self.scope['user']
        return (
            user.profile_picture.url
            if hasattr(user, 'profile_picture') and user.profile_picture
            else '/static/img/default-profile.jpg'
        )
    @database_sync_to_async
    def get_message(self, message_id):
        try:
            message = Message.objects.filter(id=message_id, sender=self.scope['user']).first()
            if message:
                logger.debug(f"get_message: Fetched message ID={message.id}, content='{message.content}'")
            else:
                logger.warning(f"get_message: No message found for ID={message_id}")
            return message
        except Exception as e:
            logger.error(f"Error in get_message: {e}")
            return None

    async def broadcast_edit(self, message):
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'edit_message',
                'message_id': message.id,
                'content': message.content,
                'is_edited': message.is_edited,
                'timestamp': message.edited_at.isoformat(),
            }
        )

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
        logger.debug(f"chat_message() triggered with event: {event}")
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event.get('message', ''),  # Hyperlinked message content
            'sender': event.get('sender'),
            'sender_profile_picture': event.get('sender_profile_picture', '/static/img/default-profile.jpg'),
            'timestamp': event.get('timestamp'),
            'attachment_url': event.get('attachment_url'),
            'attachment_type': event.get('attachment_type', 'unknown'),
            'thumbnail_url': event.get('thumbnail_url'),  # Include thumbnail URL
        }))

    async def edit_message(self, event):
        """
        Handle the broadcast of an edited message to all clients.
        """
        logger.info(f"Broadcasting edited message ID: {event['message_id']} with content: {event['content']}")
        await self.send(text_data=json.dumps({
            'type': 'edit_message',
            'message_id': event['message_id'],
            'content': event['content'],
            'is_edited': event.get('is_edited', False),
            'timestamp': event['timestamp'],
        }))

    @database_sync_to_async
    def save_message_atomic(self, content, sender, conversation):
        with transaction.atomic():
            return Message.objects.create(content=content, sender=sender, conversation=conversation)
    @database_sync_to_async
    def save_message(self, content):
        """
        Save the message content to the database.
        """
        conversation = Conversation.objects.select_related('user1', 'user2').get(id=self.conversation_id)
        message = Message.objects.create(
            content=content,
            sender=self.scope['user'],
            conversation=conversation,
        )
        return message
    
    def generate_video_thumbnail(video_path):
        try:
            # Use moviepy to generate a thumbnail
            clip = VideoFileClip(video_path)
            thumbnail_name = f"{uuid.uuid4()}.jpg"
            thumbnail_path = os.path.join(settings.MEDIA_ROOT, "thumbnails", thumbnail_name)

            # Ensure the thumbnails directory exists
            os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)

            # Save the thumbnail
            clip.save_frame(thumbnail_path, t=0)
            clip.close()

            # Return the relative URL of the thumbnail
            return os.path.join(settings.MEDIA_URL, "thumbnails", thumbnail_name)
        except Exception as e:
            logger.error(f"Error generating thumbnail: {e}")
            return None
        
    @database_sync_to_async
    def save_attachment(self, message, file_name, file_content):
        """
        Decode and save the attachment file and generate a thumbnail if it's a video.
        """
        file_data = base64.b64decode(file_content)
        file_path = message.attachment.save(file_name, ContentFile(file_data), save=True)
        message.save()

    @database_sync_to_async
    def get_decrypted_message_content(self, message):
        """
        Decrypt the message content for display.
        """
        return message.get_decrypted_content()

    @database_sync_to_async
    def edit_message(self, message_id, new_content):
        try:
            logger.info(f"Editing message ID {message_id}: New content = {new_content}")
            message = Message.objects.get(id=message_id, sender=self.scope['user'])
            message.content = encrypt_message(new_content, message.sender)
            message.is_edited = True
            message.save()
            return message
        except Message.DoesNotExist:
            raise ValueError("Message not found or permission denied.")
    
    @csrf_exempt
    def upload_file(request):
        if request.method == 'POST' and request.FILES.get('file'):
            file = request.FILES['file']
            conversation_id = request.POST.get('conversation_id')
            user = request.user

            try:
                conversation = Conversation.objects.get(id=conversation_id)

                #    Save the file to the message
                message = Message.objects.create(
                    conversation=conversation,
                    sender=user,
                    content='[Attachment]',  # Placeholder
                )
                message.attachment.save(file.name, file)
                mime_type, _ = mimetypes.guess_type(message.attachment.path)
                if mime_type and mime_type.startswith('video/'):
                    thumbnail_url = generate_video_thumbnail.delay(message.attachment.path).get()
                    message.thumbnail_url = thumbnail_url
                    message.save()

                return JsonResponse({
                    'status': 'success',
                    'message_id': message.id,
                    'attachment_url': message.attachment.url,
                    'thumbnail_url': thumbnail_url,
                })

            except Exception as e:
                return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

        return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)
    
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
    @database_sync_to_async
    def get_recipient_and_metadata(self, message):
        conversation = message.conversation

        if conversation.type == 'private':
            recipient_user = (
                conversation.user2 if conversation.user1 == self.scope['user'] else conversation.user1
            )
            return [(recipient_user, recipient_user.organization.id if recipient_user.organization else None, conversation.id)]

        elif conversation.type == 'group':
            members = conversation.members_new.exclude(id=self.scope['user'].id)
            return [
                (member, member.organization.id if member.organization else None, conversation.id)
                for member in members
            ]

        return []  # Return an empty list if no valid recipients
    
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
class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user_group_name = f"user_{self.scope['user'].id}"
        if self.scope["user"].is_authenticated:
            # Add the user to their notification group
            await self.channel_layer.group_add(
                self.user_group_name,
                self.channel_name,
            )
            await self.accept()
            logging.info(f"User {self.scope['user'].id} connected to notifications group.")
        else:
            await self.close()

    async def disconnect(self, close_code):
        if self.scope["user"].is_authenticated:
            # Remove the user from their notification group
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name,
            )
            logging.info(f"User {self.scope['user'].id} disconnected from notifications group.")

    # Receive notification messages
    async def notification_message(self, event):
        message = event["message"]
        org_id = event.get("org_id")
        conversation_id = event.get("conversation_id")
    
        await self.send(text_data=json.dumps({
            "type": "message",
            "message": event["message"],
            "org_id": event.get("org_id"),
            "conversation_id": event.get("conversation_id"),
            "sender": event.get("sender", "Unknown User"),
            "sender_profile_picture": event.get("sender_profile_picture", "/static/img/default-profile.jpg"),
            "conversation_url": event.get("conversation_url"),  # 👈 Ensure this is passed to frontend
        }))