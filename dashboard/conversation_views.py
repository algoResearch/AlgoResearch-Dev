from django.contrib import messages
from django.core import serializers
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.utils.timezone import now
from django.contrib.auth.decorators import login_required
import time
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q, F, Avg, Max, Min, Count
from django.utils import timezone
from django.utils.timezone import localtime
from .models import (Conversation, Message, User, Notification, ConversationUser, Organization, InboxNotification, GroupMember, EventInvitation, Experiment, RFIDAssignment, WeightMeasurement, Collaborator, CalendarEvent, Comment, Friend, Cage, Animal, Sample, Dose, Observation, Comment)
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, authenticate
from django.contrib.messages import error  # Import specifically if needed
import pandas as pd
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
import mimetypes
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import random
from django.contrib.auth import logout
from django.db import IntegrityError
from .forms import CustomUserCreationForm, UpdateProfileForm, ExperimentForm, UpdateGroupInfoForm
import json
from django.http import HttpResponseRedirect
from django.utils.safestring import mark_safe
from .forms import UserProfileForm
from .forms import ProfilePictureForm, MessageForm
from .forms import UpdateProfileForm, OverviewForm, ObservationForm, SampleForm, DoseForm
from django.views.decorators.http import require_http_methods
from django.utils.dateparse import parse_datetime
import csv
from .models import Invitation
from django.templatetags.static import static
from datetime import date
from django.utils import timezone
import pytz
from django.db.models import Prefetch

channel_layer = get_channel_layer()

import logging
# Assuming you have access to request.user and the last_message_time is in UTC.

logger = logging.getLogger('performance')
# Set up logging
def fetch_messages(request, org_id):
    user = request.user
    organization = get_object_or_404(Organization, id=org_id)

    active_tab = request.GET.get("tab", "messages")
    conversation_list = []
    total_unread_count = 0

    if active_tab == "messages":
        conversations = Conversation.objects.filter(
            Q(user1=user) | Q(user2=user) | Q(groupmember__user=user),
            organization=organization
        ).annotate(
            last_message_time=Max('messages__timestamp')
        ).prefetch_related(
            Prefetch(
                'messages',
                queryset=Message.objects.order_by('-timestamp'),
                to_attr='prefetched_messages'
            )
        ).order_by('-last_message_time')

        for convo in conversations:
            if convo.type == 'private':
                other_user = convo.user2 if convo.user1 == user else convo.user1
                name = other_user.username
                profile_picture = (
                    other_user.profile_picture.url if other_user.profile_picture
                    else static("img/default-profile.jpg")
                )
            else:
                name = convo.name.strip() if convo.name and convo.name.strip() else "Unnamed Group"
                profile_picture = (
                    convo.profile_picture.url if convo.profile_picture
                    else static("img/group-default.png")
                )

            unread_count = convo.messages.filter(is_read=False).exclude(sender=user).count()
            total_unread_count += unread_count

            last_message = convo.prefetched_messages[0] if convo.prefetched_messages else None
            last_message_preview = last_message.get_decrypted_content() if last_message else ""
            if last_message and last_message.attachment:
                if last_message.attachment.name.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    last_message_preview = "[Image]"
                elif last_message.attachment.name.endswith(('.pdf', '.doc', '.docx', '.xlsx', '.csv')):
                    last_message_preview = "[File]"

            conversation_list.append({
                'id': convo.id,
                'name': name,
                'type': convo.type,
                'profile_picture': profile_picture,
                'unread_count': unread_count,
                'last_message_time': timezone.localtime(convo.last_message_time),
                'last_message_preview': last_message_preview,
            })

    return render(request, 'conversations.html', {
        'conversations': conversation_list if active_tab == "messages" else [],
        'unread_conversations_count': total_unread_count,
        'organization': organization,
        'org_id': org_id,
        'active_tab': active_tab
    })

def get_invitation_response(event_id, user_id):
    try:
        invitation = EventInvitation.objects.get(event_id=event_id, invited_user_id=user_id)
        return invitation.status  # 'accepted', 'declined', or other possible states
    except EventInvitation.DoesNotExist:
        return None
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils.timezone import localtime
from django.templatetags.static import static
from django.db.models import Max, Q
import logging

logger = logging.getLogger(__name__)

