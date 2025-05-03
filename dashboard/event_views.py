from django.contrib import messages as django_messages
from django.core import serializers
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q, F, Avg, Max, Min, Count
import logging
from django.utils import timezone
from django.utils.timezone import now, localtime
from dateutil.rrule import rrule, WEEKLY, MONTHLY, DAILY
from dateutil.rrule import rrule, DAILY, WEEKLY
from datetime import timezone as dt_timezone  
from datetime import timedelta
from datetime import timezone as datetime_timezone
from .models import (Conversation, EventCompletion, Message, User, Organization, GroupMember, Experiment, RFIDAssignment, WeightMeasurement, Collaborator, CalendarEvent, Comment, Friend, Cage, Animal, Sample, Dose, Observation, Comment)
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, authenticate, get_user_model
import pandas as pd
from django.views.decorators.csrf import csrf_exempt
import random
from django.contrib.auth import logout
from django.db import IntegrityError
from django.utils.timezone import now
import hashlib
from dashboard.data_collection_views import generate_unique_signature
from .forms import CustomUserCreationForm, UpdateProfileForm, ExperimentForm
import json
from django.http import HttpResponseRedirect
from django.utils.safestring import mark_safe
from .forms import UserProfileForm
from .forms import ProfilePictureForm
from .forms import UpdateProfileForm, OverviewForm, ObservationForm, SampleForm, DoseForm
from django.views.decorators.http import require_http_methods
from django.utils.dateparse import parse_date, parse_datetime
import csv
from .models import Invitation, UserAction, User
from django.core.exceptions import ObjectDoesNotExist
from datetime import datetime
from datetime import date
logger = logging.getLogger(__name__)


