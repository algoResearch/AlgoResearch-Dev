from django.contrib import messages as django_messages
from django.core import serializers
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q, F, Avg, Max, Min, Count
from django.utils import timezone
from .models import (Conversation, Message, User, InboxNotification, GroupMember, Experiment, RFIDAssignment, WeightMeasurement, Collaborator, CalendarEvent, Comment, Friend, Cage, Animal, Sample, Dose, Observation, Comment)
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, authenticate
import pandas as pd
from django.views.decorators.csrf import csrf_exempt
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
@login_required
def messages(request):
    user = request.user

    # Fetch all conversations for the user
    conversations = Conversation.objects.filter(
        Q(user1=user) | Q(user2=user) | Q(groupmember__user=user)
    ).distinct()

    conversation_list = []
    selected_conversation_id = None  # Initialize selected_conversation_id

    for convo in conversations:
        if convo.type == 'private':
            other_user = convo.user2 if convo.user1 == user else convo.user1
            unread_count = Message.objects.filter(conversation=convo, is_read=False).exclude(sender=user).values('sender').distinct().count()
            conversation_list.append({
                'id': convo.id,
                'type': convo.type,
                'username': other_user.username,
                'profile_picture': other_user.profile_picture.url if other_user.profile_picture else '{% static "img/default-profile.jpg" %}',
                'unread_count': unread_count
            })
        else:
            unread_count = Message.objects.filter(conversation=convo, is_read=False).exclude(sender=user).values('sender').distinct().count()
            conversation_list.append({
                'id': convo.id,
                'type': convo.type,
                'name': convo.name or 'Unnamed Group',
                'profile_picture': '{% static "img/group.png" %}',
                'unread_count': unread_count
            })

    # Get the selected conversation ID from the request (if available)
    if 'conversation_id' in request.GET:
        selected_conversation_id = request.GET.get('conversation_id')

    # Fetch the selected conversation object
    selected_conversation = None
    if selected_conversation_id:
        try:
            selected_conversation = Conversation.objects.get(pk=selected_conversation_id)
        except Conversation.DoesNotExist:
            selected_conversation_id = None

    return render(request, 'conversations.html', {
        'conversations': conversation_list,
        'selected_conversation_id': selected_conversation_id,  # Pass to template
      
    })

@login_required
def conversation_view(request, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id)
    messages = Message.objects.filter(conversation=conversation).order_by('timestamp')

    # Mark all messages as read when the conversation is viewed
    messages.filter(read=False).exclude(sender=request.user).update(read=True)

    context = {
        'conversation': conversation,
        'messages': messages,
        'selected_conversation_id': conversation_id,
    }
    return render(request, 'conversations.html', context)

@login_required
def conversation(request, conversation_id):
    user = request.user

    # Fetch all conversations involving the current user
    all_conversations = Conversation.objects.filter(
        Q(user1=user) | Q(user2=user) | Q(groupmember__user=user)
    ).distinct()

    # Now, iterate and manually count unread messages not sent by 'user'
    conversation_list = []
    for convo in all_conversations:
        # Filtering messages within the loop, not ideal but works for clarity
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
            'unread_count': unread_count
        })

    # Fetch the specific conversation details
    conversation = get_object_or_404(Conversation, id=conversation_id)
    messages = Message.objects.filter(conversation=conversation).order_by('timestamp')
    messages.update(is_read=True)  # Mark messages as read when viewed

    context = {
        'conversations': conversation_list,  # All conversations for the sidebar
        'conversation': conversation,         # Specific conversation details
        'messages': messages,                 # Messages of the specific conversation
        'selected_conversation_id': conversation_id,  # To highlight the active conversation
    }
    return render(request, 'conversations.html', context)

@login_required
def ajax_conversation_details(request, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id)
    messages = Message.objects.filter(conversation=conversation).order_by('-timestamp')
    messages_data = [{
        'sender': message.sender.username,
        'content': message.content,
        'timestamp': message.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    } for message in messages]
    return JsonResponse({'messages': messages_data})


@login_required
def conversations(request):
    conversations = Conversation.objects.filter(Q(user1=user) | Q(user2=user) | Q(groupmember__user=user)).distinct()
    return render(request, 'conversations.html', {'conversations': conversations})


