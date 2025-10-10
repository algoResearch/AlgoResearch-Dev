from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import logging

logger = logging.getLogger(__name__)

def notify_user_ws(user, sender, message, org_id, conversation_id, mentioned=False, request_path=""):
    """
    Send WebSocket notification to a user. This function can be called from views or consumers.
    """
    try:
        preview = message.get_decrypted_content()[:50]
        sender_name = f"{sender.first_name} {sender.last_name}".strip() or sender.username

        if mentioned and user.id != sender.id:
            convo_name = message.conversation.name or "a group chat"
            notification_message = f"{sender.username} mentioned you in '{convo_name}'."
        else:
            notification_message = f"{sender.username}: {preview}{'...' if len(preview) == 50 else ''}"

        is_admin = request_path.startswith(f"/{org_id}/admin/")
        conversation_url = (
            f"/{org_id}/admin/conversation/{conversation_id}/"
            if is_admin else f"/{org_id}/conversation/{conversation_id}/"
        )

        profile_pic = (
            sender.profile_picture.url
            if hasattr(sender, 'profile_picture') and sender.profile_picture
            else '/static/img/default-profile.jpg'
        )

        async_to_sync(get_channel_layer().group_send)(
            f"user_{user.id}",
            {
                'type': 'notification_message',
                'message': notification_message,
                'org_id': org_id,
                'conversation_id': conversation_id,
                'sender': sender_name,
                'sender_profile_picture': profile_pic,
                'conversation_url': conversation_url,
            }
        )
        logger.debug(f"📢 Sent notification to {user.username}")
    except Exception as e:
        logger.error(f"Failed to notify {user.username}: {e}")
