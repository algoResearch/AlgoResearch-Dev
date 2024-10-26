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
from datetime import timedelta
from datetime import timezone as dt_timezone  
from datetime import timezone as datetime_timezone
from .models import (Conversation, EventCompletion, Message, User, GroupMember, Experiment, RFIDAssignment, WeightMeasurement, Collaborator, CalendarEvent, Comment, Friend, Cage, Animal, Sample, Dose, Observation, Comment)
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
logger = logging.getLogger(__name__)

@login_required
def events(request, org_id):
    if request.method == 'GET':
        # Fetch events from the database for the specified organization
        events = CalendarEvent.objects.filter(user=request.user, organization__id=org_id)
        for event in events:
            logger.info(f"Event: {event.title}, Start Date (UTC): {event.start_date}")

        events_list = [{
            'id': e.id,
            'title': e.title,
            'start': e.start_date.isoformat(),
            'end': e.end_date.isoformat()
        } for e in events]
        return JsonResponse(events_list, safe=False)


    if request.method == 'POST':
        data = json.loads(request.body)
        # Create a new event associated with the user's organization
        CalendarEvent.objects.create(
            user=request.user,
            organization_id=org_id,
            title=data['title'],
            start_date=data['start'],
            end_date=data['end'],
            experiment=None  # Optional if associated with an experiment
        )
        return JsonResponse({'success': True})

@login_required
@require_POST
def add_event(request, org_id):
    data = json.loads(request.body)
    title = data.get('title')
    start_date = data.get('start')
    end_date = data.get('end')

    if title and start_date and end_date:
        # Create and save the event
        CalendarEvent.objects.create(
            title=title,
            start_date=start_date,
            end_date=end_date,
            user=request.user,
            organization_id=org_id  # Link event to the user's organization
        )
        return JsonResponse({'status': 'success', 'message': 'Event added successfully'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid data'})


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

@login_required
def today_or_upcoming_events(request, org_id, experiment_id=None):
    # Get the user's timezone
    user_timezone = timezone.get_current_timezone()

    # Get the current date in the user's local timezone (ignore the time part)
    today_start = timezone.localtime(timezone.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    logger.info(f"Today's start (local): {today_start}, Today's end (local): {today_end}")

    # Use date filtering to avoid time mismatch issues
    today_events = CalendarEvent.objects.filter(
        user=request.user,
        organization__id=org_id,
        start_date__gte=today_start.date(),  # Using only the date part
        start_date__lt=today_end.date()      # Using only the date part
    ).order_by('completed', 'completed_at', 'start_date')

    logger.info(f"Fetched events for today: {today_events}")

    # Prepare event data for the response
    events_data = [{
        'id': event.id,
        'title': event.title,
        'start': event.start_date.isoformat(),
        'end': event.end_date.isoformat(),
        'completed': event.completed,
        'completed_at': event.completed_at.isoformat() if event.completed_at else None,
        'experiment_id': event.experiment.id if event.experiment else None,
        'experiment_name': event.experiment.name if event.experiment else None,
    } for event in today_events]

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