from django.db.models import Q, Count
from .models import Message, Conversation, InboxNotification
from django.conf import settings

def default_profile_picture(request):
    return {'DEFAULT_PROFILE_PICTURE': settings.DEFAULT_PROFILE_PICTURE}

def unread_conversations_count(request):
    if request.user.is_authenticated:
        # Filter conversations with unread messages
        conversations_with_unread = Conversation.objects.filter(
            Q(messages__is_read=False),
            Q(user1=request.user) | Q(user2=request.user) | Q(groupmember__user=request.user)
        ).exclude(messages__sender=request.user).distinct()

        # Count the conversations with unread messages
        total_unread_conversations = conversations_with_unread.count()

        # Unread notifications for the Inbox
        total_unread_notifications = InboxNotification.objects.filter(
            user=request.user, is_read=False
        ).count()
    else:
        total_unread_conversations = 0
        total_unread_notifications = 0

    print(f"Context processor executed for: {request.path}")
    print(f"Unread conversations count for {request.path}: {total_unread_conversations}")

    return {
        'unread_conversations_count': total_unread_conversations,
        'unread_notifications_count': total_unread_notifications,
    }