@login_required
def conversation_view(request, org_id, conversation_id):
    user = request.user
    organization = get_object_or_404(Organization, id=org_id)

    # Fetch the selected conversation
    conversation = get_object_or_404(Conversation, id=conversation_id, organization=organization)

    # Determine conversation type and set profile picture and name
    if conversation.type == 'private':
        other_user = conversation.user2 if conversation.user1 == user else conversation.user1
        profile_picture = (
            other_user.profile_picture.url if other_user.profile_picture
            else static("img/default-profile.jpg")
        )
        conversation_name = other_user.get_full_name() or other_user.username or "Unnamed User"
    else:  # For group conversations
        profile_picture = (
            conversation.profile_picture.url if conversation.profile_picture
            else static("img/group-default.png")
        )
        conversation_name = conversation.name.strip() if conversation.name and conversation.name.strip() else "Unnamed Group"
        logger.debug(f"Group conversation profile picture: {profile_picture}")

    # Fetch sidebar conversations
    conversations = Conversation.objects.filter(
        Q(user1=user) | Q(user2=user) | Q(groupmember__user=user),
        organization=organization
    ).annotate(
        last_message_time=Max('messages__timestamp')
    ).order_by('-last_message_time')

    conversation_list = []
    for convo in conversations:
        if convo.type == 'private':
            other_user = convo.user2 if convo.user1 == user else convo.user1
            name = other_user.get_full_name() or other_user.username or "Unnamed User"
            profile_picture = (
                other_user.profile_picture.url if other_user.profile_picture
                else static("img/default-profile.jpg")
            )
        else:  # Group conversations
            name = convo.name.strip() if convo.name and convo.name.strip() else "Unnamed Group"
            profile_picture = (
                convo.profile_picture.url if convo.profile_picture
                else static("img/group-default.png")
            )

        conversation_list.append({
            'id': convo.id,
            'name': name,
            'type': convo.type,
            'profile_picture': profile_picture,
            'last_message_time': localtime(convo.last_message_time) if convo.last_message_time else None,
            'unread_count': convo.messages.filter(is_read=False).exclude(sender=user).count(),
        })

    # Fetch messages for the current conversation
    messages = Message.objects.filter(conversation=conversation).order_by('timestamp')
    decrypted_messages = [
        {
            'sender': msg.sender,
            'content': msg.get_decrypted_content(),
            'timestamp': msg.timestamp.isoformat(),
            'attachment': msg.attachment.url if msg.attachment else None,
            'is_image': msg.attachment.name.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')) if msg.attachment else False,
            'is_pdf': msg.attachment.name.lower().endswith('.pdf') if msg.attachment else False,
        }
        for msg in messages
    ]

    # Prepare the context for rendering
    context = {
        'conversation': conversation,
        'conversation_name': conversation_name,
        'profile_picture': profile_picture,
        'messages': decrypted_messages,
        'org_id': org_id,
        'selected_conversation_id': conversation_id,
        'active_tab': 'messages',
        'conversations': conversation_list,
    }

    return render(request, 'conversations.html', context)

