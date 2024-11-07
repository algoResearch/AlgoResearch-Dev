from django.contrib import messages 
from django.contrib import messages as django_messages
from django.core import serializers
from django.shortcuts import render, redirect, get_object_or_404
import re
import calendar
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden, HttpResponseBadRequest, HttpResponseServerError
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
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

@login_required
def create_experiment(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)  # Ensure correct organization context
    if request.method == 'POST':
        # Extract experiment data
        name = request.POST.get('name', '')
        number_of_animals = int(request.POST.get('number_of_animals', 0))
        number_of_groups = int(request.POST.get('number_of_groups', 0))
        max_per_cage = int(request.POST.get('max_per_cage', 0))
        investigators_data = request.POST.get('investigators', '[]')
        drug_data = request.POST.get('drugs', '[]')
        strain_data = request.POST.get('strains', '[]')
        rfid_required = request.POST.get('rfid_required') == '1'

        # Weight and tumor size measurements
        measure_weight = request.POST.get('measure_weight') == 'on'
        measure_tumor_size = request.POST.get('measure_tumor_size') == 'on'

        # Weight schedule fields
        weight_schedule = request.POST.get('weight_schedule', 'no') if measure_weight else None
        weigh_in_interval = int(request.POST.get('weigh_in_interval', 0)) if measure_weight and weight_schedule == 'yes' else None
        experiment_duration = int(request.POST.get('experiment_duration', 0)) if measure_weight and weight_schedule == 'yes' else None

        # Tumor schedule fields
        tumor_schedule = request.POST.get('tumor_schedule', 'no') if measure_tumor_size else None
        tumor_measurement_interval = int(request.POST.get('tumor_measurement_interval', 0)) if measure_tumor_size and tumor_schedule == 'yes' else None
        tumor_duration = int(request.POST.get('tumor_duration', 0)) if measure_tumor_size and tumor_schedule == 'yes' else None

        # Create the Experiment object
        experiment = Experiment.objects.create(
            name=name,
            number_of_animals=number_of_animals,
            number_of_groups=number_of_groups,
            rfid_required=rfid_required,
            max_per_cage=max_per_cage,
            weigh_in_interval=weigh_in_interval,
            duration=experiment_duration,
            tumor_measurement_interval=tumor_measurement_interval,
            tumor_duration=tumor_duration,
            owner=request.user,
            monitor_weight=measure_weight,
            monitor_tumor=measure_tumor_size,
            organization=organization  # Add the organization field
        )

        # Assign animals to cages after the experiment is created
        assign_animals_to_cages(experiment, number_of_animals, max_per_cage)

        # Process and assign drugs to the experiment
        try:
            drugs = json.loads(drug_data)
            for drug in drugs:
                Drug.objects.create(name=drug, experiment=experiment)
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid drugs data format.'})

        # Process and assign strains to the experiment
        try:
            strains = json.loads(strain_data)
            for strain in strains:
                Strain.objects.create(name=strain, experiment=experiment)
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid strains data format.'})

        # Process investigator data and ensure they belong to the same organization
        try:
            investigators = json.loads(investigators_data)
            for investigator in investigators:
                user = get_object_or_404(User, username=investigator.get('username'), organization=organization)  # Ensure user is in the same organization
                role = investigator.get('role')

                # Create collaborator
                Collaborator.objects.create(
                    experiment=experiment,
                    user=user,
                    role=role
                )

                # Send notification to the user's inbox
                notification_message = f"You have been added to the experiment '{experiment.name}' as a {role}."
                InboxNotification.objects.create(
                    user=user,
                    experiment=experiment,
                    message=notification_message,
                    is_read=False  # Mark as unread by default
                )

                # Add the experiment events to the investigator's calendar
                add_events_to_calendar(user, experiment, organization, weight_schedule, weigh_in_interval, experiment_duration, tumor_schedule, tumor_measurement_interval, tumor_duration)

        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid investigators data format.'})

        # Add the experiment events to the owner's calendar
        add_events_to_calendar(request.user, experiment, organization, weight_schedule, weigh_in_interval, experiment_duration, tumor_schedule, tumor_measurement_interval, tumor_duration)

        # Add tasks based on the experiment settings
        tasks = []
        if rfid_required:
            tasks.append(Task(experiment=experiment, title="Assign RFID Values", description="Assign RFID values to all animals."))

        if measure_weight:
            tasks.append(Task(experiment=experiment, title="Take Initial Weight", description="Take the initial weight of all animals."))

        if measure_tumor_size:
            tasks.append(Task(experiment=experiment, title="Take Initial Tumor Size", description="Take the initial tumor size measurements."))

        # Save tasks in bulk
        Task.objects.bulk_create(tasks)

        return JsonResponse({'status': 'success', 'experiment_id': experiment.id})

    return render(request, 'new-experiment.html', {'org_id': org_id})

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
def experiment_basic_info(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    
    if request.method == 'POST':
        # Get the form data
        name = request.POST.get('name')
        description = request.POST.get('description')
        start_date = request.POST.get('start_date')
        
        # Create a new experiment instance
        experiment = Experiment.objects.create(
            name=name,
            description=description,
            start_date=start_date,
            organization=organization,
            owner=request.user  # Ensure the current user is set as the owner
        )
        experiment.step_basic_info_completed = True
        experiment.save()
        
        
        # Redirect to the Add Investigators step after saving the experiment
        return redirect('add_investigators', org_id=org_id, experiment_id=experiment.id)

    today = timezone.now().date()
    return render(request, 'experiment_basic_info.html', {'org_id': org_id, 'today': today})
@login_required
def add_investigators(request, org_id, experiment_id):
    organization = get_object_or_404(Organization, id=org_id)
    experiment = get_object_or_404(Experiment, id=experiment_id)

    if request.method == 'POST':
        # Get the selected investigators from the POST request
        selected_investigators = json.loads(request.POST.get('selected_investigators', '[]'))

        # If no investigators are selected, allow the user to proceed without an error
        if not selected_investigators:
            # Log a message (optional)
            print(f"No investigators selected for experiment {experiment.name} (ID: {experiment_id})")

            # Save the experiment and move on to the next step
            experiment.step_summary_completed = True
            experiment.save()

            return JsonResponse({'status': 'success', 'message': 'No investigators selected, proceeding to next step.'})

        # Find users and ensure they belong to the same organization
        investigators = User.objects.filter(username__in=selected_investigators, organization=organization)

        if investigators.exists():
            # Convert the queryset of investigators to a list of usernames
            investigator_usernames = list(investigators.values_list('username', flat=True))

            # Log the investigators being added to the experiment
            print(f"Adding investigators to experiment {experiment.name}: {investigator_usernames}")

            # Add the investigators to the experiment
            experiment.investigators = json.dumps(investigator_usernames)
            experiment.step_summary_completed = True  # Update the experiment's step completion status
            experiment.save()

            return JsonResponse({'status': 'success', 'message': 'Investigators added successfully'})
        else:
            return JsonResponse({'status': 'error', 'message': 'No valid investigators found in the organization.'})

    # GET request: Display the list of users in the same organization
    users = User.objects.filter(organization=organization).exclude(id=request.user.id)

    return render(request, 'add_investigators.html', {
        'users': users,
        'org_id': org_id,
        'experiment_id': experiment_id,
    })
@login_required
def search_organization_users(request, org_id):
    """
    View to fetch and return users belonging to the same organization.
    Allows searching based on username or full name.
    """
    query = request.GET.get('query', '')
    organization = request.user.organization

    users = User.objects.filter(
        Q(organization=organization) & 
        (Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains(query)))
    ).exclude(id=request.user.id)  # Exclude the current user

    user_data = []
    for user in users:
        user_data.append({
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'profile_picture': user.profile_picture.url if user.profile_picture else None
        })

    return JsonResponse({'users': user_data})


