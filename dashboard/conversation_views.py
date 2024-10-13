from django.contrib import messages as django_messages
from django.core import serializers
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q, F, Avg, Max, Min, Count
from django.utils import timezone
from .models import (Conversation, Message, User, Organization, InboxNotification, GroupMember, Experiment, RFIDAssignment, WeightMeasurement, Collaborator, CalendarEvent, Comment, Friend, Cage, Animal, Sample, Dose, Observation, Comment)
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, authenticate
import pandas as pd
from django.views.decorators.csrf import csrf_exempt
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import random
from django.contrib.auth import logout
from django.db import IntegrityError
from .forms import CustomUserCreationForm, UpdateProfileForm, ExperimentForm
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

import logging
# Assuming you have access to `request.user` and the `last_message_time` is in UTC.

# Set up logging
logger = logging.getLogger('dashboard')


@login_required
def messages(request, org_id):
    user = request.user
    organization = get_object_or_404(Organization, id=org_id)

    # Fetch all conversations for the user within the organization and order by the most recent message timestamp
    conversations = Conversation.objects.filter(
        Q(user1=user) | Q(user2=user),
        organization=organization
    ).annotate(
        last_message_time=Max('messages__timestamp')
    ).order_by('-last_message_time')

    conversation_list = []
    total_unread_count = 0  # Initialize total unread count

    for convo in conversations:
        other_user = convo.user2 if convo.user1 == user else convo.user1
        unread_count = convo.messages.filter(is_read=False).exclude(sender=user).count()
        total_unread_count += unread_count

        # Prepare conversation list
        conversation_list.append({
            'id': convo.id,
            'username': other_user.username,
            'profile_picture': other_user.profile_picture.url if other_user.profile_picture else '{% static "img/default-profile.jpg" %}',
            'unread_count': unread_count,
            'last_message_time': timezone.localtime(convo.last_message_time),
        })

    return render(request, 'conversations.html', {
        'conversations': conversation_list,
        'unread_conversations_count': total_unread_count,
        'organization': organization,  # Ensure org_id is passed here
        'org_id': org_id  # Ensure org_id is passed
    })

@login_required
def conversation_view(request, conversation_id, org_id):
    user = request.user
    organization = get_object_or_404(Organization, id=org_id)
    conversation = get_object_or_404(Conversation, id=conversation_id, organization=organization)
    messages = Message.objects.filter(conversation=conversation).order_by('timestamp')
    # Decrypt the message content before passing it to the template
    decrypted_messages = [
        {
            'sender': msg.sender,
            'content': msg.get_decrypted_content(),  # Decrypted content
            'timestamp': msg.timestamp,
            'is_read': msg.is_read,
            'attachment': msg.attachment
        }
        for msg in messages
    ]
    # Do not mark messages as read here, WebSocket will handle that

    return render(request, 'conversation_detail.html', {
        'conversation': conversation,
        'messages': decrypted_messages,
        'org_id': org_id,
        'selected_conversation_id': conversation_id
    })


@login_required
def conversation(request, conversation_id, org_id):
    user = request.user
    organization = get_object_or_404(Organization, id=org_id)

    # Fetch all conversations involving the current user within the organization
    all_conversations = Conversation.objects.filter(
        Q(user1=user) | Q(user2=user) | Q(groupmember__user=user),
        organization=organization
    ).annotate(
        last_message_time=Max('messages__timestamp')
    ).order_by('-last_message_time')

    conversation_list = []
    for convo in all_conversations:
        unread_count = convo.messages.exclude(sender=user).filter(is_read=False).count()

        if convo.type == 'private':
            other_user = convo.user2 if convo.user1 == user else convo.user1
            profile_picture = other_user.profile_picture.url if other_user.profile_picture else static("img/default-profile.jpg")
        else:
            profile_picture = static("img/group.png")

        conversation_list.append({
            'id': convo.id,
            'type': convo.type,
            'username': other_user.username if convo.type == 'private' else convo.name,
            'profile_picture': profile_picture,
            'unread_count': unread_count,
            'last_message_time': convo.last_message_time
        })

    # Fetch the specific conversation within the organization
    conversation = get_object_or_404(Conversation, id=conversation_id, organization=organization)
    messages = Message.objects.filter(conversation=conversation).order_by('timestamp')

    # Decrypt the message content before passing it to the template
    decrypted_messages = []
    for msg in messages:
        decrypted_content = msg.get_decrypted_content()  # Decrypt the message content
        decrypted_messages.append({
            'sender': msg.sender,
            'content': decrypted_content,
            'timestamp': msg.timestamp,
            'is_read': msg.is_read,
            'attachment': msg.attachment
        })

    # Mark messages as read when viewed
    messages.update(is_read=True)

    context = {
        'conversations': conversation_list,  # All conversations for the sidebar
        'conversation': conversation,        # Specific conversation details
        'messages': decrypted_messages,      # Decrypted messages of the specific conversation
        'selected_conversation_id': conversation_id,  # Highlight the active conversation
        'org_id': org_id,                    # Pass org_id to the context
    }
    return render(request, 'conversations.html', context)