@login_required
def conversation(request, org_id, conversation_id):
    user = request.user
    organization = get_object_or_404(Organization, id=org_id)

    # Fetch the specific conversation
    conversation = get_object_or_404(
        Conversation.objects.prefetch_related('groupmember__user'),
        id=conversation_id,
        organization=organization
    )

    # Determine conversation name and profile picture
    if conversation.type == 'private':
        other_user = conversation.user2 if conversation.user1 == user else conversation.user1
        conversation_name = other_user.get_full_name() or other_user.username or "Unnamed User"
        profile_picture = (
            other_user.profile_picture.url if other_user.profile_picture
            else static("img/default-profile.jpg")
        )
    else:  # Group conversation
        conversation_name = conversation.name.strip() if conversation.name and conversation.name.strip() else "Unnamed Group"
        profile_picture = (
            conversation.profile_picture.url if conversation.profile_picture
            else static("img/group-default.png")
        )

    # Fetch group members if the conversation is a group
    group_members = (
        GroupMember.objects.filter(conversation=conversation).select_related('user')
        if conversation.type == 'group'
        else None
    )

    # Prepare sidebar conversations
    conversations = Conversation.objects.filter(
        Q(user1=user) | Q(user2=user) | Q(groupmember__user=user),
        organization=organization
    ).annotate(
        last_message_time=Max('messages__timestamp')
    ).order_by('-last_message_time')

    conversation_list = []
    for convo in conversations:
        if convo.type == 'private':
            other_user = convo.user2 if convo.user1 == user else convo.user1
            name = other_user.get_full_name() or other_user.username or "Unnamed User"
            convo_picture = (
                other_user.profile_picture.url if other_user.profile_picture
                else static("img/default-profile.jpg")
            )
        else:
            name = convo.name.strip() if convo.name and convo.name.strip() else "Unnamed Group"
            convo_picture = (
                convo.profile_picture.url if convo.profile_picture
                else static("img/group-default.png")
            )

        conversation_list.append({
            'id': convo.id,
            'name': name,
            'type': convo.type,
            'profile_picture': convo_picture,
            'last_message_time': timezone.localtime(convo.last_message_time) if convo.last_message_time else None,
            'unread_count': convo.messages.filter(is_read=False).exclude(sender=user).count(),
        })

    # Decrypt and prepare messages for display
    messages = Message.objects.filter(conversation=conversation).order_by('timestamp')
    decrypted_messages = [
        {
            'sender': msg.sender,
            'content': msg.get_decrypted_content(),
            'timestamp': msg.timestamp.isoformat(),
            'is_read': msg.is_read,
            'attachment': msg.attachment.url if msg.attachment else None,
            'is_image': msg.attachment.name.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')) if msg.attachment else False,
            'is_pdf': msg.attachment.name.lower().endswith('.pdf') if msg.attachment else False,
        }
        for msg in messages
    ]

    # Mark messages as read for the current user
    messages.exclude(sender=user).update(is_read=True)

    # Prepare context
    context = {
        'conversations': conversation_list,
        'conversation': conversation,
        'conversation_name': conversation_name,
        'profile_picture': profile_picture,
        'messages': decrypted_messages,
        'selected_conversation_id': conversation_id,
        'org_id': org_id,
        'active_tab': 'messages',
        'group_members': group_members,
    }

    return render(request, 'conversations.html', context)


@login_required
def notification_conversation(request, org_id, notification_id):
    user = request.user
    organization = get_object_or_404(Organization, id=org_id)
    
    # Handle tab switching
    active_tab = request.GET.get('tab')
    if active_tab == 'messages':
        return redirect('messages', org_id=org_id) + '?tab=messages'

    notification = get_object_or_404(InboxNotification, id=notification_id, user=user)

    # Mark as read if unread
    if not notification.is_read:
        notification.is_read = True
        notification.save()

    # Set sender_name based on whether it's from an admin or another user
    sender_name = "Organization" if notification.from_admin else (notification.sender.username if notification.sender else "Unknown")

    messages = [{
        'sender': sender_name,
        'content': notification.message,
        'timestamp': notification.timestamp,
        'is_read': notification.is_read,
        'attachment': None
    }]

    context = {
        'conversations': get_user_conversations(user, organization),
        'messages': messages,
        'selected_conversation_id': notification_id,
        'org_id': org_id,
        'active_tab': 'notifications'
    }
    return render(request, 'conversations.html', context)
def get_user_conversations(user, organization):
    """Fetch conversations for the user with prefetching and annotations."""
    conversations = Conversation.objects.filter(
        Q(user1=user) | Q(user2=user) | Q(groupmember__user=user),
        organization=organization
    ).annotate(
        last_message_time=Max('messages__timestamp')
    ).prefetch_related(
        Prefetch(
            'messages',
            queryset=Message.objects.order_by('-timestamp'),
            to_attr='prefetched_messages'
        )
    ).order_by('-last_message_time')

    conversation_list = []
    for convo in conversations:
        if convo.type == 'private':
            other_user = convo.user2 if convo.user1 == user else convo.user1
            name = other_user.username  # Set the name to the other user's username
        elif convo.type == 'group':
            name = convo.name.strip() if convo.name and convo.name.strip() else "Unnamed Group"  # Use group name or fallback
        else:
            name = "Unknown Conversation"  # Default fallback for unknown types

        # Construct the conversation dictionary
        conversation_list.append({
            'id': convo.id,
            'name': name,  # Ensure name is passed correctly
            'type': convo.type,
            'profile_picture': (
                convo.profile_picture.url if convo.profile_picture
                else static("img/group-default.png" if convo.type == 'group' else "img/default-profile.jpg")
            ),
            'unread_count': convo.messages.filter(is_read=False).exclude(sender=user).count(),
            'last_message_time': timezone.localtime(convo.last_message_time),
        })
    logger.info(f"Constructed Conversation List: {conversation_list}")
    return conversation_list