@login_required
def experiment_metrics(request, org_id, experiment_id):
    # Fetch the experiment and ensure it belongs to the organization
    experiment = get_object_or_404(Experiment, id=experiment_id, organization__id=org_id)
    logger.info(f"Experiment Metrics POST request received for experiment: {experiment.name} (ID: {experiment_id})")

    # Fetch all investigators for the experiment (owner and selected investigators)
    investigators = [experiment.owner]
    if experiment.investigators:
        investigators += list(User.objects.filter(username__in=json.loads(experiment.investigators)))
    logger.info(f"Investigators for experiment {experiment.name}: {[user.username for user in investigators]}")

    if request.method == 'POST':
        logger.info("Processing form data for weight and tumor metrics...")

        # Determine which metrics are being monitored
        monitor_weight = request.POST.get('monitor_weight') == 'yes'
        monitor_tumor = request.POST.get('monitor_tumor') == 'yes'
        logger.info(f"Monitor Weight: {monitor_weight}, Monitor Tumor Size: {monitor_tumor}")

        # Process weight metrics if weight monitoring is enabled
        warning_weight_percentage = float(request.POST.get('warning_weight_percentage', 0)) if monitor_weight else None
        removal_weight_percentage = float(request.POST.get('removal_weight_percentage', 0)) if monitor_weight else None

        # Custom scheduling for weight monitoring
        weight_schedule_days = request.POST.getlist('weight_schedule_days') if monitor_weight else []
        weight_schedule_weeks = int(request.POST.get('weight_schedule_weeks', 0)) if monitor_weight else 0

        # Process tumor metrics if tumor monitoring is enabled
        tumor_volume_warning = float(request.POST.get('tumor_volume_warning', 0)) if monitor_tumor else None
        tumor_volume_removal = float(request.POST.get('tumor_volume_removal', 0)) if monitor_tumor else None

        # Custom scheduling for tumor monitoring
        tumor_schedule_days = request.POST.getlist('tumor_schedule_days') if monitor_tumor else []
        tumor_schedule_weeks = int(request.POST.get('tumor_schedule_weeks', 0)) if monitor_tumor else 0

        # Save the metrics to the experiment instance
        experiment.monitor_weight = monitor_weight
        experiment.warning_weight_percentage = warning_weight_percentage
        experiment.removal_weight_percentage = removal_weight_percentage

        experiment.monitor_tumor = monitor_tumor
        experiment.tumor_volume_warning = tumor_volume_warning
        experiment.tumor_volume_removal = tumor_volume_removal

        experiment.save()
        logger.info(f"Experiment {experiment.name} metrics saved.")

        # Clear existing calendar events related to this experiment
        deleted_count, _ = CalendarEvent.objects.filter(experiment=experiment).delete()
        logger.info(f"Cleared {deleted_count} existing calendar events for experiment {experiment.name}")

        # Schedule weight monitoring events if applicable
        if monitor_weight and weight_schedule_days and weight_schedule_weeks > 0:
            logger.info(f"Scheduling weight monitoring events for {experiment.name}")
            schedule_events_for_days(
                start_date=date.today(),
                days=weight_schedule_days,
                weeks=weight_schedule_weeks,
                experiment=experiment,
                investigators=investigators,
                event_type='weight'
            )

        # Schedule tumor monitoring events if applicable
        if monitor_tumor and tumor_schedule_days and tumor_schedule_weeks > 0:
            logger.info(f"Scheduling tumor monitoring events for {experiment.name}")
            schedule_events_for_days(
                start_date=date.today(),
                days=tumor_schedule_days,
                weeks=tumor_schedule_weeks,
                experiment=experiment,
                investigators=investigators,
                event_type='tumor'
            )

        # Mark this step as completed for the experiment
        experiment.step_metrics_completed = True
        experiment.save()
        logger.info(f"Experiment {experiment.name} metrics step completed.")

        # Redirect to the next step in the experiment setup process
        return redirect('task_schedules', org_id=org_id, experiment_id=experiment_id)

    return render(request, 'experiment_metrics.html', {'org_id': org_id, 'experiment_id': experiment_id})

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

    # Check if the investigators field is None or empty
    if experiment.investigators:
        selected_investigators = json.loads(experiment.investigators)
    else:
        selected_investigators = []

    members = set([experiment.owner])  # Start with the experiment owner

    # Add investigators to members if any were selected
    if selected_investigators:
        for username in selected_investigators:
            user = User.objects.filter(username=username, organization=request.user.organization).first()
            if user:
                members.add(user)
    
    members = list(members)  # Convert the set to a list

    if request.method == 'POST':
        data = json.loads(request.body)
        tasks = data.get('tasks', [])

        if not tasks:
            return JsonResponse({'status': 'error', 'message': 'No tasks provided.'}, status=400)

        for task in tasks:
            title = task.get('title')
            description = task.get('description')
            frequency = int(task.get('frequency', 0))
            duration = int(task.get('duration', 0))
            assignee_ids = task.get('assignees', [])

            if not title or not description or not frequency or not duration:
                return JsonResponse({'status': 'error', 'message': 'All fields are required for each task.'}, status=400)

            # Fetch the assigned users
            if not assignee_ids:
                assignees = members  # Assign to all investigators and owner if none are specified
            else:
                assignees = User.objects.filter(id__in=assignee_ids)

            # Save the task to the Task model
            new_task = Task.objects.create(
                title=title,
                description=description,
                frequency=frequency,
                duration=duration,
                experiment=experiment,
                assigned_by=request.user
            )
            new_task.assignees.set(assignees)

            # Schedule task events
            for assignee in assignees:
                current_date = timezone.now().date()
                end_date = current_date + timedelta(days=duration)

                while current_date <= end_date:
                    CalendarEvent.objects.create(
                        user=assignee,
                        organization_id=org_id,
                        title=title,
                        description=description,
                        start_date=current_date,
                        end_date=current_date,
                        experiment=experiment
                    )
                    current_date += timedelta(days=frequency)

        return JsonResponse({'status': 'success', 'message': 'Tasks scheduled successfully.'})

    # Fetch the existing tasks to display
    tasks = Task.objects.filter(experiment=experiment).prefetch_related('assignees')

    return render(request, 'task_schedules.html', {
        'org_id': org_id,
        'experiment_id': experiment_id,
        'investigators': members,
        'tasks': tasks,
    })
