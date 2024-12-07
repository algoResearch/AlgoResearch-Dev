from django.contrib import messages 
from django.contrib import messages as django_messages
from django.core import serializers
from django.shortcuts import render, redirect, get_object_or_404
import re
from django.utils.timezone import make_aware
from django.contrib.auth.models import User
import calendar
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from itertools import groupby
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden, HttpResponseBadRequest, HttpResponseServerError
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
import uuid
import os
from django.db.models import Q, F, Avg, Max, Min, Count
from django.utils import timezone
from .models import (Conversation, Task, Group, Treatment, InboxNotification, Organization, Message, User, GroupMember, Experiment, RFIDAssignment, WeightMeasurement, Collaborator, CalendarEvent, Drug, Strain, Comment, Friend, Cage, Animal, Sample, Dose, Observation, Comment)
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, authenticate
import pandas as pd
from django.views.decorators.csrf import csrf_exempt
import random
from django.core.paginator import Paginator
from django.contrib.auth import logout
from django.db import IntegrityError
import pytz  # For timezone conversion if necessary
from .forms import CustomUserCreationForm, UpdateProfileForm, ExperimentForm, ImportForm, AssignTaskForm, ExperimentBasicInfoForm, ExperimentMetricsForm
import json
from datetime import datetime, timedelta
from django.http import HttpResponseRedirect
from django.utils.safestring import mark_safe
from dateutil.relativedelta import relativedelta
from django.db import transaction
from .forms import UserProfileForm
from .forms import ProfilePictureForm
from .forms import UpdateProfileForm, OverviewForm, ObservationForm, SampleForm, DoseForm
from django.views.decorators.http import require_http_methods
from django.utils.dateparse import parse_datetime
import csv
from .models import Invitation, UserAction
from datetime import date
from django.urls import reverse
import logging

logger = logging.getLogger(__name__)  # Set up a logger for error tracking

def add_events_to_calendar(user, experiment, organization, weight_schedule, weigh_in_interval, experiment_duration, tumor_schedule, tumor_measurement_interval, tumor_duration):
    """
    Helper function to add weigh-in and tumor measurement events to a user's calendar.
    """
    # Create weigh-in events if a weigh-in schedule exists
    if weight_schedule == 'yes' and weigh_in_interval and experiment_duration:
        current_date = timezone.now().date()
        while current_date < timezone.now().date() + timezone.timedelta(days=experiment_duration):
            CalendarEvent.objects.create(
                user=user,
                organization=organization,
                title=f"Weigh-In for {experiment.name}",
                start_date=current_date,
                end_date=current_date,
                experiment=experiment,
                color='blue'
            )
            current_date += timezone.timedelta(days=weigh_in_interval)

    # Create tumor measurement events if a tumor schedule exists
    if tumor_schedule == 'yes' and tumor_measurement_interval and tumor_duration:
        current_date = timezone.now().date()
        while current_date < timezone.now().date() + timezone.timedelta(days=tumor_duration):
            CalendarEvent.objects.create(
                user=user,
                organization=organization,
                title=f"Tumor Measurement for {experiment.name}",
                start_date=current_date,
                end_date=current_date,
                experiment=experiment,
                color='red'
            )
            current_date += timezone.timedelta(days=tumor_measurement_interval)

def assign_animals_to_cages(experiment, number_of_animals, max_per_cage):
    # Fetch existing animals for the experiment and convert to a list
    animals = list(Animal.objects.filter(experiment=experiment))

    # Generate missing animals if needed
    for i in range(len(animals), number_of_animals):
        animal_index = i + 1  # Ensure the animal index is unique and non-null
        new_animal = Animal.objects.create(
            experiment=experiment,
            animal_index=animal_index,
            organization=experiment.organization  # Ensure the organization is set for the animal
        )
        animals.append(new_animal)  # Append the new animal to the list

        # Associate the strains and drugs from the experiment to the animal
        new_animal.strains.set(experiment.strain_list.all())
        new_animal.drugs.set(experiment.drug_list.all())

    # Assign animals to cages
    animal_counter = 0
    for cage_number in range(1, (number_of_animals // max_per_cage) + 2):
        for _ in range(max_per_cage):
            if animal_counter < len(animals):
                animal = animals[animal_counter]
                
                # Generate a unique RFID for each assignment
                unique_rfid = f'RFID_{experiment.id}_{animal.animal_index}'  # Example: RFID_1_1

                # Check if RFID already exists in the current experiment organization
                if not RFIDAssignment.objects.filter(rfid=unique_rfid, experiment__organization=experiment.organization).exists():
                    RFIDAssignment.objects.create(
                        rfid=unique_rfid,
                        animal=animal,
                        experiment=experiment,
                        cage_number=cage_number  # Removed the 'organization' field
                    )
                    animal_counter += 1
                else:
                    # Handle the case where RFID is already in use
                    print(f"Skipping RFID {unique_rfid} as it already exists.")
            else:
                break
@login_required
def drafts(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    user = request.user

    # Include only drafts where the user is the owner or a collaborator
    drafts = Experiment.objects.filter(
        Q(owner=user) | Q(collaborators__user=user),  # User involvement
        organization=organization,  # Belongs to the same organization
        is_draft=True  # Only drafts
    ).distinct().select_related('owner').order_by('-created_at')

    return render(request, 'drafts.html', {
        'org_id': org_id,
        'drafts': drafts,
    })

@login_required
def delete_draft(request, org_id, experiment_id):
    if request.method == 'POST':  # Ensure the request is a POST request
        # Fetch the draft experiment and verify it belongs to the organization and the logged-in user
        experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id, owner=request.user)

        if not experiment.step_basic_info_completed:  # Only allow deleting drafts
            experiment.delete()
            return JsonResponse({'status': 'success', 'message': 'Draft deleted successfully.'})
        else:
            return JsonResponse({'status': 'error', 'message': 'Cannot delete a completed experiment.'}, status=400)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=400)
@login_required
def experiment_basic_info(request, org_id, experiment_id=None):
    logger.info("Testing logger in experiment_basic_info view")
    organization = get_object_or_404(Organization, id=org_id)

    # Fetch or create the experiment
    if experiment_id:
        experiment = get_object_or_404(Experiment, id=experiment_id, organization=organization)
    else:
        experiment = Experiment.objects.create(
            organization=organization,
            owner=request.user,
            status='draft'
        )

    if request.method == 'POST':
        # Update experiment details
        experiment.name = request.POST.get('name', experiment.name).strip()
        experiment.description = request.POST.get('description', experiment.description).strip()
        start_date = request.POST.get('start_date', None)

        try:
            experiment.start_date = start_date if start_date else experiment.start_date
        except ValueError:
            messages.error(request, "Invalid date format. Please use YYYY-MM-DD.")
            return render(request, 'experiment_basic_info.html', {
                'org_id': org_id,
                'experiment': experiment,
                'experiment_id': experiment.id,
            })

        # Save as Draft
        if 'save_as_draft' in request.POST:
            experiment.is_draft = True  # Ensure the draft flag is set
            experiment.status = 'draft'
            experiment.save()
            messages.success(request, "Experiment saved as draft.")
            return redirect('drafts', org_id=org_id)
        # Save and Continue
        if 'save_and_continue' in request.POST:
            experiment.step_basic_info_completed = True
            experiment.status = 'active'
            experiment.save()
            messages.success(request, "Experiment basic info completed.")
            return redirect('add_investigators', org_id=org_id, experiment_id=experiment.id)

        # Save changes
        experiment.save()

    context = {
        'org_id': org_id,
        'experiment': experiment,
        'experiment_id': experiment.id,
        'step_basic_info_completed': experiment.step_basic_info_completed,
        'step_investigators_completed': experiment.step_investigators_completed,
        'step_metrics_completed': experiment.step_metrics_completed,
        'step_tasks_completed': experiment.step_tasks_completed,
        'step_groups_completed': experiment.step_groups_completed,
        'step_summary_completed': experiment.step_summary_completed,
    }

    return render(request, 'experiment_basic_info.html', context)
@login_required
def add_investigators(request, org_id, experiment_id):
    organization = get_object_or_404(Organization, id=org_id)
    experiment = get_object_or_404(Experiment, id=experiment_id)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            selected_investigators = data.get('selected_investigators', [])
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)

        if not selected_investigators:
            # No investigators selected; mark step as completed
            experiment.step_investigators_completed = True
            experiment.save()
            return JsonResponse({'status': 'success', 'message': 'No investigators added. Step marked as completed.'})

        # Process valid investigators
        investigators = User.objects.filter(
            username__in=selected_investigators,
            organization=organization
        ).exclude(id=request.user.id)

        if investigators.exists():
            # Convert investigators into Collaborator objects
            for user in investigators:
                Collaborator.objects.get_or_create(
                    experiment=experiment,
                    user=user,
                    defaults={'role': 'Investigator'}  # Default role if none is provided
                )

            # Mark step as completed
            experiment.step_investigators_completed = True
            experiment.save()

            return JsonResponse({'status': 'success', 'message': 'Investigators added successfully.'})

        return JsonResponse({'status': 'error', 'message': 'No valid investigators found.'}, status=400)

    # Render the page for GET requests (if applicable)
    users = User.objects.filter(organization=organization).exclude(id=request.user.id)
    return render(request, 'add_investigators.html', {
        'users': users,
        'org_id': org_id,
        'experiment_id': experiment_id,
        'experiment': experiment,
    })