@login_required
def conversations_list(request):
    conversations = Conversation.objects.filter(
        group_members__user=request.user
    ).distinct()  # Get all conversations (private and group) the user is part of

    return render(request, 'conversations.html', {'conversations': conversations})

@login_required
def create_group_chat(request, org_id):
    if request.method == 'POST':
        name = request.POST.get('name')
        user_ids = request.POST.getlist('users')  # List of user IDs

        # Create a new group conversation
        conversation = Conversation.objects.create(name=name, type='group', organization_id=org_id)

        # Add the current user and selected members to the group
        GroupMember.objects.create(conversation=conversation, user=request.user)
        for user_id in user_ids:
            user = User.objects.get(id=user_id)
            GroupMember.objects.create(conversation=conversation, user=user)

        return redirect('conversation', conversation_id=conversation.id, org_id=org_id)

    # Fetch all users except the current user
    all_users = User.objects.exclude(id=request.user.id)
    return render(request, 'conversations.html', {'users': all_users, 'org_id': org_id})

@login_required
def update_group_info(request, org_id, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id, type='group')

    if request.method == 'POST':
        group_name = request.POST.get('group_name', '').strip()
        group_photo = request.FILES.get('group_photo', None)

        if group_name:
            conversation.name = group_name
        if group_photo:
            conversation.profile_picture = group_photo

        try:
            conversation.save()
            messages.success(request, "Group information updated successfully.")
        except Exception as e:
            messages.error(request, f"Failed to update group information. Error: {str(e)}")

        return redirect('conversation', org_id=org_id, conversation_id=conversation.id)

    return render(request, 'conversations.html', {'conversation': conversation})

@login_required
def ajax_conversation_details(request, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id)
    conversation_key = get_conversation_key(conversation.id)
    messages = Message.objects.filter(conversation=conversation).order_by('-timestamp')[:10]
    decrypted_messages = decrypt_messages_bulk(messages, conversation_key)

    # Decrypt each message
    # Decrypt each message for the AJAX response
    messages_data = [
    {
        'sender': message.sender.username,
        'content': message.get_decrypted_content(),
        'timestamp': message.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    }
    for message in messages
]


    return JsonResponse({'messages': messages_data})

@login_required
def conversations(request, org_id):
    conversations = Conversation.objects.filter(
        Q(user1=user) | Q(user2=user),
            organization=organization  # Filter by organization ID
        ).annotate(
            last_message_time=Max('messages__timestamp')
        ).order_by('-last_message_time')
    return render(request, 'conversations.html', {'conversations': conversations})

@login_required
@require_POST
def send_new_message(request, org_id):
    data = json.loads(request.body)
    receiver_usernames = data.get('receiver_usernames', [])
    content = data.get('content', '')

    # Fetch the organization based on org_id
    organization = get_object_or_404(Organization, id=org_id)

    if receiver_usernames and content:
        if len(receiver_usernames) > 1:  # If more than one user, create a group chat
            # Create a group conversation
            conversation = Conversation.objects.create(
                type='group',
                organization=organization,
                name=f'Group Chat {request.user.username} & others'  # Set a group name
            )

            # Add the current user and all selected users to the group
            GroupMember.objects.create(conversation=conversation, user=request.user)
            for username in receiver_usernames:
                user = User.objects.get(username=username)
                GroupMember.objects.create(conversation=conversation, user=user)

        else:
            # Handle private chat with a single user
            recipient = User.objects.get(username=receiver_usernames[0])
            conversation, created = Conversation.objects.get_or_create(
                type='private',
                user1=request.user,
                user2=recipient,
                organization=organization
            )

        # Create the message
        Message.objects.create(
            sender=request.user,
            content=content,
            conversation=conversation
        )

        return JsonResponse({
            'status': 'Message sent',
            'conversation_id': conversation.id  # Return the conversation ID for redirection
        })

    return JsonResponse({'status': 'Error', 'message': 'Invalid data'}, status=400)

