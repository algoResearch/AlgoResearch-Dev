from dashboard.models import Message, Conversation, MessageUser
def create_message_user_entries(message, conversation):
    """
    Ensure MessageUser entries exist for all conversation participants.
    """
    if conversation.type == 'private':
        user_ids = [conversation.user1_id, conversation.user2_id]
    else:
        user_ids = conversation.group_members.values_list('user_id', flat=True)

    bulk_create = []
    for user_id in user_ids:
        bulk_create.append(MessageUser(user_id=user_id, message=message))

    MessageUser.objects.bulk_create(bulk_create, ignore_conflicts=True)
