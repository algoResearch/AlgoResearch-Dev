from django.db.models import Q
from .models import Message, Conversation, InboxNotification

def unread_conversations_count(request):
    if request.user.is_authenticated:
        # Count unread messages where the user is either user1, user2, or part of a group conversation
        total_unread_messages = Message.objects.filter(
            Q(conversation__user1=request.user) | 
            Q(conversation__user2=request.user) | 
            Q(conversation__groupmember__user=request.user),
            is_read=False
        ).exclude(sender=request.user).count()

        # Count unread notifications for the Inbox
        total_unread_notifications = InboxNotification.objects.filter(
            user=request.user, is_read=False
        ).count()
    else:
        total_unread_messages = 0
        total_unread_notifications = 0

    return {
        'unread_conversations_count': total_unread_messages,
        'unread_notifications_count': total_unread_notifications,  # For the Inbox
    }