@login_required
@require_POST
def send_message(request, conversation_id, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    conversation = get_object_or_404(Conversation, pk=conversation_id, organization=organization)
    form = MessageForm(request.POST, request.FILES)

    if form.is_valid():
        message = form.save(commit=False)
        message.sender = request.user
        message.conversation = conversation
        message.is_read = False
        message.save()

        # Prepare attachment details
        attachment_url = None
        attachment_type = None
        if message.attachment:
            attachment_url = message.attachment.url
            mime_type, _ = mimetypes.guess_type(message.attachment.name)
            attachment_type = mime_type or 'unknown'

        # WebSocket message data
        message_data = {
            'type': 'chat_message',
            'message_content': message.get_decrypted_content() or '[No Text]',
            'sender': message.sender.username,
            'sender_profile_picture': (
                message.sender.profile_picture.url
                if message.sender.profile_picture else '/static/img/default-profile.jpg'
            ),
            'timestamp': message.timestamp.isoformat(),
            'attachment_url': attachment_url,
            'attachment_type': attachment_type,
        }

        # Send WebSocket message
        async_to_sync(channel_layer.group_send)(
            f'chat_{conversation_id}',
            {
                'type': 'chat_message',
                **message_data,
            }
        )

        return JsonResponse({'status': 'Message sent', **message_data}, status=200)

    return JsonResponse({'status': 'Error', 'message': 'Form data is invalid.'}, status=400)

@login_required
@require_POST
def delete_conversation(request, conversation_id, org_id):
    conversation = get_object_or_404(Conversation.objects.filter(
        Q(user1=request.user) | Q(user2=request.user),
        organization=request.user.organization  # Ensure the conversation is within the organization
    ), id=conversation_id)

    conversation.messages.all().delete()
    conversation.delete()
    return JsonResponse({'status': 'Conversation deleted'})

@login_required
def new_message(request, org_id):
    # Retrieve friends where the current user is either user1 or user2 and the status is 'accepted'
    organization = get_object_or_404(Organization, id=org_id)
    friends = Friend.objects.filter(
        (Q(user1=request.user) | Q(user2=request.user)) & Q(status='accepted')
    ).values_list('user1__username', 'user2__username')


    # Extract the usernames, but exclude the current user's own username
    friends = set(
        friend for pair in friends for friend in pair if friend != request.user.username
    )


    
    return render(request, 'new-message.html', {'friends': friends, 'org_id': org_id})


@login_required
def leave_group(request, org_id, conversation_id):
    user = request.user
    organization = get_object_or_404(Organization, id=org_id)
    conversation = get_object_or_404(Conversation, id=conversation_id, organization=organization)

    # Ensure this is a group conversation
    if conversation.type != 'group':
        messages.error(request, "You can only leave group conversations.")
        return redirect('fetch_messages', org_id=org_id)

    # Check if the user is a member of the group
    group_member = GroupMember.objects.filter(conversation=conversation, user=user).first()
    if not group_member:
        messages.error(request, "You are not a member of this group.")
        return redirect('fetch_messages', org_id=org_id)

    # Remove the user from the group
    group_member.delete()

    # Check if the group has no members left and delete the conversation if necessary
    if not conversation.groupmember.exists():
        conversation.delete()

    messages.success(request, "You have left the group.")
    return redirect('fetch_messages', org_id=org_id)

@login_required
def add_members(request, org_id, conversation_id):
    if request.method == "POST":
        conversation = get_object_or_404(Conversation, id=conversation_id, organization_id=org_id)

        # Get the list of usernames to add
        member_usernames = request.POST.getlist('members')

        # Fetch the current group members
        existing_members = GroupMember.objects.filter(conversation=conversation).values_list('user__username', flat=True)

        # Track already existing members and successfully added members
        already_in_group = []
        added_members = []

        for username in member_usernames:
            if username in existing_members:
                already_in_group.append(username)
            else:
                user = get_object_or_404(User, username=username, organization_id=org_id)
                GroupMember.objects.create(conversation=conversation, user=user)
                added_members.append(username)

        return JsonResponse({
            'status': 'success',
            'added_members': added_members,
            'already_in_group': already_in_group,
        })

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=400)