@login_required
def search_organization_users(request, org_id):
    query = request.GET.get('query', '').strip()
    organization = get_object_or_404(Organization, id=org_id)

    # Filter users in the organization matching the query
    users = User.objects.filter(
        organization=organization
    ).filter(
        Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query)
    ).exclude(id=request.user.id)  # Exclude the current user

    # Prepare the user data for the response
    user_data = [
        {
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'profile_picture': user.profile_picture.url if user.profile_picture else None,
        }
        for user in users
    ]

    return JsonResponse({'users': user_data})

@login_required
def experiment_metrics(request, org_id, experiment_id):
    # Fetch the experiment and ensure it belongs to the organization
    experiment = get_object_or_404(Experiment, id=experiment_id, organization__id=org_id)
    logger.info(f"Experiment Metrics request received for experiment: {experiment.name} (ID: {experiment_id})")

    # Fetch all investigators for the experiment
    investigators = [experiment.owner]
    if experiment.investigators:
        investigators += list(User.objects.filter(username__in=json.loads(experiment.investigators)))
    logger.info(f"Investigators for experiment {experiment.name}: {[user.username for user in investigators]}")

    if request.method == 'POST':
        logger.info("Processing form data for weight and tumor metrics...")
        
        # Determine which metrics are being monitored
        monitor_weight = request.POST.get('monitor_weight') == 'yes'
        monitor_tumor = request.POST.get('monitor_tumor') == 'yes'
        tumor_size_method = request.POST.get('tumor_size_method') if monitor_tumor else None

        logger.info(f"Monitor Weight: {monitor_weight}, Monitor Tumor Size: {monitor_tumor}, Tumor Size Method: {tumor_size_method}")

        # Validate required tumor fields if tumor monitoring is enabled
        if monitor_tumor and not tumor_size_method:
            return JsonResponse({'status': 'error', 'message': 'Tumor size method is required when monitoring tumor size.'}, status=400)

        # Process weight metrics if weight monitoring is enabled
        warning_weight_percentage = float(request.POST.get('warning_weight_percentage', 0)) if monitor_weight else None
        removal_weight_percentage = float(request.POST.get('removal_weight_percentage', 0)) if monitor_weight else None
        weight_frequency = request.POST.get('weight_frequency', '')
        custom_interval_days = int(request.POST.get('custom_interval_days', 0)) if request.POST.get('custom_interval_days') else None
        weight_end_date = request.POST.get('weight_end_date') if request.POST.get('weight_end_date') else None

        # Process tumor metrics if tumor monitoring is enabled
        tumor_volume_warning = float(request.POST.get('tumor_volume_warning', 0)) if monitor_tumor else None
        tumor_volume_removal = float(request.POST.get('tumor_volume_removal', 0)) if monitor_tumor else None
        tumor_frequency = request.POST.get('tumor_frequency', '')
        tumor_custom_interval_days = int(request.POST.get('tumor_custom_interval_days', 0)) if request.POST.get('tumor_custom_interval_days') else None
        tumor_end_date = request.POST.get('tumor_end_date') if request.POST.get('tumor_end_date') else None

        # Save the metrics to the experiment instance
        experiment.monitor_weight = monitor_weight
        experiment.warning_weight_percentage = warning_weight_percentage
        experiment.removal_weight_percentage = removal_weight_percentage
        experiment.monitor_tumor = monitor_tumor
        experiment.tumor_size_method = tumor_size_method
        experiment.tumor_volume_warning = tumor_volume_warning
        experiment.tumor_volume_removal = tumor_volume_removal

        experiment.save()
        logger.info(f"Saved metrics for experiment {experiment.id}: Monitor Weight: {experiment.monitor_weight}, Monitor Tumor: {experiment.monitor_tumor}")
        logger.info(f"Experiment {experiment.name} metrics saved.")

        # Mark this step as completed
        experiment.step_metrics_completed = True
        experiment.save()

        return redirect('task_schedules', org_id=org_id, experiment_id=experiment_id)

    return render(request, 'experiment_metrics.html', {
        'org_id': org_id,
        'experiment_id': experiment_id,
        'experiment': experiment,
        'monitor_weight': experiment.monitor_weight,
        'monitor_tumor': experiment.monitor_tumor,
        'tumor_size_method': experiment.tumor_size_method,
        'warning_weight_percentage': experiment.warning_weight_percentage,
        'removal_weight_percentage': experiment.removal_weight_percentage,
        'tumor_volume_warning': experiment.tumor_volume_warning,
        'tumor_volume_removal': experiment.tumor_volume_removal,
        'weight_frequency': experiment.weight_frequency,
        'tumor_frequency': experiment.tumor_frequency,
        'custom_interval_days': experiment.custom_interval_days,
        'tumor_custom_interval_days': experiment.tumor_custom_interval_days,
        'weight_end_date': experiment.weight_end_date,
        'tumor_end_date': experiment.tumor_end_date,
        'step_metrics_completed': experiment.step_metrics_completed,
    })


