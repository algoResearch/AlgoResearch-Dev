import json
import base64
import uuid
import os
import logging
import re
import mimetypes
from django.db.models import Q, F, Avg, Max, Min, Count, Case, When, IntegerField, BooleanField, ExpressionWrapper
from dashboard.Tasks import generate_video_thumbnail
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from moviepy.editor import VideoFileClip
from django.db import transaction
from asgiref.sync import async_to_sync, sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.files.base import ContentFile
from django.conf import settings
from django.utils import timezone
import asyncio  # Ensure asyncio is imported at the top of the file
from .models import Conversation, Message, MutedConversation
from dashboard.generate_key import encrypt_message, decrypt_message
from datetime import datetime, timedelta
import logging
logger = logging.getLogger(__name__)


def extract_mentions(content):
    """
    Extract all mentioned usernames from the message content.
    """
    return re.findall(r'@(\w+)', content)

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

    async def handle_read_receipt(self, data):
        """
        Mark the latest message as read and notify the conversation group.
        """
        message_ids = data.get("message_ids", [])
        user = self.scope["user"]

        if not message_ids:
            return

        # Fetch the latest unread message for the current user
        try:
            latest_message = await database_sync_to_async(Message.objects.filter)(
                id__in=message_ids,
                conversation_id=self.conversation_id,
                sender__ne=user,
                is_read=False
            ).latest('timestamp')
        
            # Mark it as read
            latest_message.is_read = True
            latest_message.read_timestamp = datetime.now()
            await database_sync_to_async(latest_message.save)()

            # Broadcast to the group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "read_receipt",
                    "message_id": latest_message.id,
                    "read_timestamp": latest_message.read_timestamp.isoformat(),
                    "sender": user.username,  # Optionally include sender for verification
                }
            )
        except Message.DoesNotExist:
            # No unread messages found
            pass

    @database_sync_to_async
    def is_muted(self, sender, recipient):
        """
        Check if the recipient has muted the sender.
        """
        return Conversation.objects.filter(
            (Q(user1=sender, user2=recipient) | Q(user1=recipient, user2=sender)),
            is_muted=True,
        ).exists()
    @database_sync_to_async
    def update_message_atomic(self, message, new_content):
        with transaction.atomic():
            message.content = new_content
            message.edited_at = timezone.now()
            message.is_edited = True
            message.save()
    
    async def read_receipt(self, event):
        await self.send(text_data=json.dumps({
            "type": "read_receipt",
            "message_id": event["message_id"],
            "read_timestamp": event["read_timestamp"],
        }))
    async def handle_new_message(self, data):
        try:
            # Extract message content and attachment details
            message_content = data.get('message', '').strip() if data.get('message') else ''
            attachment = data.get('attachment', None)

            # Ensure that either text or attachment exists
            if not message_content and not attachment:
                await self.send(text_data=json.dumps({'type': 'error', 'message': 'Message or attachment required.'}))
                return
            mentions = extract_mentions(message_content)
            # Save the message in the database
            db_content = message_content or '[Attachment]'
            saved_message = await self.save_message(db_content)
            if mentions:
                await self.notify_mentioned_users(saved_message, mentions)
            # Prepare attachment details
            attachment_url = None
            attachment_type = None
            thumbnail_url = None

            if attachment:
                file_name = attachment.get('name')
                file_content = attachment.get('content')
                if file_name and file_content:
                    await self.save_attachment(saved_message, file_name, file_content)
                    attachment_url = saved_message.attachment.url
                    mime_type, _ = mimetypes.guess_type(saved_message.attachment.path)
                    attachment_type = mime_type or 'unknown'

                    # Process video attachments to generate thumbnails
                    if mime_type and mime_type.startswith('video/'):
                        await self.process_attachment(saved_message)
                        thumbnail_url = saved_message.thumbnail_url

            # Prepare the message payload for WebSocket broadcast
            decrypted_content = await self.get_decrypted_message_content(saved_message)
            sender_profile_picture = (
                self.scope['user'].profile_picture.url
                if getattr(self.scope['user'], 'profile_picture', None) and hasattr(self.scope['user'].profile_picture, 'url')
                else '/static/img/default-profile.jpg'
            )
            message_data = {
                'type': 'chat_message',
                'message': decrypted_content if message_content else '',
                'sender': self.scope['user'].username,
                'sender_profile_picture': sender_profile_picture,
                'timestamp': saved_message.timestamp.isoformat(),
                'attachment_url': attachment_url,
                'attachment_type': attachment_type,
                'thumbnail_url': thumbnail_url,
            }

            # Broadcast the message to the conversation group
            await self.channel_layer.group_send(self.room_group_name, message_data)

            # Notify recipients of the new message
            recipients_metadata = await self.get_recipient_and_metadata(saved_message)
            if not recipients_metadata:
                raise ValueError("No recipients found for the message.")

            for recipient_user, org_id, conversation_id in recipients_metadata:
                # Check if the user has muted all notifications
                if recipient_user.mute_all_notifications:
                    continue  # Skip this user

                # Check if the conversation is muted for the user
                is_muted = await database_sync_to_async(
                    lambda: Conversation.objects.filter(
                        id=conversation_id, mute_notifications=recipient_user
                    ).exists()
                )()

                if is_muted:
                    continue  # Skip notifications for muted conversations

                # Prepare and send notification message
                notification_message = {
                    'type': 'notification_message',
                    'message': f"{decrypted_content[:50]}",
                    'org_id': org_id,
                    'conversation_id': conversation_id,
                    'sender': f"{self.scope['user'].first_name} {self.scope['user'].last_name}".strip() or self.scope['user'].username,
                    'sender_profile_picture': (
                        self.scope['user'].profile_picture.url
                        if getattr(self.scope['user'], 'profile_picture', None) and hasattr(self.scope['user'].profile_picture, 'url')
                        else '/static/img/default-profile.jpg'
                    ),
                }
                await self.channel_layer.group_send(
                    f"user_{recipient_user.id}",  # Notify recipient's WebSocket group
                    notification_message
                )

        except ValueError as ve:
            logger.error(f"ValueError: {ve}")
            await self.send(text_data=json.dumps({'type': 'error', 'message': str(ve)}))
        except Exception as e:
            logger.error(f"Error handling new message: {e}")
            await self.send(text_data=json.dumps({'type': 'error', 'message': 'Failed to handle new message.'}))

    async def process_attachment(self, saved_message):
        """
        Process the saved attachment, specifically generating a thumbnail for video files.
        """
        try:
            if saved_message.attachment and saved_message.attachment.path:
                mime_type, _ = mimetypes.guess_type(saved_message.attachment.path)
                if mime_type and mime_type.startswith('video/'):
                    logger.info(f"Starting thumbnail generation for video: {saved_message.attachment.path}")

                    # Call Celery task synchronously and wait for result
                    thumbnail_url = await sync_to_async(generate_video_thumbnail.delay)(saved_message.id)
                    thumbnail_url = thumbnail_url.get()  # Retrieve the result of the Celery task

                    if thumbnail_url:
                        # Update the saved_message instance
                        saved_message.thumbnail_url = thumbnail_url
                        await database_sync_to_async(saved_message.save)(update_fields=['thumbnail_url'])
                    else:
                        logger.warning(f"Failed to generate thumbnail for Message ID {saved_message.id}")

        except Exception as e:
            logger.error(f"Error processing attachment: {e}")

    async def update_thumbnail(self, event):
        await self.send(text_data=json.dumps({
            'type': 'update_thumbnail',
            'message_id': event['message_id'],
            'thumbnail_url': event['thumbnail_url'],
    }))
    async def notify_mentioned_users(self, message, mentions):
        """
        Notify users mentioned in the message.
        """
        mentioned_users = await database_sync_to_async(
            lambda: User.objects.filter(username__in=mentions)
        )()

        for user in mentioned_users:
            # Skip notifying the sender
            if user.id == self.scope['user'].id:
                continue

            # Create a notification in the database
            await database_sync_to_async(Notification.objects.create)(
                user=user,
                message=f"You were mentioned in a conversation: {message.conversation.name}",
                conversation=message.conversation,
                sender=message.sender,
            )

            # Send WebSocket notification to the user
            await self.channel_layer.group_send(
                f"user_{user.id}",
                {
                    'type': 'notification_message',
                    'message': f"You were mentioned by {message.sender.username}: {message.content[:50]}",
                    'conversation_id': message.conversation.id,
                    'sender': message.sender.username,
                    'sender_profile_picture': message.sender.profile_picture.url if message.sender.profile_picture else '/static/img/default-profile.jpg',
                    'timestamp': message.timestamp.isoformat(),
                }
            )

    async def handle_edit_message(self, data):
        try:
            logger.debug(f"Received edit payload: {data}")

            # Extract and validate parameters
            message_id = data.get('message_id')
            new_content = data.get('content', '').strip()

            if not message_id or not isinstance(message_id, int):
                logger.warning(f"Invalid message ID received: {message_id}")
                await self.send(text_data=json.dumps({'type': 'error', 'message': 'Invalid message ID.'}))
                return

            if not new_content:
                logger.warning("Content is empty.")
                await self.send(text_data=json.dumps({'type': 'error', 'message': 'Message content cannot be empty.'}))
                return

            # Fetch the message
            message = await self.get_message(message_id)
            if not message:
                logger.warning(f"Message not found or unauthorized: ID={message_id}")
                await self.send(text_data=json.dumps({'type': 'error', 'message': 'Message not found or permission denied.'}))
                return

            logger.debug(f"Fetched message: ID={message.id}, content='{message.content}'")

            # Update the message
            message.content = new_content
            message.edited_at = timezone.now()
            message.is_edited = True
            await database_sync_to_async(message.save)()

            logger.info(f"Message ID {message_id} successfully edited.")

            # Broadcast the updated message
            await self.broadcast_edit(message, new_content)

        except Exception as e:
            logger.error(f"Error in handle_edit_message: {e}")
            await self.send(text_data=json.dumps({'type': 'error', 'message': 'Failed to edit the message.'}))
        async def validate_edit_parameters(self, message_id, content):
            return isinstance(message_id, int) and isinstance(content, str) and content.strip()


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
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event.get('message', ''),
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
        """
        Handle notifications sent to the user group.
        """
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'message': event['message'],
            'conversation_id': event['conversation_id'],
            'sender': event['sender'],
            'sender_profile_picture': event.get('sender_profile_picture', '/static/img/default-profile.jpg'),
            'timestamp': event['timestamp'],
        }))