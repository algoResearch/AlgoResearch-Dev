from django.contrib import messages as django_messages
from django.core import serializers
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q, F, Avg, Max, Min, Count
from django.utils import timezone
from .models import (Conversation, Message, User, GroupMember, Experiment, RFIDAssignment, WeightMeasurement, Collaborator, CalendarEvent, Comment, Friend, Cage, Animal, Sample, Dose, Observation, Comment)
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
from .forms import ProfilePictureForm
from .forms import UpdateProfileForm, OverviewForm, ObservationForm, SampleForm, DoseForm
from django.views.decorators.http import require_http_methods
from django.utils.dateparse import parse_datetime
import csv
from .models import Invitation

from datetime import date
def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
        else:
            print(form.errors)  # This will print form errors to the console
    else:
        form = CustomUserCreationForm()
    return render(request, 'register.html', {'form': form})

@login_required
def home(request):
    return render(request, 'home.html')


@login_required
def home_view(request):
    return render(request, 'home.html')

@login_required
def profile(request):
    if request.method == 'POST':
        if 'profile_picture' in request.FILES:
            profile_form = ProfilePictureForm(request.POST, request.FILES, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                django_messages.success(request, 'Profile picture updated successfully')
            else:
                django_messages.error(request, 'Failed to update profile picture.')

        elif 'first_name' in request.POST:
            update_form = UpdateProfileForm(request.POST, instance=request.user)
            if update_form.is_valid():
                update_form.save()
                django_messages.success(request, 'Profile updated successfully')
            else:
                django_messages.error(request, 'Failed to update profile.')

        return redirect('profile')
    else:
        update_form = UpdateProfileForm(instance=request.user)
        profile_form = ProfilePictureForm(instance=request.user)

    return render(request, 'profile.html', {
        'form': update_form,
        'profile_form': profile_form,
    })


def profile_view(request):
    if request.method == 'POST':
        profile_form = UpdateProfileForm(request.POST, request.FILES, instance=request.user)
        if profile_form.is_valid():
            profile_form.save()
            return redirect('profile')  # Redirect to the profile page after saving
    else:
        profile_form = UpdateProfileForm(instance=request.user)

    return render(request, 'profile.html', {
        'profile_form': profile_form,
    })

@login_required
def update_profile_picture(request):
    if request.method == 'POST':
        profile_form = ProfilePictureForm(request.POST, request.FILES, instance=request.user)
        if profile_form.is_valid():
            profile_form.save()
            messages.success(request, 'Profile picture updated successfully')
            return redirect('profile')
        else:
            messages.error(request, 'Failed to update profile picture.')
    else:
        profile_form = ProfilePictureForm(instance=request.user)
    return render(request, 'profile.html', {
        'profile_form': profile_form,
    })

@login_required
def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('home')  # Redirect to a home page or another page after login
        else:
            messages.error(request, 'Invalid username or password')
    return render(request, 'dashboard/login.html')  # Correct template path
@login_required
@require_POST
def add_friend(request):
    data = request.json()
    friend_username = data['friend_username']

    friend = get_object_or_404(User, username=friend_username)

    Friend.objects.create(user1=request.user, friend_id=friend.id, status='pending')
    
    return JsonResponse({'status': 'Friend request sent'})

@login_required
@require_POST
def remove_friend(request):
    data = request.json()
    friend_username = data['friend_username']

    friend = get_object_or_404(User, username=friend_username)

    Friend.objects.filter(Q(user1=request.user, friend_id=friend.id) | Q(user1=friend, friend_id=request.user)).delete()
    
    return JsonResponse({'status': 'Friend removed successfully'})

@login_required
def pending_requests(request):
    pending_requests = Friend.objects.filter(friend_id=request.user.id, status='pending').select_related('user')
    return render(request, 'pending_requests.html', {'pending_requests': pending_requests})

@login_required
@require_POST
def respond_friend_request(request):
    data = request.json()
    friend_id = data.get('friend_id')
    action = data.get('action')

    if action == 'accept':
        Friend.objects.filter(user1=friend_id, friend_id=request.user.id).update(status='accepted')
    elif action == 'decline':
        Friend.objects.filter(user1=friend_id, friend_id=request.user.id).delete()

    return JsonResponse({'status': 'success', 'message': f'Friend request {action}ed'})

@login_required
def friend_info(request, friend_id):
    user = get_object_or_404(User, id=friend_id)
    conversation = Conversation.objects.filter(Q(user1=request.user, user2=user) | Q(user1=user, user2=request.user)).first()

    return JsonResponse({'status': 'success', 'user': {
        'id': user.id,
        'username': user.username,
        'organization': user.organization,
        'title': user.title,
        'location': user.location,
        'conversation_id': conversation.id if conversation else None
    }})
@login_required
def dashboard(request):
    user = request.user
    conversations = Conversation.objects.filter(
        Q(user1=user) | Q(user2=user) | Q(groupmember__user=user)
    ).distinct()

    # Count the number of conversations with unread messages
    total_unread_conversations = conversations.filter(
        Q(messages__is_read=False)
    ).exclude(messages__sender=user).values('id').distinct().count()

    upcoming_events_count = CalendarEvent.objects.filter(user=user, start_date__gte=timezone.now()).count()
    active_experiments_count = Experiment.objects.filter(owner=user, ended=False).count()

    context = {
        'upcoming_events_count': upcoming_events_count,
        'total_unread_conversations': total_unread_conversations,
        'active_experiments_count': active_experiments_count,
    }

    return render(request, 'dashboard.html', context)
@login_required
@require_POST
def add_collaborator(request):
    data = json.loads(request.body)
    experiment_id = data['experiment_id']
    username = data['username']
    role = data['role']

    user = get_object_or_404(User, username=username)
    experiment = get_object_or_404(Experiment, id=experiment_id)

    # Create or get the conversation between the current user and the invited user
    conversation, created = Conversation.objects.get_or_create(
        type='private',
        user1=request.user,
        user2=user,
        defaults={'name': f"Invitation to {experiment.name}"}
    )

    # Create the invitation
    invitation = Invitation.objects.create(
        sender=request.user,
        receiver=user,
        experiment=experiment,
        role=role,
        status='pending'
    )

    # Send the invitation as a message
    message_content = f"You have been invited to join the experiment '{invitation.experiment.name}' as a {invitation.role}. Do you accept?"
    Message.objects.create(
        sender=request.user,
        content=message_content,
        conversation=conversation,
        invitation_id=invitation.id
    )

    # Automatically add the collaborator's calendar events if the experiment has a weigh-in schedule
    if experiment.weigh_in_interval and experiment.duration:
        current_date = timezone.now().date()
        while current_date < timezone.now().date() + timezone.timedelta(days=experiment.duration):
            CalendarEvent.objects.create(
                user=user,
                title=f"Weigh-In for {experiment.name} (Collaborator)",
                start_date=current_date,
                end_date=current_date,
                experiment=experiment,
                color='red'  # Assign the color red for collaborator events
            )
            current_date += timezone.timedelta(days=experiment.weigh_in_interval)

    return JsonResponse({'status': 'Invitation sent successfully'})

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
@require_POST
def respond_invitation(request):
    data = json.loads(request.body)
    invitation_id = data.get('invitation_id')
    action = data.get('action')

    if not invitation_id:
        return JsonResponse({'status': 'error', 'message': 'Invitation ID is missing'}, status=400)

    try:
        invitation = Invitation.objects.get(id=invitation_id)
    except Invitation.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Invalid Invitation ID'}, status=404)

    if invitation.status != 'pending':
        return JsonResponse({'status': 'error', 'message': f'Invitation already {invitation.status}'}, status=400)

    if action == 'accept':
        # Add the user as a collaborator
        Collaborator.objects.create(
            experiment=invitation.experiment,
            user=invitation.receiver,
            role=invitation.role
        )
        invitation.status = 'accepted'
        message = f"You have accepted the invitation to {invitation.experiment.name}. You can find it in your Experiments page."
    elif action == 'decline':
        invitation.status = 'declined'
        message = f"You have declined the invitation to {invitation.experiment.name}."

    invitation.save()

    # If you want to link to a conversation, ensure the conversation logic is handled correctly here.
    conversation = Conversation.objects.get_or_create(
        type='private',
        user1=invitation.sender,
        user2=invitation.receiver,
        defaults={'name': f"Conversation about {invitation.experiment.name}"}
    )[0]

    Message.objects.create(
        sender=request.user,
        content=message,
        conversation=conversation
    )

    return JsonResponse({'status': 'success', 'message': message})

@login_required
@require_POST
def remove_collaborator(request):
    data = request.json()
    experiment_id = data['experiment_id']
    user_id = data['user_id']

    Collaborator.objects.filter(experiment_id=experiment_id, user_id=user_id).delete()
    return JsonResponse({'status': 'Collaborator removed'})


@login_required
def user_home(request):
    user = request.user
    experiments = Experiment.objects.filter(owner=user, ended=False)
    experiment_data = []

    for experiment in experiments:
        last_weigh_in = WeightMeasurement.objects.filter(experiment=experiment).order_by('-timestamp').first()
        last_weigh_in_date = last_weigh_in.timestamp if last_weigh_in else experiment.created_date
        next_weigh_in_date = last_weigh_in_date + timezone.timedelta(days=experiment.weigh_in_interval)
        days_until_next_weigh_in = (next_weigh_in_date - timezone.now()).days
        healthy_count = RFIDAssignment.objects.filter(experiment=experiment, removed=False).count()
        removed_count = RFIDAssignment.objects.filter(experiment=experiment, removed=True).count()

        experiment_data.append({
            'id': experiment.id,
            'name': experiment.name,
            'number_of_animals': experiment.number_of_animals,
            'number_of_groups': experiment.number_of_groups,
            'created_date': last_weigh_in_date,
            'removed_animals': removed_count,
            'available_animals': healthy_count,
            'days_until_next_weigh_in': days_until_next_weigh_in
        })

    return render(request, 'userhome.html', {'user': user, 'experiments': experiment_data})


@login_required
@require_POST
def create_group(request):
    data = request.json()
    group_name = data['group_name']
    user_ids = data['user_ids']

    conversation = Conversation.objects.create(type='group', name=group_name)

    for user_id in user_ids:
        GroupMember.objects.create(conversation=conversation, user_id=user_id)

    return JsonResponse({'status': 'Success', 'message': 'Group created successfully', 'conversation_id': conversation.id})