def schedule_events(start_date, frequency, custom_interval_days, end_date, experiment, investigators, event_type):
    """
    Schedules events based on specified frequency for a given experiment.
    """
    dates = []
    current_date = start_date

    # Use the provided end_date instead of a hardcoded one
    end_date = end_date if end_date else start_date + timedelta(weeks=12)

    if frequency == 'daily':
        dates = [current_date + timedelta(days=i) for i in range((end_date - start_date).days)]
    elif frequency == 'weekly':
        dates = [current_date + timedelta(weeks=i) for i in range(0, (end_date - start_date).days // 7)]
    elif frequency == 'biweekly':
        dates = [current_date + timedelta(weeks=i * 2) for i in range(0, (end_date - start_date).days // 14)]
    elif frequency == 'monthly':
        dates = generate_monthly_dates(start_date, end_date)
    elif frequency == 'custom' and custom_interval_days > 0:
        dates = [current_date + timedelta(days=i * custom_interval_days) for i in range(0, (end_date - start_date).days // custom_interval_days)]

    for date in dates:
        for investigator in investigators:
            CalendarEvent.objects.create(
                title=f"{event_type.capitalize()} Monitoring for {experiment.name}",
                start_date=date,
                end_date=date,
                user=investigator,
                experiment=experiment,
                organization=experiment.organization
            )
    logger.info(f"Scheduled {len(dates) * len(investigators)} events for {event_type} monitoring")

def generate_monthly_dates(start_date, end_date):
    """
    Generates a list of monthly dates from start_date to end_date.
    """
    dates = []
    current_date = start_date
    while current_date <= end_date:
        dates.append(current_date)
        current_date += relativedelta(months=1)
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

def schedule_events_for_days(start_date, days, weeks, experiment, investigators, event_type):
    """
    Helper function to schedule separate events on specific days for a given number of weeks.
    """
    weekdays = {day: i for i, day in enumerate(calendar.day_name)}  # Map day names to weekdays
    selected_weekdays = [weekdays[day] for day in days]  # Get corresponding weekday numbers
    logger.info(f"Selected weekdays for scheduling: {selected_weekdays}")

    # Calculate specific dates for scheduling
    specific_dates = []
    for week in range(weeks):
        for weekday in selected_weekdays:
            event_date = start_date + timedelta(days=(week * 7) + weekday - start_date.weekday())
            if event_date >= start_date:  # Ensure event is not in the past
                specific_dates.append(event_date)

    # Create a separate CalendarEvent for each date in specific_dates
    for event_date in specific_dates:
        for investigator in investigators:
            CalendarEvent.objects.create(
                user=investigator,
                title=f"{event_type.capitalize()} Monitoring for {experiment.name}",
                organization=experiment.organization,
                start_date=event_date,
                end_date=event_date,  # Use the same date for start and end to create a single-day event
                specific_dates=[event_date],  # Only the current date in specific_dates
                experiment=experiment,
                description=f"Scheduled {event_type} monitoring for {event_date}.",
                color="blue" if event_type == "weight" else "green"
            )
            logger.info(f"Scheduled {event_type} event on {event_date} for {investigator.username}")

@login_required
def add_alert(request, org_id, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization__id=org_id)

    if request.method == 'POST':
        metric_type = request.POST.get('metric_type')
        warning_threshold = float(request.POST.get('warning_threshold'))
        removal_threshold = float(request.POST.get('removal_threshold'))

        # Validate thresholds
        if warning_threshold <= removal_threshold:
            return JsonResponse({'status': 'error', 'message': 'Warning threshold must be greater than removal threshold'}, status=400)

        # Update the appropriate fields on the Experiment model
        if metric_type == 'weight':
            experiment.warning_weight_percentage = warning_threshold
            experiment.removal_weight_percentage = removal_threshold
        elif metric_type == 'tumor':
            experiment.tumor_volume_warning = warning_threshold
            experiment.tumor_volume_removal = removal_threshold

        experiment.save()
        return redirect('experiment_metrics', org_id=org_id, experiment_id=experiment_id)

    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)
@login_required
def task_schedules(request, org_id, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization__id=org_id)

    if request.method == 'POST':
        # Check if "Save and Continue" was clicked
        if 'save_and_continue' in request.POST:
            experiment.step_tasks_completed = True  # Mark the step as completed
            experiment.save()  # Save the experiment to update the database
            logger.info(f"Task Schedules completed for Experiment ID {experiment.id}. step_tasks_completed = {experiment.step_tasks_completed}")
            return redirect('create_groups', org_id=org_id, experiment_id=experiment_id)
    # Render the page for GET requests
    tasks = Task.objects.filter(experiment=experiment)
    return render(request, 'task_schedules.html', {
        'org_id': org_id,
        'experiment_id': experiment.id,
        'experiment': experiment,
        'tasks': tasks,
    })
@login_required
def create_groups(request, org_id, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)

    available_animals = Animal.objects.filter(
        organization_id=org_id,
        experiment__isnull=True,
        is_available=True
    )
    groups = Group.objects.filter(experiment=experiment)

    logger.info(f"Request GET parameters: {request.GET}")

    # Handle "Next" button action
    if request.GET.get('next') == 'true':
        logger.info(f"'next=true' detected for experiment ID {experiment_id}")
        # Ensure at least one group exists before marking the step as completed
        if groups.exists():
            experiment.step_groups_completed = True
            experiment.save()
            logger.info(f"Groups step marked as completed for experiment ID {experiment.id}. step_groups_completed = {experiment.step_groups_completed}")
        else:
            logger.warning(f"No groups exist for experiment ID {experiment_id}. Cannot mark step as completed.")
        return redirect('experiment_summary', org_id=org_id, experiment_id=experiment_id)

    # Handle POST requests for group creation
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            group_name = data.get('group_name')
            group_color = data.get('group_color')
            selected_animal_ids = data.get('selected_animals', [])

            if group_name and group_color:
                group = Group.objects.create(
                    name=group_name,
                    color=group_color,
                    number_of_animals=len(selected_animal_ids),
                    experiment=experiment
                )

                animals_to_add = Animal.objects.filter(
                    id__in=selected_animal_ids,
                    organization=experiment.organization,
                    is_available=True,
                    experiment__isnull=True
                )

                for animal in animals_to_add:
                    animal.group = group
                    animal.experiment = experiment
                    animal.is_available = False
                    animal.save()

                logger.info(f"Group '{group.name}' created successfully for experiment ID {experiment.id}")
                return JsonResponse({'status': 'success', 'group_id': group.id})
            else:
                logger.warning(f"Group creation failed for experiment ID {experiment.id}. Missing name or color.")
                return JsonResponse({'status': 'error', 'message': 'Group name or color missing'})

        except Exception as e:
            logger.error(f"Error creating group for experiment ID {experiment.id}: {e}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return render(request, 'groups.html', {
        'experiment': experiment,
        'groups': groups,
        'available_animals': available_animals,
        'org_id': org_id,
        'experiment_id': experiment_id,
        'step_basic_info_completed': experiment.step_basic_info_completed,
        'step_investigators_completed': experiment.step_investigators_completed,
        'step_metrics_completed': experiment.step_metrics_completed,
        'step_tasks_completed': experiment.step_tasks_completed,
        'step_groups_completed': experiment.step_groups_completed,
        'step_summary_completed': experiment.step_summary_completed,
    })

@login_required
def add_group(request, org_id, experiment_id):
    if request.method == 'POST':
        experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)
        data = json.loads(request.body)

        group_name = data.get('group_name')
        group_color = data.get('group_color')
        selected_animal_ids = data.get('selected_animals', [])

        logger.info(f"Received request to create group '{group_name}' with color '{group_color}' for experiment ID {experiment_id}")

        if group_name and group_color and selected_animal_ids:
            group = Group.objects.create(
                name=group_name,
                color=group_color,
                number_of_animals=len(selected_animal_ids),
                experiment=experiment
            )
            logger.info(f"Group '{group_name}' created with ID {group.id} for experiment ID {experiment_id}")

            animals_to_add = Animal.objects.filter(
                id__in=selected_animal_ids,
                organization=experiment.organization,
                is_available=True,
                experiment__isnull=True
            )

            for animal in animals_to_add:
                # Assign group, experiment, and tracking date to the animal
                animal.group = group
                animal.experiment = experiment
                animal.tracking_date = timezone.now().date()  # Set the tracking date to the current date
                animal.is_available = False
                animal.save()
                logger.info(f"Animal ID {animal.id} successfully assigned to group '{group_name}' and experiment ID {experiment_id}")
                logger.info(f"Animal ID {animal.id} assigned with tracking_date {animal.tracking_date}")
                # Generate a unique RFID
                unique_rfid = f"RFID_{experiment.id}_{animal.animal_index}"
                
                # Check and ensure RFID uniqueness
                existing_assignment = RFIDAssignment.objects.filter(rfid=unique_rfid).first()
                if existing_assignment:
                    logger.warning(f"RFID {unique_rfid} already assigned. Skipping assignment for Animal ID {animal.id}.")
                else:
                    # Create RFIDAssignment
                    RFIDAssignment.objects.create(
                        rfid=unique_rfid,
                        animal=animal,
                        experiment=experiment,
                        cage_number=animal.cage.cage_number if animal.cage else 'N/A'
                    )
                    logger.info(f"RFIDAssignment created for Animal ID {animal.id} with RFID {unique_rfid}")

                # Update Samples and Doses to link to the experiment
                Sample.objects.filter(animal=animal, experiment__isnull=True).update(experiment=experiment)
                Dose.objects.filter(animal=animal, experiment__isnull=True).update(experiment=experiment)

            return JsonResponse({'status': 'success', 'group_id': group.id})
        else:
            logger.warning("Incomplete data provided for group creation")
            return JsonResponse({'status': 'error', 'message': 'Incomplete data'}, status=400)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)

@login_required
def assign_treatment(request, org_id, experiment_id):
    if request.method == 'POST':
        group_id = request.POST.get('group_id')
        drug_name = request.POST.get('drug_name')
        dose = request.POST.get('dose')
        stock_concentration = request.POST.get('stock_concentration')
        dose_volume = request.POST.get('dose_volume')

        # Get the group object
        group = get_object_or_404(Group, id=group_id, experiment_id=experiment_id)

        # Create a treatment and assign it to the group
        treatment = Treatment.objects.create(
            experiment=group.experiment,
            drug_name=drug_name,
            dose=dose,
            stock_concentration=stock_concentration,
            dose_volume=dose_volume,
            created_by=request.user
        )

        # Assign the treatment to the group
        group.treatment = treatment
        group.save()

        # Assign this treatment to all animals in the group
        animals = Animal.objects.filter(group=group)
        for animal in animals:
            animal.treatments.add(treatment)

        return JsonResponse({
            'status': 'success',
            'message': 'Treatment assigned successfully',
            'group_id': group.id,
            'drug_name': treatment.drug_name,
            'dose': treatment.dose
        })

    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)

@login_required
def experiment_summary(request, org_id, experiment_id):
    """
    Handles the summary step of the experiment creation process.
    Marks the summary step as completed and finalizes the experiment.
    """
    # Fetch the experiment and ensure it belongs to the organization
    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)
    logger.info(f"Entered experiment_summary for experiment ID {experiment.id}")

    if request.method == "POST":
        logger.info(f"Processing form submission for summary step of experiment ID {experiment.id}")

        # Mark the summary step as completed
        experiment.step_summary_completed = True
        experiment.is_draft = False  # Mark as no longer a draft
        experiment.status = "active"  # Ensure the experiment status is set to active

        try:
            # Save the experiment
            experiment.save()
            logger.info(f"Experiment {experiment.name} (ID: {experiment.id}) marked as summary step completed.")

            # Re-fetch the experiment from the database to confirm the save
            experiment.refresh_from_db()
            logger.info(f"Database state after save: step_summary_completed={experiment.step_summary_completed}, is_draft={experiment.is_draft}, status={experiment.status}")
        except Exception as e:
            logger.error(f"Failed to save experiment {experiment.name} (ID: {experiment.id}): {e}")
            return render(request, 'summary.html', {
                'org_id': org_id,
                'experiment': experiment,
                'experiment_id': experiment.id,
                'tasks': experiment.task_set.all(),
                'groups': experiment.group_set.all(),
                'error': "An error occurred while finalizing the experiment. Please try again."
            })

        return redirect('experiment_home', org_id=org_id, experiment_id=experiment.id)

    # For GET requests, render the summary page
    logger.info(f"Rendering summary page for experiment ID {experiment.id}")
    return render(request, 'summary.html', {
        'org_id': org_id,
        'experiment': experiment,
        'experiment_id': experiment.id,
        'tasks': experiment.task_set.all(),
        'groups': experiment.group_set.all(),
    })