def create_groups(request, org_id, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)

    # Query only animals that are not assigned to an experiment and are available
    available_animals = Animal.objects.filter(
        organization_id=org_id,
        experiment__isnull=True,  # Only animals not yet assigned to an experiment
        is_available=True
    )

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            group_name = data.get('group_name')
            group_color = data.get('group_color')
            selected_animal_ids = data.get('selected_animals', [])

            if group_name and group_color:
                # Create the group
                group = Group.objects.create(
                    name=group_name,
                    color=group_color,
                    number_of_animals=len(selected_animal_ids),
                    experiment=experiment
                )

                # Fetch the selected animals
                animals_to_add = Animal.objects.filter(
                    id__in=selected_animal_ids,
                    organization=experiment.organization,
                    is_available=True,
                    experiment__isnull=True
                )

                # Mark each selected animal as part of the group
                for animal in animals_to_add:
                    animal.group = group
                    animal.experiment = experiment
                    animal.is_available = False  # Mark as unavailable in the Vivarium
                    animal.save()

                return JsonResponse({'status': 'success', 'group_id': group.id})
            else:
                return JsonResponse({'status': 'error', 'message': 'Group name or color missing'})

        except Exception as e:
            print("Error creating group:", e)
            return HttpResponseServerError("An error occurred while creating the group.")

    # Handle GET request to render the 'groups.html' page with context data
    groups = Group.objects.filter(experiment=experiment)
    context = {
        'experiment': experiment,
        'groups': groups,
        'available_animals': available_animals,  # Pass available animals to context
        'org_id': org_id,
        'experiment_id': experiment_id
    }
    return render(request, 'groups.html', context)