@login_required
def ajax_conversation_details(request, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id)
    messages = Message.objects.filter(conversation=conversation).order_by('timestamp')

    # Decrypt each message
    # Decrypt each message for the AJAX response
    messages_data = [{
        'sender': message.sender.username,
        'content': message.get_decrypted_content(),  # Decrypted message content
        'timestamp': message.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    } for message in messages]

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
    if request.method == 'POST':
        data = json.loads(request.body)
        receiver_usernames = data.get('receiver_usernames', [])
        content = data.get('content', '')

        # Fetch the organization based on org_id
        organization = get_object_or_404(Organization, id=org_id)

        if receiver_usernames and content:
            # Assume only one recipient for simplicity (you can modify this to support multiple recipients)
            recipient = User.objects.get(username=receiver_usernames[0])

            # Create or get the conversation
            conversation, created = Conversation.objects.get_or_create(
                type='private',
                user1=request.user,
                user2=recipient,
                organization=organization  # Ensure the conversation is tied to the specified organization
            )

            # Create the message
            message = Message.objects.create(
                sender=request.user,
                content=content,
                conversation=conversation
            )

            return JsonResponse({
                'status': 'Message sent',
                'conversation_id': conversation.id  # Ensure the conversation ID is returned for redirection
            })

        return JsonResponse({'status': 'Error', 'message': 'Invalid data'})
    
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

        # Just return the message response. No broadcasting here, WebSocket will handle it.
        decrypted_content = message.get_decrypted_content()

        sender_profile_picture = (
            message.sender.profile_picture.url
            if message.sender.profile_picture else '/static/img/default-profile.jpg'
        )

        return JsonResponse({
            'status': 'Message sent',
            'message_content': decrypted_content,  # Use decrypted message content
            'sender_id': message.sender.id,
            'sender_profile_picture': sender_profile_picture,
            'attachment_url': message.attachment.url if message.attachment else None
        }, status=200)
    else:
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
    members = set([experiment.owner])
    collaborators = Collaborator.objects.filter(experiment=experiment, user__organization=request.user.organization)

    for collaborator in collaborators:
        members.add(collaborator.user)

    # Exclude the current user (the sender)
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
def get_unread_messages_count(request, org_id=None):
    user = request.user

    # Get unread message count
    unread_message_count = Message.objects.filter(
        conversation__in=Conversation.objects.filter(
            Q(user1=user) | Q(user2=user) | Q(groupmember__user=user)
        ),
        is_read=False
    ).exclude(sender=user).count()

    # Get unread notification count
    unread_notification_count = InboxNotification.objects.filter(user=user, is_read=False).count()

    # Combine both counts
    total_unread_count = unread_message_count + unread_notification_count

    return JsonResponse({'unread_count': total_unread_count})

@login_required
@require_POST
def mark_notification_as_read(request, org_id, notification_id):
    notification = get_object_or_404(InboxNotification, id=notification_id, user=request.user)
    notification.is_read = True
    notification.save()
    return redirect('inbox', org_id=org_id)  # Redirect back to the inbox page