def assign_animals_to_groups(experiment, groups):
    for group in groups:
        animals = list(Animal.objects.filter(group=group, experiment=experiment))
        number_of_animals = group.number_of_animals

        # Assign or create missing animals as needed
        for i in range(len(animals), number_of_animals):
            animal_index = i + 1 + sum(g.number_of_animals for g in groups if g.id < group.id)
            new_animal = Animal.objects.create(
                experiment=experiment,
                animal_index=animal_index,
                group=group,
                organization=experiment.organization,
                is_available=False  # Mark as assigned to an experiment
            )
            animals.append(new_animal)

        # Create unique RFIDAssignments for each animal in the group
        for animal in animals:
            unique_rfid = f'RFID_{experiment.id}_{animal.animal_index}'
            RFIDAssignment.objects.get_or_create(
                rfid=unique_rfid,
                animal=animal,
                experiment=experiment,
                cage_number=None  # No cages if animals are directly assigned to the experiment
            )

@login_required
@require_POST
def finalize_experiment(request, org_id, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)

    # Ensure all steps are completed before finalizing
    if not (experiment.step_basic_info_completed and
            experiment.step_investigators_completed and
            experiment.step_metrics_completed and
            experiment.step_tasks_completed and
            experiment.step_groups_completed):
        return JsonResponse({'status': 'error', 'message': 'All steps must be completed before finalizing the experiment.'}, status=400)

    # Mark the experiment as finalized
    experiment.is_draft = False
    experiment.step_summary_completed = True
    experiment.save()

    return JsonResponse({'status': 'success', 'message': 'Experiment finalized successfully.'})

def add_experiment(request):
    if request.method == 'POST':
        # Fetch the user's organization
        organization = request.user.organization

        # Get form data from POST request
        name = request.POST['name']
        description = request.POST.get('description', '')
        start_date = request.POST.get('start_date', None)
        weight_schedule = request.POST.get('weight_schedule', 'no') == 'yes'
        weigh_in_interval = int(request.POST['weigh_in_interval']) if weight_schedule else None
        experiment_duration = int(request.POST['experiment_duration']) if weight_schedule else None

        # Create a new Experiment instance
        experiment = Experiment.objects.create(
            name=name,
            description=description,
            start_date=start_date,
            weigh_in_interval=weigh_in_interval,
            owner=request.user,
            duration=experiment_duration,
            weight_schedule=weight_schedule,
            organization=organization
        )

        # Redirect to the next step: adding groups and treatments
        return redirect('create_groups', org_id=organization.id, experiment_id=experiment.id)

    return render(request, 'new-experiment.html')