@login_required
def add_group(request, org_id, experiment_id):
    if request.method == 'POST':
        experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)
        data = json.loads(request.body)

        group_name = data.get('group_name')
        group_color = data.get('group_color')
        selected_animal_ids = data.get('selected_animals', [])

        if group_name and group_color and selected_animal_ids:
            # Create the group
            group = Group.objects.create(
                name=group_name,
                color=group_color,
                number_of_animals=len(selected_animal_ids),
                experiment=experiment
            )

            # Fetch the selected animals
            animals_to_add = Animal.objects.filter(
                id__in=selected_animal_ids,
                organization=experiment.organization,
                is_available=True,
                experiment__isnull=True
            )

            for animal in animals_to_add:
                # Link the animal to the experiment
                animal.group = group
                animal.experiment = experiment
                animal.is_available = False  # Mark as unavailable in the Vivarium
                animal.save()

                # Generate a unique RFID value for each animal in the experiment
                unique_rfid = f"RFID_{experiment.id}_{animal.id}"  # Ensures uniqueness per experiment-animal pair

                # Create or update RFIDAssignment with experiment info
                RFIDAssignment.objects.update_or_create(
                    animal=animal,
                    experiment=experiment,
                    defaults={
                        'rfid': unique_rfid,
                        'cage_number': animal.cage.id if animal.cage else 1,
                    }
                )

            return JsonResponse({'status': 'success', 'group_id': group.id})
        else:
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
    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)

    # Fetch the groups and their treatments
    groups = Group.objects.filter(experiment=experiment).select_related('treatment')

    tasks = Task.objects.filter(experiment=experiment)

    context = {
        'experiment': experiment,
        'groups': groups,
        'tasks': tasks,
        'org_id': org_id,
        'experiment_id': experiment_id,
    }

    return render(request, 'summary.html', context)

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
    organization = get_object_or_404(Organization, id=org_id)  # Fetch the organization

    if request.method == 'POST':
        form = ImportForm(request.POST, request.FILES)

        if form.is_valid():
            file = form.cleaned_data['import_file']

            try:
                # Read and decode the CSV file
                csv_file = file.read().decode('utf-8').splitlines()
                reader = csv.DictReader(csv_file)

                # Collect data to preview and calculate the number of unique animals
                data_to_preview = []
                animal_indices = set()  # To track unique animals
                cage_animals = {}  # To track the number of animals per cage

                for row in reader:
                    animal_index = row.get('Animal Index')
                    cage_number = row.get('Cage Number')

                    # Add the animal index to track unique animals
                    animal_indices.add(animal_index)

                    # Track how many animals are in each cage
                    if cage_number not in cage_animals:
                        cage_animals[cage_number] = 0
                    cage_animals[cage_number] += 1

                    # Add the row data to the preview list
                    data_to_preview.append({
                        'animal_index': animal_index,
                        'cage_number': cage_number,
                        'weight': row.get('Weight'),
                        'tumor_size': row.get('Tumor Size'),
                        'timestamp': row.get('Timestamp'),
                        'sample_id': row.get('Sample ID'),
                        'sample_type': row.get('Sample Type'),
                        'drug_name': row.get('Drug Name'),
                        'dose': row.get('Dose'),
                        'stock_concentration': row.get('Stock Concentrate'),
                        'dose_volume': row.get('Dose Volume'),
                        'sex': row.get('Sex'),
                        'species': row.get('Species'),
                        'tail': row.get('Tail'),
                        'ear': row.get('Ear'),
                        'tag': row.get('Tag'),
                        'donor': row.get('Donor'),
                        'category': row.get('Category'),
                        'score': row.get('Score')
                    })

                # Calculate number_of_animals
                number_of_animals = len(animal_indices)

                # Calculate the number of groups (cages)
                number_of_groups = len(cage_animals)

                # Calculate max_per_cage based on the highest number of animals in any cage
                max_per_cage = max(cage_animals.values())

                # Create a temporary experiment with required fields
                experiment_name = request.POST.get('experiment_name')
                if not experiment_name:
                    return JsonResponse({'status': 'error', 'message': 'Experiment name is required.'})

                temporary_experiment = Experiment.objects.create(
                    name=experiment_name,
                    owner=request.user,
                    number_of_animals=number_of_animals,
                    max_per_cage=max_per_cage,  # Correct max per cage
                    number_of_groups=number_of_groups,  # Correct number of groups
                    organization=organization  # Link the experiment to the user's organization
                )

                # Create animals and details
                for row in data_to_preview:
                    animal_index = int(row['animal_index'])
                    cage_number = int(row['cage_number'])
                    weight = float(row['weight']) if row['weight'] else None
                    tumor_size = float(row['tumor_size']) if row['tumor_size'] else None
                    timestamp_str = row['timestamp']

                    # Parse the timestamp
                    try:
                        timestamp = timezone.make_aware(datetime.strptime(timestamp_str, '%m/%d/%Y %H:%M:%S'), timezone.get_current_timezone())
                    except ValueError:
                        timestamp = timezone.make_aware(datetime.strptime(timestamp_str, '%m/%d/%Y'), timezone.get_current_timezone())

                    # Get or create the animal
                    animal, _ = Animal.objects.get_or_create(
                        experiment=temporary_experiment,
                        animal_index=animal_index,
                        defaults={'organization': organization}
                    )

                    # Handle RFID assignment (if RFID is enabled)
                    unique_rfid = f'RFID_{temporary_experiment.id}_{animal_index}'
                    rfid_assignment, created = RFIDAssignment.objects.get_or_create(
                        experiment=temporary_experiment,
                        animal=animal,
                        defaults={'cage_number': cage_number, 'rfid': unique_rfid}
                    )

                    # Save weight measurement
                    if weight or tumor_size:
                        WeightMeasurement.objects.create(
                            animal=animal,
                            rfid_assignment=rfid_assignment,
                            weight=weight,
                            tumor_size=tumor_size,
                            timestamp=timestamp,
                            recorder=request.user
                        )

                    # Handle Sample information
                    sample_id = row.get('sample_id')
                    sample_type = row.get('sample_type')

                    if sample_id and sample_type:
                        Sample.objects.create(
                            animal=animal,
                            experiment=temporary_experiment,
                            sample_id=sample_id,
                            sample_type=sample_type,
                            timestamp=timestamp,
                            user=request.user
                        )

                    # Handle Dose information (if present)
                    drug_name = row.get('drug_name')
                    dose = row.get('Dose')
                    stock_concentration = row.get('Stock Concentrate')
                    dose_volume = row.get('Dose Volume')

                    if drug_name and dose and stock_concentration and dose_volume:
                        Dose.objects.create(
                            animal=animal,
                            experiment=temporary_experiment,
                            drug_name=drug_name,
                            dose=dose,
                            stock_concentration=stock_concentration,
                            dose_volume=dose_volume,
                            timestamp=timestamp,
                            user=request.user
                        )

                    # Handle Overview fields
                    animal.sex = row.get('sex') or animal.sex
                    animal.species = row.get('species') or animal.species
                    animal.tail = row.get('tail') or animal.tail
                    animal.ear = row.get('ear') or animal.ear
                    animal.tag = row.get('tag') or animal.tag
                    animal.donor = row.get('donor') or animal.donor
                    animal.save()

                    # Handle Observations (if present)
                    category = row.get('category')
                    score = row.get('score')

                    if category and score:
                        Observation.objects.create(
                            animal=animal,
                            category=category,
                            score=score,
                            user=request.user,
                            timestamp=timestamp
                        )

                # Store the data and experiment name in the session for preview
                request.session['import_preview_data'] = data_to_preview
                request.session['experiment_name'] = experiment_name
                request.session['experiment_id'] = temporary_experiment.id

                # Redirect to the experiment confirmation page with the experiment_id
                return redirect('experiment_confirmation', org_id=org_id, experiment_id=0)  # Pass experiment_id=0 for temporary preview

            except Exception as e:
                logger.exception("Error during CSV import")
                return JsonResponse({'status': 'error', 'message': str(e)})

        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid file. Please upload a valid CSV file.'})
    else:
        form = ImportForm()

    return render(request, 'import.html', {'form': form, 'org_id': org_id})

