from django.db.models import Q
from .models import Message, Conversation

def unread_messages_count(request):
    if request.user.is_authenticated:
        # Counting unread messages in all conversations involving the user
        unread_count = Message.objects.filter(
            conversation__in=Conversation.objects.filter(
                Q(user1=request.user) | Q(user2=request.user) | Q(groupmember__user=request.user)
            ),
            is_read=False
        ).exclude(sender=request.user).count()
    else:
        unread_count = 0
    return {
        'unread_messages_count': unread_count
    }