@login_required
def import_export_view(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    
    # Data required for export tab can be loaded here if necessary
    search_query = request.GET.get('search', '')
    sort_by = request.GET.get('sort_by', 'name')
    order = request.GET.get('order', 'asc')

    # Fetch experiments for export section (example query)
    experiments = Experiment.objects.filter(
        organization=organization, name__icontains=search_query
    ).order_by(sort_by if order == 'asc' else f'-{sort_by}')

    paginator = Paginator(experiments, 10)
    page_number = request.GET.get('page')
    experiments_page = paginator.get_page(page_number)

    context = {
        'org_id': org_id,
        'search_query': search_query,
        'sort_by': sort_by,
        'order': order,
        'experiments': experiments_page,
    }
    
    return render(request, 'import.html', context)
@login_required
def import_data(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)

    if request.method == 'POST':
        form = ImportForm(request.POST, request.FILES)

        if form.is_valid():
            files = request.FILES.getlist('import_file')  # Get multiple files
            archive_flag = request.POST.get('archive_experiment', 'no') == 'yes'

            if not files:
                return JsonResponse({
                    'status': 'error',
                    'message': 'No files uploaded. Please select at least one file.'
                }, status=400)

            bulk_upload_id = uuid.uuid4()  # Assign a unique ID for this bulk upload
            created_experiments = []
            error_messages = []
            uploaded_files = []  # Track uploaded file details

            for file in files:
                try:
                    # Generate an experiment name from the file name
                    experiment_name = os.path.splitext(file.name)[0]

                    # Process the file and create an experiment
                    experiment, preview_data = create_experiment_from_file(
                        file=file,
                        experiment_name=experiment_name,
                        archive_flag=archive_flag,
                        organization=organization,
                        user=request.user,
                        bulk_upload_id=bulk_upload_id
                    )

                    # Serialize datetime objects in preview_data
                    for row in preview_data:
                        for key, value in row.items():
                            if isinstance(value, datetime):
                                row[key] = value.isoformat()  # Convert datetime to ISO 8601 string

                    # Save preview data to session for single imports
                    request.session[f'import_preview_data_{experiment.id}'] = preview_data
                    created_experiments.append(experiment)
                    uploaded_files.append({'name': file.name, 'size': file.size})

                except Exception as e:
                    logger.exception(f"Error processing file {file.name}")
                    error_messages.append(f"File {file.name}: {str(e)}")

            if error_messages:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Some files could not be processed.',
                    'errors': error_messages
                }, status=400)

            # Generate the appropriate redirect URL
            if len(created_experiments) > 1:
                # Bulk import confirmation page
                redirect_url = reverse('experiment_confirmation_bulk', args=[org_id, bulk_upload_id])
            elif len(created_experiments) == 1:
                # Single experiment confirmation page
                request.session[f'import_errors_{created_experiments[0].id}'] = error_messages
                redirect_url = reverse('experiment_confirmation', args=[org_id, created_experiments[0].id])
            else:
                return JsonResponse({
                    'status': 'error',
                    'message': 'No experiments were created.'
                }, status=400)

            # Return JSON response with redirect URL
            return JsonResponse({'status': 'success', 'redirect_url': redirect_url})

        else:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid form submission. Please correct the errors and try again.'
            }, status=400)
    else:
        form = ImportForm()
    return render(request, 'import.html', {
        'form': form,
        'org_id': org_id,
        'upload_mode': 'single',  # Default upload mode for initial GET request
    })



def parse_rows_parallel(rows):
    with ThreadPoolExecutor(max_workers=4) as executor:
        return list(executor.map(parse_import_row, rows, range(len(rows))))
def create_experiment_from_file(file, experiment_name, archive_flag, organization, user, bulk_upload_id):
    csv_file = file.read().decode('utf-8').splitlines()
    reader = csv.DictReader(csv_file)

    # Normalize headers
    reader.fieldnames = [field.strip().lower() for field in reader.fieldnames]

    # Parse rows in parallel
    parsed_data_list_with_errors = parse_rows_parallel([row for row in reader])

    # Separate parsed data and errors
    parsed_data_list = []
    errors = []
    for parsed_data, row_errors in parsed_data_list_with_errors:
        if row_errors:
            errors.extend(row_errors)
        else:
            parsed_data_list.append(parsed_data)

    if errors:
        raise ValueError(f"Errors in the data: {errors}")

    # Calculate metadata for experiment creation
    animal_indices = set()
    cage_animals = defaultdict(int)
    groups_data = {}
    has_weight_data = False
    has_tumor_data = False

    for parsed_data in parsed_data_list:
        animal_indices.add(parsed_data.get('animal_index'))
        cage_animals[parsed_data.get('cage_number')] += 1
        group_name = parsed_data.get('group_name')
        if group_name:
            groups_data[group_name] = groups_data.get(group_name, 0) + 1
        if parsed_data.get('weight'):
            has_weight_data = True
        if parsed_data.get('tumor_size'):
            has_tumor_data = True

    # Create experiment
    experiment = Experiment.objects.create(
        name=experiment_name,
        organization=organization,
        owner=user,
        number_of_animals=len(animal_indices),
        max_per_cage=max(cage_animals.values(), default=0),
        number_of_groups=len(groups_data),
        archived=archive_flag,
        monitor_weight=has_weight_data,
        monitor_tumor=has_tumor_data,
        bulk_upload_id=bulk_upload_id,
    )
    if archive_flag:
        experiment.ended = True
        experiment.save()

    # Save parsed data in bulk
    save_import_rows_bulk(parsed_data_list, experiment, organization, user)

    # Return the experiment and parsed data for preview
    return experiment, parsed_data_list

def parse_import_row(row, row_number):
    """
    Parses a single row of the import file and validates the fields.
    """
    errors = []
    parsed_data = {}

    try:
        # Extract fields using normalized keys
        parsed_data['animal_index'] = row.get('animal index')
        parsed_data['cage_number'] = row.get('cage number')  # Match normalized 'cage number'
        if not parsed_data['cage_number']:
            errors.append(f"Row {row_number}: 'Cage Number' is missing.")

        # Parse weight and validate if numeric
        weight = row.get('weight')
        if weight:
            try:
                parsed_data['weight'] = float(weight)
            except ValueError:
                errors.append(f"Row {row_number}: 'Weight' is not a valid number.")
        else:
            parsed_data['weight'] = None

        # Parse tumor size and validate if numeric
        tumor_size = row.get('tumor size')
        if tumor_size:
            try:
                parsed_data['tumor_size'] = float(tumor_size)
            except ValueError:
                errors.append(f"Row {row_number}: 'Tumor Size' is not a valid number.")
        else:
            parsed_data['tumor_size'] = None

        parsed_data['timestamp'] = parse_timestamp(row.get('timestamp'), row_number)
        parsed_data['rfid'] = row.get('rfid')
        parsed_data['group_name'] = row.get('group name', '').strip()  # Clean and default to an empty string
        logger.info(f"Parsed group name: {parsed_data.get('group_name')}")
        if not parsed_data['group_name']:
            errors.append(f"Row {row_number}: 'Group Name' is missing.")

        # Optional fields
        parsed_data['sex'] = row.get('sex')
        parsed_data['species'] = row.get('species')
        parsed_data['tail'] = row.get('tail')
        parsed_data['ear'] = row.get('ear')
        parsed_data['tag'] = row.get('tag')
        parsed_data['donor'] = row.get('donor')
        parsed_data['sample_id'] = row.get('sample id')
        parsed_data['sample_type'] = row.get('sample type')
        parsed_data['drug_name'] = row.get('drug name')
        parsed_data['dose'] = row.get('dose')
        parsed_data['stock_concentration'] = row.get('stock concentration')  # Match exact header
        parsed_data['dose_volume'] = row.get('dose volume')
        parsed_data['category'] = row.get('category')
        parsed_data['score'] = row.get('score')

    except Exception as e:
        errors.append(f"Row {row_number}: Error parsing row - {e}")

    return parsed_data, errors