def parse_timestamp(timestamp_str):
    """Helper function to parse timestamps in different formats."""
    try:
        return timezone.make_aware(datetime.strptime(timestamp_str, '%m/%d/%Y %H:%M:%S'), timezone.get_current_timezone())
    except ValueError:
        try:
            return timezone.make_aware(datetime.strptime(timestamp_str, '%m/%d/%Y'), timezone.get_current_timezone())
        except ValueError:
            raise ValueError(f"Invalid timestamp format: {timestamp_str}")
@login_required
def experiment_confirmation(request, org_id, experiment_id):
    organization = get_object_or_404(Organization, id=org_id)  # Ensure the organization

    # If the experiment_id is 0, it means we're in the preview stage, and the experiment doesn't exist yet
    if experiment_id == 0:
        experiment = None  # No actual experiment instance at this point
        experiment_name = request.session.get('experiment_name')  # Get the name from session
    else:
        # Get the actual experiment if it's not a preview
        experiment = get_object_or_404(Experiment, id=experiment_id, organization=organization)
        experiment_name = experiment.name

    # Get the preview data from the session
    data_to_preview = request.session.get('import_preview_data')

    if request.method == 'POST':
        # Process the confirmation and create the experiment
        if data_to_preview:
            try:
                if experiment_id == 0:
                    # Create the actual experiment now that the user confirmed the data
                    experiment = Experiment.objects.create(
                        name=experiment_name,
                        organization=organization,
                        owner=request.user,
                        number_of_animals=len(set(row['animal_index'] for row in data_to_preview)),  # Unique animals
                        number_of_groups=len(set(row['cage_number'] for row in data_to_preview))  # Unique cages
                    )

                for row in data_to_preview:
                    animal_index = int(row['animal_index'])
                    cage_number = int(row['cage_number'])
                    weight = float(row['weight'])
                    tumor_size = float(row['tumor_size']) if row['tumor_size'] else None
                    timestamp_str = row['timestamp']

                    # Parse the timestamp in MM/DD/YYYY format
                    try:
                        timestamp = datetime.strptime(timestamp_str, '%m/%d/%Y %H:%M:%S')
                    except ValueError:
                        # Handle cases where the time is not provided
                        timestamp = datetime.strptime(timestamp_str, '%m/%d/%Y')

                    # Get or create the animal
                    animal, _ = Animal.objects.get_or_create(
                        experiment=experiment,
                        animal_index=animal_index,
                        organization=organization
                    )

                    # Create or update RFID assignment
                    rfid_assignment, _ = RFIDAssignment.objects.get_or_create(
                        experiment=experiment,
                        animal=animal,
                        defaults={'rfid': f"RFID_{experiment.id}_{animal.animal_index}", 'cage_number': cage_number}
                    )

                    # Save weight measurement
                    WeightMeasurement.objects.create(
                        animal=animal,
                        rfid_assignment=rfid_assignment,
                        weight=weight,
                        tumor_size=tumor_size,
                        timestamp=timestamp,
                        recorder=request.user
                    )

                # Clear the session data after successful import
                request.session.pop('import_preview_data', None)
                request.session.pop('experiment_name', None)

                return redirect('experiment_summary', org_id=org_id, experiment_id=experiment.id)  # Redirect to summary page

            except Exception as e:
                logger.exception("Error during experiment confirmation")
                return JsonResponse({'status': 'error', 'message': str(e)})
        else:
            return JsonResponse({'status': 'error', 'message': 'No preview data available.'})

    context = {
        'data_to_preview': data_to_preview,
        'experiment_name': experiment_name,
        'org_id': org_id
    }

    return render(request, 'experiment_confirmation.html', {'experiment': experiment, 'data_to_preview': data_to_preview, 'org_id': org_id})