@login_required
def remove_member(request, org_id, conversation_id, user_id):
    conversation = get_object_or_404(Conversation, id=conversation_id, organization_id=org_id)
    user = get_object_or_404(User, id=user_id)
    if user in conversation.members.all():
        conversation.members.remove(user)
        messages.success(request, f"{user.username} has been removed from the group.")
    return redirect('conversation', org_id=org_id, conversation_id=conversation_id)

@require_POST
@login_required
def send_event_invitation(request, org_id, event_id):
    data = json.loads(request.body)
    invited_user_id = data.get("user_id")
    invited_user = get_object_or_404(User, id=invited_user_id, organization_id=org_id)
    event = get_object_or_404(CalendarEvent, id=event_id, organization_id=org_id)

    # Check if a conversation already exists between sender and invitee
    conversation, created = Conversation.objects.get_or_create(
        organization_id=org_id,
        type='private',
        user1=request.user,
        user2=invited_user
    )

    # Create the invitation
    invitation, created_invitation = EventInvitation.objects.get_or_create(
        event=event,
        invited_user=invited_user
    )

    # Send a notification if the invitation is newly created
    if created_invitation:
        InboxNotification.objects.create(
            user=invited_user,
            message=f"You've been invited to the event '{event.title}'",
            event_invitation=invitation
        )

    return JsonResponse({'status': 'success', 'invitation_id': invitation.id})
@login_required
def respond_to_event_invitation(request, org_id, invitation_id):
    data = json.loads(request.body)
    response = data.get("response")

    invitation = get_object_or_404(EventInvitation, id=invitation_id, invited_user=request.user)

    if response not in ["accepted", "declined"]:
        return JsonResponse({'status': 'error', 'message': 'Invalid response'}, status=400)

    invitation.status = response
    invitation.save()

    if response == "accepted":
        # Add user to the event or take other actions
        CalendarEvent.objects.create(
            title=invitation.event.title,
            description=invitation.event.description,
            start_date=invitation.event.start_date,
            end_date=invitation.event.end_date,
            color=invitation.event.color,
            all_day=invitation.event.all_day,
            user=invitation.invited_user,
            organization=invitation.event.organization,
            is_shared=True
        )

    return JsonResponse({'status': 'success', 'message': f'Invitation {response}'})

@login_required
@require_POST
def send_invitation(request):
    data = json.loads(request.body)
    experiment_id = data['experiment_id']
    username = data['username']
    role = data['role']

    user = get_object_or_404(User, username=username)
    experiment = get_object_or_404(Experiment, id=experiment_id)

    conversation, created = Conversation.objects.get_or_create(
        type='private',
        user1=request.user,
        user2=user,
        defaults={'name': user.username}
    )

    invitation = Invitation.objects.create(
        sender=request.user,
        receiver=user,
        experiment=experiment,
        role=role,
        status='pending'
    )

    message_content = f"You have been invited to join the experiment '{experiment.name}' as a {role}. Do you accept?"
    Message.objects.create(
        sender=request.user,
        content=message_content,
        conversation=conversation,
        invitation_id=invitation.id  # Ensure you have a field to link invitations to messages if needed
    )

    return JsonResponse({'status': 'Invitation sent successfully', 'conversation_id': conversation.id})


@login_required
@require_POST
def remove_collaborator(request):
    data = request.json()
    experiment_id = data['experiment_id']
    user_id = data['user_id']

    Collaborator.objects.filter(experiment_id=experiment_id, user_id=user_id).delete()
    return JsonResponse({'status': 'Collaborator removed'})

@login_required
@require_POST
def update_collaborator_role(request):
    data = request.json()
    experiment_id = data['experiment_id']
    user_id = data['user_id']
    role = data['role']

    Collaborator.objects.filter(experiment_id=experiment_id, user_id=user_id).update(role=role)
    return JsonResponse({'status': 'Collaborator role updated'})