def parse_timestamp(timestamp_str, row_number):
    """
    Parses a timestamp string into a timezone-aware datetime object.
    Supports multiple formats for flexibility.
    """
    try:
        if timestamp_str:
            # Try parsing with different formats
            for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%Y-%m-%d %H:%M:%S'):
                try:
                    parsed_time = datetime.strptime(timestamp_str, fmt)
                    return timezone.make_aware(parsed_time)
                except ValueError:
                    continue
            # If none of the formats match, raise an error
            raise ValueError(f"Invalid timestamp format '{timestamp_str}'.")
        return None
    except ValueError as e:
        raise ValueError(f"Row {row_number}: {e}")
def save_import_row(parsed_data, experiment, organization, user):
    """
    Saves a single row of parsed data into the database while ensuring groups, cages,
    treatments, RFIDs, and doses are correctly assigned and not duplicated.
    """
    try:
        # Validate and assign group name
        group_name = parsed_data.get('group_name', '').strip()
        if not group_name:
            raise ValueError("Group name is missing in the imported data.")

        # Retrieve or create the group
        group, group_created = Group.objects.get_or_create(
            experiment=experiment,
            name=group_name,
            defaults={
                'color': '#{:06x}'.format(random.randint(0, 0xFFFFFF)),  # Random color for new groups
                'number_of_animals': 0,
            },
        )

        # Associate treatment with the group, ensuring no duplicates
        if parsed_data.get('drug_name'):
            treatment_filters = {
                'experiment': experiment,
                'drug_name': parsed_data['drug_name'],
                'dose': parsed_data.get('dose'),
                'dose_volume': parsed_data.get('dose_volume'),
                'stock_concentration': parsed_data.get('stock_concentration'),
            }

            try:
                # Attempt to retrieve a unique treatment
                treatment = Treatment.objects.get(**treatment_filters)
            except Treatment.DoesNotExist:
                # Create the treatment if it doesn't exist
                treatment = Treatment.objects.create(
                    experiment=experiment,
                    drug_name=parsed_data['drug_name'],
                    dose=parsed_data.get('dose'),
                    dose_volume=parsed_data.get('dose_volume'),
                    stock_concentration=parsed_data.get('stock_concentration'),
                    created_by=user,
                )
            except Treatment.MultipleObjectsReturned:
                # Handle duplicate treatments
                logger.warning(
                    f"Multiple treatments found for filters: {treatment_filters}. Using the first one."
                )
                treatment = Treatment.objects.filter(**treatment_filters).first()

            # Assign treatment to the group if not already assigned
            if group.treatment != treatment:
                group.treatment = treatment
                group.save()

        # Add animal to the group
        animal, animal_created = Animal.objects.get_or_create(
            experiment=experiment,
            animal_index=parsed_data['animal_index'],
            defaults={
                'organization': organization,
                'sex': parsed_data.get('sex'),
                'species': parsed_data.get('species'),
                'tail': parsed_data.get('tail'),
                'ear': parsed_data.get('ear'),
                'tag': parsed_data.get('tag'),
                'donor': parsed_data.get('donor'),
                'group': group,
            },
        )
        if animal_created:
            group.number_of_animals += 1
            group.save()

        # Assign RFID to the animal if provided
        if parsed_data.get('rfid') and animal.rfid_tag != parsed_data.get('rfid'):
            animal.rfid_tag = parsed_data['rfid']
            animal.save()

        # Create or update RFIDAssignment if applicable
        if parsed_data.get('rfid'):
            RFIDAssignment.objects.update_or_create(
                animal=animal,
                experiment=experiment,
                defaults={
                    'rfid': parsed_data['rfid'],
                    'cage_number': parsed_data['cage_number'],
                },
            )

        # Assign the animal to a cage
        cage, _ = Cage.objects.get_or_create(
            experiment=experiment,
            cage_number=parsed_data.get('cage_number'),
            organization=organization,
            defaults={'name': f"Cage {parsed_data['cage_number']}", 'capacity': 4},
        )
        if animal.cage != cage:
            animal.cage = cage
            animal.save()

        # Create or update weight and tumor size measurements
        monitor_weight, monitor_tumor = False, False
        if parsed_data.get('weight') is not None:
            monitor_weight = True  # Activate weight monitoring if weight data exists
            WeightMeasurement.objects.update_or_create(
                animal=animal,
                timestamp=parsed_data.get('timestamp'),
                defaults={'weight': parsed_data['weight'], 'recorder': user},
            )

        if parsed_data.get('tumor_size') is not None:
            monitor_tumor = True  # Activate tumor monitoring if tumor size data exists
            WeightMeasurement.objects.update_or_create(
                animal=animal,
                timestamp=parsed_data.get('timestamp'),
                defaults={'tumor_size': parsed_data.get('tumor_size'), 'recorder': user},
            )

        # Update experiment monitoring flags if necessary
        if monitor_weight and not experiment.monitor_weight:
            experiment.monitor_weight = True
        if monitor_tumor and not experiment.monitor_tumor:
            experiment.monitor_tumor = True
        experiment.save()

        # Create or update the dose for the animal
        if parsed_data.get('drug_name'):
            Dose.objects.update_or_create(
                animal=animal,
                experiment=experiment,
                drug_name=parsed_data['drug_name'],
                dose=parsed_data.get('dose'),
                defaults={
                    'stock_concentration': parsed_data.get('stock_concentration'),
                    'dose_volume': parsed_data.get('dose_volume'),
                    'user': user,  # Logged-in user as the creator of the dose
                    'timestamp': parsed_data.get('timestamp'),
                },
            )

    except Exception as e:
        logger.exception("Error saving import row")
        raise ValueError(f"Error saving row for animal {parsed_data.get('animal_index')}: {e}")

