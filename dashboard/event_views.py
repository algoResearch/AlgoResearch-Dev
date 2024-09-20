from django.contrib import messages as django_messages
from django.core import serializers
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q, F, Avg, Max, Min, Count
from django.utils import timezone
from django.utils.timezone import now
from datetime import timedelta
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
@login_required
def events(request):
    if request.method == 'GET':
        events = CalendarEvent.objects.filter(user=request.user)
        events_list = [{
            'id': e.id,
            'title': e.title,
            'start': e.start_date.isoformat(),
            'end': e.end_date.isoformat()
        } for e in events]
        return JsonResponse(events_list, safe=False)

    if request.method == 'POST':
        data = json.loads(request.body)
        CalendarEvent.objects.create(
            user=request.user,
            title=data['title'],
            start_date=data['start'],
            end_date=data['end'],
            experiment=None  # Set if it is associated with an experiment
        )
        return JsonResponse({'success': True})

@login_required
@require_POST
def add_event(request):
    data = json.loads(request.body)
    title = data.get('title')
    start_date = data.get('start')
    end_date = data.get('end')

    if title and start_date and end_date:
        CalendarEvent.objects.create(
            title=title,
            start_date=start_date,
            end_date=end_date,
            user=request.user
        )
        return JsonResponse({'status': 'success', 'message': 'Event added successfully'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid data'})

@login_required
@require_POST
def delete_calendar_event(request, event_id):
    event = get_object_or_404(CalendarEvent, id=event_id, user=request.user)
    event.delete()
    return JsonResponse({'status': 'Event deleted successfully'})

@login_required
def upcoming_events(request):
    # Assuming you want a view to list upcoming events
    today = timezone.now().date()
    upcoming_events = CalendarEvent.objects.filter(user=request.user, start_date__gte=today)
    events_data = [{
        'id': event.id,
        'title': event.title,
        'start': event.start_date.isoformat(),
        'end': event.end_date.isoformat(),
        'allDay': True  # if your calendar supports all-day events
    } for event in upcoming_events]
    
    return JsonResponse(events_data, safe=False)

@login_required
def get_upcoming_events_count(request):
    upcoming_count = CalendarEvent.objects.filter(start_date__gt=now()).count()
    return JsonResponse({'upcoming_count': upcoming_count})


@login_required
def today_or_upcoming_events(request, experiment_id):
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    # Filter events for today by checking if start_date is within the day's range
    today_events = CalendarEvent.objects.filter(user=request.user, start_date__gte=today_start, start_date__lt=today_end)

    # If no events for today, get the next upcoming events
    if not today_events.exists():
        today_events = CalendarEvent.objects.filter(user=request.user, start_date__gte=today_start).order_by('start_date')[:5]  # Limit to next 5 events

    events_data = [{
        'id': event.id,
        'title': event.title,
        'start': event.start_date.isoformat(),
        'end': event.end_date.isoformat(),
        'experiment_id': event.experiment.id if event.experiment else None  # Include experiment ID if it exists
    } for event in today_events]

    return JsonResponse(events_data, experiment_id, safe=False)

@login_required
def today_or_upcoming_events(request, experiment_id=None):
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    if experiment_id:
        today_events = CalendarEvent.objects.filter(
            user=request.user, 
            start_date__gte=today_start, 
            start_date__lt=today_end, 
            experiment__id=experiment_id
        )
    else:
        today_events = CalendarEvent.objects.filter(
            user=request.user, 
            start_date__gte=today_start, 
            start_date__lt=today_end
        )

    events_data = [{
        'id': event.id,
        'title': event.title,
        'start': event.start_date.isoformat(),
        'end': event.end_date.isoformat(),
        'experiment_id': event.experiment.id if event.experiment else None
    } for event in today_events]

    return JsonResponse(events_data, safe=False)

@login_required
def agenda_view(request):
    # Get today's date
    today = timezone.now().date()
    
    # Fetch all upcoming events starting from today
    upcoming_events = CalendarEvent.objects.filter(start_date__gte=today).order_by('start_date')
    
    return render(request, 'agenda.html', {'upcoming_events': upcoming_events})