@login_required
def send_experiment_message_page(request, org_id, experiment_id):
    # Ensure the experiment and members belong to the same organization
    experiment = get_object_or_404(Experiment, id=experiment_id, organization__id=org_id)
    
    # Start with the experiment owner as a member
    members = set([experiment.owner])
    
    # Include all collaborators (which should now include investigators as well)
    collaborators = Collaborator.objects.filter(experiment=experiment, user__organization=request.user.organization)
    
    for collaborator in collaborators:
        members.add(collaborator.user)
    
    # Exclude the current user (the sender) from the members
    members = [member for member in members if member != request.user]
    
    return render(request, 'send_experiment_message_page.html', {
        'experiment': experiment,
        'experiment_members': members,  # Pass all members except the sender to the template
        'org_id': org_id
    })

@login_required
def send_experiment_message(request, org_id, experiment_id):
    # Ensure the experiment belongs to the same organization
    experiment = get_object_or_404(Experiment, id=experiment_id, organization__id=org_id)

    if request.method == 'POST':
        message_content = request.POST.get('message')
        recipient_ids = request.POST.getlist('recipients')

        if not message_content:
            django_messages.error(request, "Message cannot be empty.")
            return redirect('send_experiment_message_page', org_id=org_id, experiment_id=experiment.id)

        if not recipient_ids:
            django_messages.error(request, "Please select at least one recipient.")
            return redirect('send_experiment_message_page', org_id=org_id, experiment_id=experiment.id)

        # Fetch selected recipients within the same organization
        recipients = User.objects.filter(id__in=recipient_ids, organization_id=org_id)

        # Send message to each selected user
        for recipient in recipients:
            # Check if a conversation already exists between the sender and the recipient
            conversation = Conversation.objects.filter(
                (Q(user1=request.user, user2=recipient) | Q(user1=recipient, user2=request.user)),
                type='private'
            ).first()

            # If no conversation exists, create a new one
            if not conversation:
                conversation = Conversation.objects.create(
                    user1=request.user,
                    user2=recipient,
                    type='private',
                    organization_id=org_id  # Link the conversation to the organization
                )

            # Create the message
            Message.objects.create(
                sender=request.user,
                content=message_content,
                conversation=conversation
            )

        django_messages.success(request, "Message sent to selected users.")
        return redirect('experiment_home', org_id=org_id, experiment_id=experiment.id)

    return redirect('experiment_home', org_id=org_id, experiment_id=experiment.id)

@login_required
def send_friend_message(request, org_id, friend_id):
    # Ensure the friend exists within the same organization
    friend = get_object_or_404(User, id=friend_id, organization__id=org_id)

    if request.method == 'POST':
        message_content = request.POST.get('message')

        if not message_content:
            django_messages.error(request, "Message cannot be empty.")
            return redirect('friend_info', org_id=org_id, friend_id=friend.id)

        # Check if a conversation already exists between the sender and the recipient
        conversation = Conversation.objects.filter(
            (Q(user1=request.user, user2=friend) | Q(user1=friend, user2=request.user)),
            type='private'
        ).first()

        # If no conversation exists, create a new one
        if not conversation:
            conversation = Conversation.objects.create(
                user1=request.user,
                user2=friend,
                type='private',
                organization_id=org_id  # Link the conversation to the organization
            )

        # Create the message
        Message.objects.create(
            sender=request.user,
            content=message_content,
            conversation=conversation
        )

        django_messages.success(request, f"Message sent to {friend.username}.")
        return redirect('friend_info', org_id=org_id, friend_id=friend.id)

    return redirect('friend_info', org_id=org_id, friend_id=friend.id)

@login_required
def start_conversation(request, org_id, friend_id):
    # Ensure the friend exists within the same organization
    friend = get_object_or_404(User, id=friend_id, organization__id=org_id)

    # Check if a conversation already exists between the sender and the recipient
    conversation = Conversation.objects.filter(
        (Q(user1=request.user, user2=friend) | Q(user1=friend, user2=request.user)),
        type='private'
    ).first()

    # If no conversation exists, create a new one
    if not conversation:
        conversation = Conversation.objects.create(
            user1=request.user,
            user2=friend,
            type='private',
            organization_id=org_id  # Link the conversation to the organization
        )

    # Redirect the user to the conversation page
    return redirect('conversation', org_id=org_id, conversation_id=conversation.id)