@login_required
@require_POST
def send_new_message(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        receiver_usernames = data.get('receiver_usernames', [])
        content = data.get('content', '')

        if receiver_usernames and content:
            # Assume only one recipient for simplicity, adjust if supporting multiple recipients
            recipient = User.objects.get(username=receiver_usernames[0])

            # Create or get the conversation
            conversation, created = Conversation.objects.get_or_create(
                type='private',
                user1=request.user,
                user2=recipient
            )

            # Create the message
            message = Message.objects.create(
                sender=request.user,
                content=content,
                conversation=conversation
            )

            return JsonResponse({
                'status': 'Message sent',
                'conversation_id': conversation.id  # Ensure this is returned
            })

        return JsonResponse({'status': 'Error', 'message': 'Invalid data'})


@login_required
@require_POST
def send_message(request, conversation_id):
    form = MessageForm(request.POST, request.FILES)
    if form.is_valid():
        message = form.save(commit=False)
        message.sender = request.user
        message.conversation = get_object_or_404(Conversation, pk=conversation_id)
        message.save()
        
        # Return a JSON response if the request is via AJAX
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'Message sent',
                'message_content': message.content,  # send back the message content to be displayed
                'sender_id': message.sender.id,
                'attachment_url': message.attachment.url if message.attachment else None
            }, status=200)

        # Redirect for non-AJAX requests (standard form submission)
        return redirect('conversation', conversation_id=conversation_id)
    else:
        # Return form errors as JSON if the request is via AJAX
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'Error', 'errors': form.errors}, status=400)

        # For non-AJAX requests, re-render the page with form errors
        return render(request, 'conversations.html', {
            'form': form,
            'selected_conversation_id': conversation_id,  # Ensure context includes conversation_id for correct template rendering
            'conversation': get_object_or_404(Conversation, pk=conversation_id),  # Pass conversation object to template
            'messages': Message.objects.filter(conversation_id=conversation_id)  # Include existing messages for rendering
        })

@login_required
@require_POST
def delete_conversation(request, conversation_id):
    conversation = get_object_or_404(Conversation.objects.filter(
        Q(user1=request.user) | Q(user2=request.user),
        id=conversation_id
    ))
    conversation.messages.all().delete()
    conversation.delete()
    return JsonResponse({'status': 'Conversation deleted'})

@login_required
def new_message(request):
    # Retrieve friends where the current user is either user1 or user2 and the status is 'accepted'
    friends = Friend.objects.filter(
        (Q(user1=request.user) | Q(user2=request.user)) & Q(status='accepted')
    ).values_list('user1__username', 'user2__username')

    # Extract the usernames, but exclude the current user's own username
    friends = set(
        friend for pair in friends for friend in pair if friend != request.user.username
    )

    return render(request, 'new-message.html', {'friends': friends})

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
def inbox_view(request):
    user = request.user

    # Fetch experiment-related notifications for the current user
    experiment_notifications = InboxNotification.objects.filter(user=user).order_by('-timestamp')

    # Fetch all conversations involving the current user
    conversations = Conversation.objects.filter(
        Q(user1=user) | Q(user2=user) 
    ).distinct()

    # Count unread messages in each conversation
    inbox_items = []
    for convo in conversations:
        unread_count = Message.objects.filter(conversation=convo, is_read=False).exclude(sender=user).count()

        if convo.type == 'private':
            other_user = convo.user2 if convo.user1 == user else convo.user1
            inbox_items.append({
                'id': convo.id,
                'type': convo.type,
                'username': other_user.username,
                'profile_picture': other_user.profile_picture.url if other_user.profile_picture else static("img/default-profile.jpg"),
                'unread_count': unread_count
            })
        else:
            inbox_items.append({
                'id': convo.id,
                'type': convo.type,
                'name': convo.name or 'Unnamed Group',
                'profile_picture': static("img/group.png"),
                'unread_count': unread_count
            })

    return render(request, 'inbox.html', {
        'inbox_items': inbox_items,  # Pass the inbox data to the template
        'experiment_notifications': experiment_notifications,  # Pass experiment notifications
    })

@login_required
def get_unread_messages_count(request):
    user = request.user
    # Filter messages that are unread and not sent by the current user
    unread_count = Message.objects.filter(
        is_read=False
    ).exclude(sender=user).count()
    
    return JsonResponse({'unread_count': unread_count})