def save_import_rows_bulk(parsed_data_list, experiment, organization, user):
    animals = []
    measurements = []
    treatments = []

    # Preload existing animals, groups, and cages into memory for quick lookups
    existing_animal_indices = set(
        Animal.objects.filter(organization=organization).values_list("animal_index", flat=True)
    )
    new_animal_indices = set()

    existing_groups = {
        group.name: group
        for group in Group.objects.filter(experiment=experiment)
    }
    existing_cages = {
        cage.cage_number: cage
        for cage in Cage.objects.filter(experiment=experiment)
    }

    new_groups = {}
    new_cages = {}

    # Temporary storage for linking measurements to animals
    animal_mapping = {}

    with transaction.atomic():  # Ensure atomic operations
        for parsed_data in parsed_data_list:
            animal_index = parsed_data.get('animal_index')

            # Check for duplicates
            if animal_index in existing_animal_indices or animal_index in new_animal_indices:
                logger.warning(f"Duplicate animal_index {animal_index} detected. Skipping.")
                continue
            new_animal_indices.add(animal_index)

            # Retrieve or create group
            group_name = parsed_data.get('group_name', '').strip()
            if group_name in existing_groups:
                group = existing_groups[group_name]
            elif group_name in new_groups:
                group = new_groups[group_name]
            else:
                group = Group(
                    experiment=experiment,
                    name=group_name,
                    color='#{:06x}'.format(random.randint(0, 0xFFFFFF)),  # Random color
                    number_of_animals=0,
                )
                new_groups[group_name] = group

            # Retrieve or create cage
            cage_number = parsed_data.get('cage_number', 'Unknown')
            if cage_number in existing_cages:
                cage = existing_cages[cage_number]
            elif cage_number in new_cages:
                cage = new_cages[cage_number]
            else:
                cage = Cage(
                    experiment=experiment,
                    cage_number=cage_number,
                    organization=organization,
                    name=f"Cage {cage_number}",
                    capacity=4,
                )
                new_cages[cage_number] = cage

            # Create the Animal object and add it to the mapping
            animal = Animal(
                experiment=experiment,
                organization=organization,
                animal_index=animal_index,
                sex=parsed_data.get('sex'),
                species=parsed_data.get('species'),
                tail=parsed_data.get('tail'),
                ear=parsed_data.get('ear'),
                tag=parsed_data.get('tag'),
                donor=parsed_data.get('donor'),
                group=group,
                cage=cage,
            )
            animals.append(animal)
            animal_mapping[animal_index] = animal

            # Create treatments
            if parsed_data.get('drug_name'):
                treatments.append(
                    Treatment(
                        experiment=experiment,
                        drug_name=parsed_data['drug_name'],
                        dose=parsed_data.get('dose'),
                        stock_concentration=parsed_data.get('stock_concentration'),
                        dose_volume=parsed_data.get('dose_volume'),
                        created_by=user,
                    )
                )

        # Bulk create new groups, cages, and animals
        created_groups = Group.objects.bulk_create(new_groups.values())
        created_cages = Cage.objects.bulk_create(new_cages.values())
        created_animals = Animal.objects.bulk_create(animals)

        # Update the `animal_mapping` with database IDs
        for animal in created_animals:
            animal_mapping[animal.animal_index] = animal

        # Create weight measurements linked to animals
        for parsed_data in parsed_data_list:
            animal_index = parsed_data.get('animal_index')
            animal = animal_mapping.get(animal_index)

            if not animal:
                continue  # Skip if the animal was not created (e.g., duplicate)

            if parsed_data.get('weight') is not None:
                measurements.append(
                    WeightMeasurement(
                        animal=animal,  # Link the animal here
                        timestamp=parsed_data.get('timestamp'),
                        weight=parsed_data['weight'],
                        recorder=user,
                    )
                )

        # Bulk insert treatments and measurements
        WeightMeasurement.objects.bulk_create(measurements)
        Treatment.objects.bulk_create(treatments)

@login_required
def experiment_confirmation(request, org_id, experiment_id=None, bulk_upload_id=None):
    organization = get_object_or_404(Organization, id=org_id)

    # Retrieve experiments
    experiments = []
    if bulk_upload_id:
        experiments = Experiment.objects.filter(
            organization=organization,
            bulk_upload_id=bulk_upload_id
        ).order_by('created_at')
    elif experiment_id:
        experiment = get_object_or_404(Experiment, id=experiment_id, organization=organization)
        experiments = [experiment]

    if not experiments:
        return render(
            request,
            'experiment_confirmation.html',
            {
                'org_id': org_id,
                'errors': ['No experiments found for confirmation.'],
                'data_to_preview': [],
            },
        )

    is_bulk_import = len(experiments) > 1
    preview_data = []
    errors = []
    cage_distribution = {}
    unique_animals = set()

    for experiment in experiments:
        # Retrieve preview data
        data_to_preview = request.session.get(f'import_preview_data_{experiment.id}', [])
        experiment_errors = request.session.get(f'import_errors_{experiment.id}', [])

        # Process data for summary
        for row in data_to_preview:
            cage_number = row.get("cage_number", "Unknown")
            cage_distribution[cage_number] = cage_distribution.get(cage_number, 0) + 1
            unique_animals.add(row.get("animal_index", "Unknown"))

        preview_data.append({
            "experiment": experiment,
            "data": data_to_preview,
            "errors": experiment_errors,
        })

    # Flatten data for single experiment
    if not is_bulk_import and preview_data:
        data_to_preview = preview_data[0]["data"]
        errors = preview_data[0]["errors"]

    return render(
        request,
        "experiment_confirmation.html",
        {
            "org_id": org_id,
            "data_to_preview": data_to_preview,
            "errors": errors,
            "experiment_name": experiments[0].name if experiments else "Unknown",
            "cage_distribution": cage_distribution,
            "unique_animal_count": len(unique_animals),
            "displayed_fields": data_to_preview[0].keys() if data_to_preview else [],
            "is_bulk_import": is_bulk_import,
            "bulk_upload_id": bulk_upload_id if is_bulk_import else None,
            "experiment_id": experiment_id if not is_bulk_import else None,
            "experiments": experiments,
        },
    )
@login_required
def finalize_import(request, org_id, experiment_id=None):
    """
    Finalizes the import process for both single and bulk experiments.
    Processes and saves all parsed rows into the database for each experiment.
    """
    organization = get_object_or_404(Organization, id=org_id)

    if request.method == 'POST':
        bulk_upload_id = request.POST.get('bulk_upload_id', None)

        # Determine single or bulk import
        if experiment_id:
            experiments = [get_object_or_404(Experiment, id=experiment_id, organization=organization)]
        elif bulk_upload_id:
            experiments = Experiment.objects.filter(
                organization=organization,
                bulk_upload_id=bulk_upload_id
            ).order_by('created_at')
        else:
            return JsonResponse({'status': 'error', 'message': 'No experiment or bulk upload ID provided.'})

        if not experiments:
            return JsonResponse({'status': 'error', 'message': 'No experiments found.'})

        try:
            # Process and save data for each experiment
            for experiment in experiments:
                data_to_preview = request.session.get(f'import_preview_data_{experiment.id}', [])
                if not data_to_preview:
                    continue

                # Save each row of data
                for row in data_to_preview:
                    save_import_row(row, experiment, organization, request.user)

                # Update experiment metadata
                experiment.number_of_groups = Group.objects.filter(experiment=experiment).count()
                experiment.number_of_animals = Animal.objects.filter(experiment=experiment).distinct().count()

                if experiment.archived:
                    experiment.ended = True

                experiment.save()

                # Clear session data
                request.session.pop(f'import_preview_data_{experiment.id}', None)
                request.session.pop(f'import_errors_{experiment.id}', None)

            # Redirect to appropriate page
            if bulk_upload_id:
                return redirect('all_experiments', org_id=org_id)
            else:
                single_experiment = experiments[0]
                if single_experiment.archived:
                    return redirect('all_experiments', org_id=org_id)
                else:
                    return redirect('experiment_home', org_id=org_id, experiment_id=single_experiment.id)

        except Exception as e:
            logger.exception("Error finalizing import")
            return JsonResponse({'status': 'error', 'message': str(e)})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})