User = get_user_model()
@login_required
def calendar_view(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    users = User.objects.filter(organization=organization).exclude(id=request.user.id)  # Exclude yourself

    # 🛠️ Detect if you are in Admin
    if '/admin/' in request.path:
        base_template = 'admin/base_admin_dashboard.html'
    else:
        base_template = 'base_dashboard.html'

    return render(request, 'calendar.html', {
        'org_id': org_id,
        'users': users,
        'base_template': base_template,  # Pass this to the template
    })

def generate_recurring_events(event, start_date, end_dt, interval, frequency, days, end_type, recurrence_end_date, occurrences):
    # Restrict occurrences to a maximum of 30
    max_occurrences = min(occurrences, 30)

    # Define frequency based on the recurrence type
    if frequency == "daily":
        rule_freq = DAILY
    elif frequency == "weekly":
        rule_freq = WEEKLY
    else:
        # Default to weekly for bi-weekly recurrence
        rule_freq = WEEKLY
        interval = 2 if frequency == "biweekly" else interval  # Set interval to 2 weeks if bi-weekly

    # Define weekdays for custom recurrences
    day_codes = {'SU': 0, 'MO': 1, 'TU': 2, 'WE': 3, 'TH': 4, 'FR': 5, 'SA': 6}
    weekdays = [day_codes[day] for day in days] if days else None

    # Set up the recurrence rule
    rule = rrule(
        freq=rule_freq,
        interval=interval,
        dtstart=start_date,
        until=recurrence_end_date if end_type == 'on' else None,
        count=max_occurrences if end_type == 'after' else None,
        byweekday=weekdays
    )

    # Create events based on the recurrence rule
    created_count = 0
    for dt in rule:
        if created_count >= max_occurrences:
            break

        # Check if an event already exists for this date
        existing_event = CalendarEvent.objects.filter(
            start_date=dt,
            user=event.user,
            organization=event.organization
        ).exists()
        
        if not existing_event:
            # Create a new event based on the calculated start date (dt)
            CalendarEvent.objects.create(
                title=event.title,
                description=event.description,
                start_date=dt,
                end_date=dt + (end_dt - start_date),
                color=event.color,
                all_day=event.all_day,
                user=event.user,
                organization=event.organization,
                is_recurring=False
            )
            created_count += 1


@login_required
def events(request, org_id):
    if request.method == 'GET':
        events = CalendarEvent.objects.filter(user=request.user, organization__id=org_id)
        events_list = [{
            'id': e.id,
            'title': e.title,
            'start': e.start_date.isoformat(),
            'end': e.end_date.isoformat(),
            'color': e.color,
            'allDay': e.all_day,
            'description': e.description,
            'project_task': {
                'task_id': e.project_task.task_id,
                'project_id': e.project_task.project.id,
            } if e.project_task else None,
        } for e in events]
        return JsonResponse(events_list, safe=False)

    if request.method == 'POST':
        data = json.loads(request.body)
        CalendarEvent.objects.create(
            user=request.user,
            organization_id=org_id,
            title=data['title'],
            start_date=data['start'],
            end_date=data['end'],
            color=data.get('color', '#1E90FF'),
            all_day=data.get('all_day', False),  # Save all_day status
            experiment=None
        )
        return JsonResponse({'success': True})
    
@login_required
@require_POST
def add_event(request, org_id):
    data = json.loads(request.body)
    title = data.get("title")
    description = data.get("description")
    start_date_str = data.get("start")
    end_date_str = data.get("end")
    color = data.get("color", "#1E90FF")  # Default color
    all_day = data.get("all_day", False)
    invite_usernames = data.get("invite_users", [])
    recurrence = data.get("recurrence") or {}

    # Parse dates
    start_date = parse_datetime(start_date_str) if start_date_str else None
    end_date = parse_datetime(end_date_str) if end_date_str else None

    # Create the main event
    event = CalendarEvent.objects.create(
        user=request.user,
        organization_id=org_id,
        title=title,
        description=description,
        start_date=start_date,
        end_date=end_date,
        color=color,
        all_day=all_day,
    )

    # Log the action in UserAction
    try:
        UserAction.objects.create(
            user=request.user,
            organization_id=org_id,
            action="Add Event",
            additional_info=f"Added event '{title}' to the calendar.",
            typed_signature="N/A",  # No user signature required
            unique_signature=generate_unique_signature(request.user, f"Add Event {event.id}", now()),
            timestamp=now()
        )
        logger.info(f"UserAction logged for adding event '{title}' by user {request.user.username}.")
    except Exception as e:
        logger.error(f"Error logging UserAction for adding event '{title}' by user {request.user.username}: {e}")

    # Process invited users and send invitations
    for username in invite_usernames:
        try:
            invited_user = User.objects.get(username=username)

            # Ensure a conversation exists between the two users
            conversation, created = Conversation.objects.get_or_create(
                user1=request.user,
                user2=invited_user,
                defaults={'organization_id': org_id, 'type': 'private'}
            )

            # Format the event invitation message
            message_content = (
                f"You have been invited to an event:\n"
                f"**Title:** {title}\n"
                f"**Description:** {description or 'No description provided'}\n"
                f"**Start:** {start_date}\n"
                f"**End:** {end_date}\n"
                "Please check your calendar for more details."
            )

            # Create the message in the conversation
            Message.objects.create(
                conversation=conversation,
                sender=request.user,
                content=message_content,
                event_id=event.id,
                user_id=invited_user.id
            )
        except ObjectDoesNotExist:
            logger.warning(f"User with username {username} does not exist.")
            continue

    # Only call `generate_recurring_events` if a valid recurrence type is provided
    if recurrence.get("type") and recurrence.get("type") != "none":
        generate_recurring_events(
            event=event,
            start_date=start_date,
            end_dt=end_date,
            interval=recurrence.get("interval", 1),
            frequency=recurrence.get("type"),
            days=recurrence.get("days", []),
            end_type=recurrence.get("end_type"),
            recurrence_end_date=recurrence.get("endDate"),
            occurrences=recurrence.get("maxOccurrences", 30),
        )

    return JsonResponse({"status": "success", "event_id": event.id, "event_count": 1})

@login_required
def accept_invite(request, org_id, event_id, user_id):
    event = get_object_or_404(CalendarEvent, id=event_id)
    invited_user = get_object_or_404(User, id=user_id)
    
    if invited_user != request.user:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    CalendarEvent.objects.create(
        user=invited_user,
        organization=event.organization,
        title=event.title,
        description=event.description,
        start_date=event.start_date,
        end_date=event.end_date,
        color=event.color,
        all_day=event.all_day,
    )

    return JsonResponse({'status': 'success', 'message': 'Event accepted and added to your calendar.'})
@login_required
def decline_invite(request, org_id, event_id, user_id):
    invited_user = get_object_or_404(User, id=user_id)
    
    if invited_user != request.user:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
    
    # Here you can mark the invitation as declined if you want to track declined invitations
    return JsonResponse({'status': 'success', 'message': 'You have declined the invitation.'})

@login_required
@require_POST
def respond_to_invitation(request, org_id, event_id, user_id):
    data = json.loads(request.body)
    response = data.get('response')  # "accepted" or "declined"
    
    # Fetch or create the invitation record
    try:
        event = CalendarEvent.objects.get(id=event_id, organization_id=org_id)
        invitation, created = EventInvitation.objects.get_or_create(user_id=user_id, event=event)
    except CalendarEvent.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Event not found'}, status=404)

    # Update the invitation status and save
    if response in ["accepted", "declined"]:
        invitation.status = response  # Update status with response
        invitation.save()

        # Add to calendar if accepted
        if response == "accepted":
            CalendarEvent.objects.create(
                user=request.user,
                organization_id=org_id,
                title=event.title,
                description=event.description,
                start_date=event.start_date,
                end_date=event.end_date,
                color=event.color,
                all_day=event.all_day,
                is_recurring=event.is_recurring,
            )

        return JsonResponse({'status': 'success', 'message': f'Event {response}'})
    return JsonResponse({'status': 'error', 'message': 'Invalid response'}, status=400)

@login_required
@require_POST
def delete_calendar_event(request, org_id, event_id):
    event = get_object_or_404(CalendarEvent, id=event_id, user=request.user, organization_id=org_id)
    event.delete()
    return JsonResponse({'status': 'Event deleted successfully'})
@login_required
def upcoming_events(request, org_id):
    today = timezone.now().date()
    upcoming_events = CalendarEvent.objects.filter(
        user=request.user,
        organization__id=org_id,
        start_date__gte=timezone.now().date()
    ).order_by('start_date')
    events_data = [{
        'id': event.id,
        'title': event.title,
        'start': event.start_date.isoformat(),
        'end': event.end_date.isoformat(),
        'experiment_id': event.experiment.id if event.experiment else None,  # Include experiment ID
    } for event in upcoming_events]
    return JsonResponse(events_data, safe=False)
@login_required
def get_upcoming_events_count(request, org_id):
    try:
        upcoming_count = CalendarEvent.objects.filter(
            user=request.user, 
            organization_id=org_id, 
            start_date__gt=timezone.now()
        ).count()
        return JsonResponse({'upcoming_count': upcoming_count})
    except Exception as e:
        print(f"Error in get_upcoming_events_count: {e}")
        return JsonResponse({'error': str(e)})
    
from django.urls import reverse

@login_required
def today_or_upcoming_events(request, org_id):
    # Get the user's timezone
    user_timezone = timezone.get_current_timezone()

    # Define today's time range
    today_start = timezone.localtime(timezone.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timezone.timedelta(days=1)

    # Fetch today's events
    today_events = CalendarEvent.objects.filter(
        user=request.user,
        organization__id=org_id,
        start_date__gte=today_start,
        start_date__lt=today_end
    ).order_by('start_date')

    # Prepare event data with links
    events_data = []
    for event in today_events:
        if "Monitoring" in event.title:
            url = reverse('data_collection', args=[org_id, event.experiment.id]) if event.experiment else "#"
        elif "Task" in event.title:
            url = reverse('experiment_home', args=[org_id, event.experiment.id]) if event.experiment else "#"
        else:
            url = "#"

        events_data.append({
            'id': event.id,
            'title': event.title,
            'start': event.start_date.isoformat(),
            'end': event.end_date.isoformat(),
            'description': event.description,
            'color': event.color,
            'all_day': event.all_day,
            'url': url,
            'completed': event.completed,  # Use the correct `completed` field
        })

    return JsonResponse(events_data, safe=False)

def schedule_task_events(experiment, tasks, user, org_id):
    """
    Adds task events to the calendar based on the task frequency and experiment duration.
    """
    for task in tasks:
        title = task['title']
        description = task['description']
        frequency = int(task['frequency'])
        
        # Start scheduling from the current date
        current_date = timezone.now().date()

        # Create events based on the frequency until the end of the experiment
        while current_date <= timezone.now().date() + timedelta(days=experiment.duration):
            CalendarEvent.objects.create(
                title=title,
                description=description,
                start_date=current_date,
                end_date=current_date,
                user=user,
                organization_id=org_id,
                experiment=experiment
            )
            current_date += timedelta(days=frequency)


@login_required
def get_completed_events_count(request, org_id):
    try:
        completed_count = CalendarEvent.objects.filter(
            user=request.user, 
            organization_id=org_id, 
            completed=True
        ).count()
        return JsonResponse({'completed_count': completed_count})
    except Exception as e:
        print(f"Error in get_completed_events_count: {e}")
        return JsonResponse({'error': str(e)})
@login_required
def agenda_view(request, org_id):
    today = timezone.now().date()
    upcoming_events = CalendarEvent.objects.filter(user=request.user, organization_id=org_id, start_date__gte=today).order_by('start_date')

    return render(request, 'agenda.html', {'upcoming_events': upcoming_events})
@login_required
def mark_event_completed(request, org_id, event_id):
    if request.method == 'POST':
        try:
            # Get the event
            event = CalendarEvent.objects.get(id=event_id, organization_id=org_id)

            # Get the experiment owner and all collaborators
            experiment = event.experiment
            owner = experiment.owner
            collaborators = experiment.collaborators()  # Assuming this is a many-to-many field referencing `User`

            # Combine the owner and collaborators into a single queryset of users
            assigned_users = User.objects.filter(Q(id=owner.id) | Q(id__in=collaborators.values_list('user_id', flat=True)))

            # Mark the event as completed for the current user
            event_completion, created = EventCompletion.objects.get_or_create(user=request.user, event=event)
            event_completion.completed = True
            event_completion.completed_at = timezone.now()
            event_completion.save()

            # Check if all users (owner + collaborators) have completed the event
            all_completed = EventCompletion.objects.filter(event=event, user__in=assigned_users).count() == assigned_users.count()

            if all_completed:
                event.completed = True
                event.completed_at = timezone.now()  # Set the overall event completion time
            else:
                event.completed = False  # Not fully completed if not all users are done
            event.save()

            return JsonResponse({'status': 'success', 'message': 'Event marked as completed'})
        except CalendarEvent.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Event not found'}, status=404)
    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)

def generate_monthly_dates(start_date, end_date):
    dates = []
    current_date = start_date
    while current_date <= end_date:
        dates.append(current_date)
        current_date += timedelta(days=30)  # Adjust based on your needs
    return dates

def generate_custom_repetition_dates(start_date, end_date, days_of_week):
    days_of_week_map = {'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 'Thursday': 3, 'Friday': 4, 'Saturday': 5, 'Sunday': 6}
    selected_days = [days_of_week_map[day] for day in days_of_week]
    dates = []
    current_date = start_date
    while current_date <= end_date:
        if current_date.weekday() in selected_days:
            dates.append(current_date)
        current_date += timedelta(days=1)
    return dates