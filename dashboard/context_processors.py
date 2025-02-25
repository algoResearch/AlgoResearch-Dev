from django.db.models import Q, Count
from .models import Message, Conversation, InboxNotification, GroupMember, Message, PDFTemplate
from django.conf import settings

def default_profile_picture(request):
    return {'DEFAULT_PROFILE_PICTURE': settings.DEFAULT_PROFILE_PICTURE}

# Add logging to debug context processor
import logging

logger = logging.getLogger(__name__)
# In your app's context_processors.py
def organization_context(request):
    if request.user.is_authenticated and hasattr(request.user, 'organization'):
        return {
            'user': request.user,
            'organization': request.user.organization,
        }
    return {}

def default_form_context(request):
    """Provides the default form ID for navigation"""
    if request.user.is_authenticated and hasattr(request.user, 'organization'):
        org_id = request.user.organization.id
        default_form = PDFTemplate.objects.filter(organization_id=org_id).first()
        return {"default_form_id": default_form.id if default_form else None}
    return {"default_form_id": None}

def unread_conversations_count(request):
    if request.user.is_authenticated:
        try:
            conversations_with_unread = Conversation.objects.filter(
                Q(messages__is_read=False),
                Q(user1=request.user) | Q(user2=request.user) | Q(group_members__user=request.user)
            ).exclude(messages__sender=request.user).distinct()

            total_unread_conversations = conversations_with_unread.count()
            total_unread_notifications = InboxNotification.objects.filter(
                user=request.user, is_read=False
            ).count()

            # Log the counts
            logger.debug(f"Unread conversations: {total_unread_conversations}, Unread notifications: {total_unread_notifications}")
        except Exception as e:
            logger.error(f"Error in unread_conversations_count: {e}")
            total_unread_conversations = 0
            total_unread_notifications = 0
    else:
        total_unread_conversations = 0
        total_unread_notifications = 0

    return {
        'unread_conversations_count': total_unread_conversations,
        'unread_notifications_count': total_unread_notifications,
    }