@login_required
def finalize_import_bulk(request, org_id):
    """
    Finalizes the bulk import process.
    Processes and saves all parsed rows into the database for multiple experiments.
    """
    organization = get_object_or_404(Organization, id=org_id)

    if request.method == 'POST':
        # Get the bulk upload ID from the POST data
        bulk_upload_id = request.POST.get('bulk_upload_id', None)

        if not bulk_upload_id:
            return JsonResponse({'status': 'error', 'message': 'Bulk upload ID is required for bulk finalization.'})

        # Retrieve all experiments linked to the bulk upload ID
        experiments = Experiment.objects.filter(
            organization=organization,
            bulk_upload_id=bulk_upload_id
        ).order_by('created_at')

        if not experiments:
            return JsonResponse({'status': 'error', 'message': 'No experiments found for the provided bulk upload ID.'})

        try:
            # Process and save data for each experiment
            for experiment in experiments:
                # Retrieve preview data from the session
                data_to_preview = request.session.get(f'import_preview_data_{experiment.id}', [])
                if not data_to_preview:
                    continue

                # Save each row of data
                for row in data_to_preview:
                    save_import_row(row, experiment, organization, request.user)

                # Update experiment metadata
                experiment.number_of_groups = Group.objects.filter(experiment=experiment).count()
                experiment.number_of_animals = Animal.objects.filter(experiment=experiment).distinct().count()

                # Mark the experiment as ended if archived
                if experiment.archived:
                    experiment.ended = True

                experiment.save()

                # Clear session data for the experiment
                request.session.pop(f'import_preview_data_{experiment.id}', None)
                request.session.pop(f'import_errors_{experiment.id}', None)

            # Redirect to the all experiments page after successful bulk finalization
            return redirect('all_experiments', org_id=org_id)

        except Exception as e:
            logger.exception("Error finalizing bulk import")
            return JsonResponse({'status': 'error', 'message': str(e)})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})

@login_required
def generate_csv_for_experiment(request, experiment):
    if experiment.organization != request.user.organization:
        return HttpResponseForbidden("You do not have permission to access this data.")

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="experiment_{experiment.id}_data.csv"'
    writer = csv.writer(response)

    # Write CSV headers
    writer.writerow([
        'Animal Index', 'Group', 'Sex', 'Species', 'Strain',
        'Weight (g)', 'Tumor Size (mm³)', 'Weight Change (%)',
        'Tumor Growth Rate (mm³/day)', 'Doses', 'Observations', 'Timestamp'
    ])

    # Fetch animals and related data
    animals = Animal.objects.filter(experiment=experiment).select_related('group').prefetch_related('strains', 'treatments', 'observations')
    measurements = WeightMeasurement.objects.filter(
        rfid_assignment__animal__experiment=experiment
    ).select_related('rfid_assignment__animal').order_by('rfid_assignment__animal__animal_index', 'timestamp')

    # Group measurements by Animal Index
    animal_measurements = {}
    for measurement in measurements:
        animal = measurement.rfid_assignment.animal
        if animal.animal_index not in animal_measurements:
            animal_measurements[animal.animal_index] = []
        animal_measurements[animal.animal_index].append(measurement)

    # Merge weight and tumor size by matching timestamps
    for animal_index, measurements in animal_measurements.items():
        combined_data = []
        weight_measurements = [m for m in measurements if m.weight is not None]
        tumor_measurements = [m for m in measurements if m.tumor_size is not None]

        # Pair weight and tumor size measurements by closest timestamps
        while weight_measurements or tumor_measurements:
            if weight_measurements and tumor_measurements:
                # Find the closest match between weight and tumor size
                weight_measurement = weight_measurements[0]
                closest_tumor_measurement = min(
                    tumor_measurements,
                    key=lambda t: abs((t.timestamp - weight_measurement.timestamp).total_seconds())
                )

                time_diff = abs((closest_tumor_measurement.timestamp - weight_measurement.timestamp).total_seconds())

                if time_diff <= 60:  # Allow a tolerance of 60 seconds
                    combined_data.append({
                        'timestamp': weight_measurement.timestamp,
                        'weight': weight_measurement.weight,
                        'tumor_size': closest_tumor_measurement.tumor_size
                    })
                    weight_measurements.pop(0)
                    tumor_measurements.remove(closest_tumor_measurement)
                else:
                    combined_data.append({
                        'timestamp': weight_measurement.timestamp,
                        'weight': weight_measurement.weight,
                        'tumor_size': None
                    })
                    weight_measurements.pop(0)
            elif weight_measurements:
                weight_measurement = weight_measurements.pop(0)
                combined_data.append({
                    'timestamp': weight_measurement.timestamp,
                    'weight': weight_measurement.weight,
                    'tumor_size': None
                })
            elif tumor_measurements:
                tumor_measurement = tumor_measurements.pop(0)
                combined_data.append({
                    'timestamp': tumor_measurement.timestamp,
                    'weight': None,
                    'tumor_size': tumor_measurement.tumor_size
                })

        # Write rows for the animal
        for data in combined_data:
            animal = measurements[0].rfid_assignment.animal
            writer.writerow([
                animal.animal_index,
                animal.group.name if animal.group else 'N/A',
                animal.sex,
                animal.species,
                ', '.join(strain.name for strain in animal.strains.all()),
                data['weight'] if data['weight'] is not None else 'N/A',
                data['tumor_size'] if data['tumor_size'] is not None else 'N/A',
                'N/A',  # Weight Change (can be added if required)
                'N/A',  # Tumor Growth Rate (can be added if required)
                ', '.join(f"{treatment.drug_name} ({treatment.dose} mg)" for treatment in animal.treatments.all()),
                ', '.join(f"{obs.category} (Score: {obs.score})" for obs in animal.observations.all()),
                data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            ])

    return response

@login_required
def export_data(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    user = request.user

    if user.organization != organization:
        return HttpResponseForbidden("You are not allowed to export data for this organization.")

    search_query = request.GET.get('search', '')
    sort_by = request.GET.get('sort_by', 'name')
    order = request.GET.get('order', 'asc')

    experiments = Experiment.objects.filter(
        Q(owner=user) | Q(collaborators__user=user),
        name__icontains=search_query,
        organization=organization
    ).distinct()

    experiments = experiments.order_by(sort_by if order == 'asc' else f'-{sort_by}')

    paginator = Paginator(experiments, 10)
    page_number = request.GET.get('page')
    experiments_page = paginator.get_page(page_number)

    if request.method == 'POST':
        experiment_id = request.POST.get('experiment')
        experiment = get_object_or_404(Experiment, id=experiment_id, organization=organization)


        try:
            return generate_csv_for_experiment(request, experiment)
        except Exception as e:
            logger.error(f"Error exporting data for experiment {experiment.id}: {str(e)}", exc_info=True)
            return HttpResponseServerError("An error occurred while generating the CSV file.")

    return render(request, 'export.html', {
        'experiments': experiments_page,
        'search_query': search_query,
        'sort_by': sort_by,
        'order': order,
        'org_id': org_id
    })

@login_required
def collaborators(request, org_id, experiment_id):
    # Get the experiment only if it belongs to the user's organization
    experiment = get_object_or_404(Experiment, pk=experiment_id, organization=request.user.organization)
    
    # Fetch collaborators for the experiment within the same organization
    collaborators = Collaborator.objects.filter(experiment=experiment, user__organization=request.user.organization)

    context = {
        'experiment': experiment,
        'collaborators': collaborators,
    }
    return render(request, 'collaborators.html', context)
    