@login_required
def generate_csv_for_experiment(experiment):
    # Ensure the experiment belongs to the user's organization
    if experiment.organization != request.user.organization:
        return HttpResponseForbidden("You do not have permission to access this data.")

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="experiment_{experiment.id}_data.csv"'
    writer = csv.writer(response)

    # Write CSV headers
    writer.writerow(['Animal Index', 'Weight', 'Tumor Size', 'Timestamp'])

    # Get data for each measurement in the experiment
    measurements = WeightMeasurement.objects.filter(
        rfid_assignment__animal__experiment=experiment  # Link to the experiment through the animal
    ).order_by('rfid_assignment__animal__animal_index', 'timestamp')

    # Write data rows
    for measurement in measurements:
        writer.writerow([
            measurement.rfid_assignment.animal.animal_index,
            measurement.weight,
            measurement.tumor_size if measurement.tumor_size else 'N/A',
            measurement.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        ])

    return response
@login_required
def export_data(request, org_id):
    # Fetch the organization and ensure the user is part of it
    organization = get_object_or_404(Organization, id=org_id)
    user = request.user
    
    if user.organization != organization:
        return HttpResponseForbidden("You are not allowed to export data for this organization.")

    # Get search query, sort by, and order from the request
    search_query = request.GET.get('search', '')
    sort_by = request.GET.get('sort_by', 'name')  # Default sorting by 'name'
    order = request.GET.get('order', 'asc')  # Default order is 'asc'
    
    # Filter experiments where the user is the owner, collaborator, and part of the same organization
    experiments = Experiment.objects.filter(
        (Q(owner=user) | Q(collaborators__user=user)) & 
        Q(name__icontains=search_query) & 
        Q(organization=organization)
    ).distinct()
    
    # Apply sorting
    if order == 'asc':
        experiments = experiments.order_by(sort_by)
    else:
        experiments = experiments.order_by(f'-{sort_by}')
    
    # Paginate the experiments list (show 10 experiments per page)
    paginator = Paginator(experiments, 10)
    page_number = request.GET.get('page')
    experiments_page = paginator.get_page(page_number)
    
    if request.method == 'POST':
        experiment_id = request.POST.get('experiment')
        experiment = get_object_or_404(Experiment, id=experiment_id, organization=organization)

        # Generate the CSV file
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="experiment_{experiment.id}_data.csv"'

        writer = csv.writer(response)
        
        # Retrieve the animals related to the selected experiment
        animals = experiment.animal_set.all()

        # Retrieve measurements for animals in the selected experiment
        measurements = WeightMeasurement.objects.filter(rfid_assignment__animal__in=animals)

        # Write headers for the CSV
        writer.writerow(['Animal Index', 'Weight', 'Tumor Size', 'Weight Change', 'Tumor Size Change', 'Timestamp'])

        # Write data rows
        for measurement in measurements:
            writer.writerow([
                measurement.rfid_assignment.animal.animal_index,
                measurement.weight,
                measurement.tumor_size if measurement.tumor_size else 'N/A',
                measurement.weight_change if measurement.weight_change else 'N/A',
                measurement.tumor_size_change if measurement.tumor_size_change else 'N/A',
                measurement.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            ])

        # Log the user's export action
        UserAction.objects.create(
            user=user,
            action=f"Exported data for experiment {experiment.name}",
            additional_info=f"Experiment ID: {experiment.id}",
            organization=organization
        )

        return response  # Return the generated CSV response

    return render(request, 'import.html', {
        'experiments': experiments_page,  # Paginated experiments
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