@login_required
def inbox_view(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    user = request.user
    notification_id = request.GET.get('notification_id')

    # Fetch experiment-related and admin notifications
    experiment_notifications = InboxNotification.objects.filter(user=user).order_by('-timestamp')

    # Fetch the selected notification if it exists
    selected_notification = None
    if notification_id:
        selected_notification = InboxNotification.objects.filter(user=user, id=notification_id).first()
        if selected_notification and not selected_notification.is_read:
            selected_notification.is_read = True
            selected_notification.save()

    # Update sender name to "Organization" for admin notifications
    for notification in experiment_notifications:
        if notification.from_admin:
            notification.sender_name = "Organization"
        else:
            notification.sender_name = notification.user.username

    # Pass org_id to the template
    return render(request, 'inbox.html', {
        'experiment_notifications': experiment_notifications,
        'selected_notification': selected_notification,
        'selected_notification_id': notification_id,
        'org_id': org_id  # Ensure org_id is passed here
    })

@login_required
def notification_view(request, org_id, notification_id):
    user = request.user
    organization = get_object_or_404(Organization, id=org_id)
    notification = get_object_or_404(InboxNotification, id=notification_id, user=user)

    # Mark notification as read if it’s not already read
    if not notification.is_read:
        notification.is_read = True
        notification.save()

    # Check if notification is related to an event invitation
    invitation = None
    if hasattr(notification, 'event_invitation'):
        invitation = notification.event_invitation

    # Set up context to render notification in conversation format or invitation format
    context = {
        'notification': notification,
        'org_id': org_id,
        'invitation': invitation  # Add the invitation if it exists
    }

    return render(request, 'notification_detail.html', context)

@login_required
def get_unread_messages_count(request, org_id=None):
    user = request.user

    unread_message_count = Message.objects.filter(
        conversation__in=Conversation.objects.filter(
            Q(user1=user) | Q(user2=user) | Q(groupmember__user=user)
        ),
        is_read=False
    ).exclude(sender=user).count()

    unread_notification_count = InboxNotification.objects.filter(user=user, is_read=False).count()
    total_unread_count = unread_message_count + unread_notification_count

    return JsonResponse({'unread_count': total_unread_count})

def get_decrypted_message_preview(message):
    cache_key = f"message_preview_{message.id}"
    preview = cache.get(cache_key)
    if not preview:
        preview = message.get_decrypted_content()
        cache.set(cache_key, preview, timeout=300)  # Cache for 5 minutes
    return preview

@login_required
@require_POST
def mark_notification_as_read(request, org_id, notification_id):
    notification = get_object_or_404(InboxNotification, id=notification_id, user=request.user)
    notification.is_read = True
    notification.save()
    return redirect('inbox', org_id=org_id)  # Redirect back to the inbox page
@login_required
def get_messages(request, conversation_id):
    page = int(request.GET.get('page', 1))  # Get the requested page number
    messages = Message.objects.filter(conversation_id=conversation_id).order_by('-timestamp')

    paginator = Paginator(messages, 10)  # 10 messages per page
    messages_page = paginator.get_page(page)

    message_list = [
        {
            'id': msg.id,
            'content': msg.get_decrypted_content(),  # Ensure messages are decrypted
            'timestamp': msg.timestamp.isoformat(),
            'is_sender': msg.sender == request.user,
            'attachment': msg.attachment.url if msg.attachment else None,
            'is_image': msg.attachment.name.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')) if msg.attachment else False,
            'is_pdf': msg.attachment.name.lower().endswith('.pdf') if msg.attachment else False,
        } for msg in messages_page
    ]

    return JsonResponse({
        'messages': message_list,
        'has_more': messages_page.has_next(),
        'current_page': messages_page.number
    })

@login_required
def get_paginated_messages(request, org_id, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id, organization_id=org_id)
    messages_query = Message.objects.filter(conversation=conversation).order_by('-timestamp')
    messages_query = Message.objects.filter(conversation=conversation).select_related('sender').prefetch_related('attachment').order_by('-timestamp')
    
    paginator = Paginator(messages_query, 10)  # 10 messages per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    message_list = [
        {
            'content': msg.get_decrypted_content(),
            'timestamp': msg.timestamp.isoformat(),
            'is_sender': msg.sender == request.user,
            'attachment': msg.attachment.url if msg.attachment else None
        }
        for msg in page_obj
    ]

    return JsonResponse({
        'messages': message_list,
        'has_more': page_obj.has_next()
    })
