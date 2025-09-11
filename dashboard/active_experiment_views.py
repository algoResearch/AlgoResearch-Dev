from django.contrib import messages as django_messages
from django.contrib import messages
from reportlab.lib.pagesizes import letter
from fpdf import FPDF
import qrcode
from random import randint
from io import BytesIO
from base64 import b64encode
from django.utils.timezone import make_aware
from django.core import serializers
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q, F, Avg, Max, Min, Count, Prefetch
from django.utils import timezone
from django.utils.timezone import now
from .models import (Conversation, RFID, Group, Treatment, Message, User, GroupMember, Task, Strain, Notification, Organization, InboxNotification, Experiment, RFIDAssignment, WeightMeasurement, Collaborator, CalendarEvent, Comment, Friend, Cage, Animal, Sample, Dose, Observation, Comment)
from django.contrib.auth.forms import UserCreationForm
from datetime import datetime, timedelta
from django.contrib.auth import login, authenticate
import pandas as pd
from django.views.decorators.csrf import csrf_exempt
from collections import defaultdict

import random
from django.contrib.auth import logout
from django.db import IntegrityError
from .forms import CustomUserCreationForm, UpdateProfileForm, ExperimentForm, WeighInImportForm, AssignTaskForm
import json
from django.http import HttpResponseRedirect
from django.utils.safestring import mark_safe
from .forms import UserProfileForm
from .forms import ProfilePictureForm
from .forms import UpdateProfileForm, OverviewForm, ObservationForm, SampleForm, DoseForm
from django.views.decorators.http import require_http_methods
from django.utils.dateparse import parse_datetime, parse_date
import csv
from .models import Invitation
from datetime import date
from django.db import transaction
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io

import traceback
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
import logging


logger = logging.getLogger(__name__)

def is_admin_or_principal(user):
    return user.role in ['admin', 'principal_admin']
def is_data_collector(user):
    return user.role in ['researcher', 'officer', 'admin', 'principal_admin']

@login_required
def experiment_list(request, org_id):
    experiments = Experiment.objects.filter(
        Q(owner=request.user) | Q(collaborators__user=request.user),
        organization=request.user.organization,  # Ensure the experiments belong to the same organization
        ended=False
    )
    return render(request, 'dashboard/all-experiments.html', {'experiments': experiments})


def calculate_next_weigh_in_date(experiment, org_id):
    if experiment.weigh_in_interval and experiment.created_at:
        days_since_start = (timezone.now().date() - experiment.created_at.date()).days
        next_weigh_in_days = experiment.weigh_in_interval - (days_since_start % experiment.weigh_in_interval)
        return timezone.now().date() + timedelta(days=next_weigh_in_days)
    return None

def calculate_days_until_next_weigh_in(next_weigh_in_date):
    if next_weigh_in_date is None:
        return None
    
    today = timezone.now().date()
    days_remaining = (next_weigh_in_date - today).days
    return max(days_remaining, 0)

# Function to calculate the progress percentage of the experiment
def calculate_progress_percentage(experiment):
    if experiment.duration is None or experiment.created_at is None:
        return None

    today = timezone.now().date()
    start_date = experiment.created_at.date()
    total_days = experiment.duration

    # Calculate how many days have passed since the start of the experiment
    days_elapsed = (today - start_date).days

    # Ensure that progress does not exceed 100%
    progress_percentage = min((days_elapsed / total_days) * 100, 100)
    return round(progress_percentage, 2)

@login_required
@require_POST
def toggle_task_completion(request, org_id, experiment_id):
    try:
        data = json.loads(request.body)
        task_id = data.get('task_id')

        if not task_id:
            return JsonResponse({'success': False, 'message': 'Task ID is required.'}, status=400)

        # Fetch the experiment and task
        experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)
        task = get_object_or_404(Task, id=task_id, experiment=experiment)

        # Mark task as completed by the current user
        if task.requires_individual_completion:
            task.mark_completed_by_user(request.user)
        else:
            # For group tasks, mark as completed directly
            task.mark_completed()

        # Check the completion status and return relevant data
        is_fully_completed = task.is_fully_completed()
        progress = task.completion_progress()

        return JsonResponse({
            'success': True,
            'message': f'Task "{task.title}" updated successfully.',
            'is_fully_completed': is_fully_completed,
            'progress': progress,
        })

    except Task.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Task not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@login_required
@transaction.atomic  # Ensure atomicity for task assignment and message creation
def assign_task(request, org_id, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization__id=org_id)

    # Get experiment owner and collaborators (researchers, investigators, etc.)
    members = set([experiment.owner])
    collaborators = Collaborator.objects.filter(experiment=experiment)

    for collaborator in collaborators:
        members.add(collaborator.user)

    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        due_date = request.POST.get('due_date')
        assigned_to_ids = request.POST.getlist('assigned_to')
        completion_requirement = request.POST.get('completion_requirement')

        # Validate required fields
        if not all([title, description, due_date, completion_requirement]):
            django_messages.error(request, "All fields are required.")
            return redirect('assign_task', org_id=org_id, experiment_id=experiment_id)

        try:
            # Create the task
            task = Task.objects.create(
                title=title,
                description=description,
                due_date=make_aware(datetime.strptime(due_date, '%Y-%m-%dT%H:%M')),
                experiment=experiment,
                assigned_by=request.user,
                requires_individual_completion=(completion_requirement == 'everyone')
            )

            # Assign users to the task
            if assigned_to_ids:
                assigned_users = User.objects.filter(id__in=assigned_to_ids)
                task.assignees.set(assigned_users)

                # Send notifications to assigned users
                for user in assigned_users:
                    conversation = Conversation.objects.filter(
                        (Q(user1=request.user, user2=user) | Q(user1=user, user2=request.user)),
                        type='private'
                    ).first()
                    if not conversation:
                        conversation = Conversation.objects.create(
                            user1=request.user,
                            user2=user,
                            type='private',
                            organization_id=org_id
                        )
                    message_content = (
                        f"You have been assigned a new task:\n\n"
                        f"Title: {task.title}\n"
                        f"Description: {task.description}\n"
                        f"Due Date: {task.due_date}\n"
                        f"Assigned by: {request.user.username}"
                    )
                    Message.objects.create(
                        sender=request.user,
                        content=message_content,
                        conversation=conversation
                    )

            django_messages.success(request, "Task assigned and notification sent to the selected users.")
            return redirect('experiment_home', org_id=org_id, experiment_id=experiment_id)
        except Exception as e:
            logger.error(f"Error assigning task: {e}")
            django_messages.error(request, "An error occurred while assigning the task.")
            return redirect('assign_task', org_id=org_id, experiment_id=experiment_id)

    # Display the assign task form
    return render(request, 'assign_task.html', {
        'experiment': experiment,
        'experiment_members': members,
        'org_id': org_id,
    })
def mark_completed_by_user(self, user):
    """Mark task as completed by a specific user."""
    if user in self.assignees.all():
        self.completed_by.add(user)
        self.save()

    if self.requires_individual_completion:
        if set(self.completed_by.all()) == set(self.assignees.all()):
            self.is_completed = True
            self.completed_at = timezone.now()
    else:
        self.is_completed = True
        self.completed_at = timezone.now()

    self.save()

@login_required
def update_task_status(request, org_id, task_id):
    task = get_object_or_404(Task, id=task_id)
    experiment_id = task.experiment.id

    if request.method == "POST":
        status = request.POST.get('status')

        if status == "in_progress":
            task.in_progress = True
            task.is_completed = False
            task.completed_at = None  # Reset the completed timestamp

        elif status == "completed":
            if task.requires_individual_completion:
                # Mark completed for the current user
                task.mark_completed_by_user(request.user)

                # Check if the task is fully completed
                if task.is_completed:
                    # Optionally notify assignees about full completion
                    logger.info(f"Task '{task.title}' fully completed by all assignees.")
            else:
                # Mark as completed for the group
                task.is_completed = True
                task.in_progress = False
                task.completed_at = timezone.now()  # Mark the task as completed

        task.save()

        # Optionally, send notifications about task updates
        return redirect('experiment_home', org_id=org_id, experiment_id=experiment_id)

    return redirect('experiment_home', org_id=org_id, experiment_id=experiment_id)

@login_required
def experiment_home(request, org_id, experiment_id):
    organization = get_object_or_404(Organization, id=org_id)
    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)
    collaborators = Collaborator.objects.filter(experiment=experiment).select_related('user')

    # Get the list of investigator objects directly from the ManyToManyField
    investigators = experiment.investigators.all()

    # Fetch all groups related to this experiment
    groups = Group.objects.filter(experiment=experiment)
    total_groups = groups.count()
    # Calculate the total number of animals by summing the number_of_animals for each group
    total_animals = sum(group.number_of_animals for group in groups)

    # Check if the experiment has a weight schedule
    has_weight_schedule = experiment.weight_schedule and experiment.weigh_in_interval is not None

    # If no weight schedule, calculate metrics for summary cards
    if not has_weight_schedule:
        cages_configured = Cage.objects.filter(experiment=experiment).count()
        
        # Update to count distinct weigh-in sessions based on session_id
        weigh_ins_completed = (
            WeightMeasurement.objects.filter(animal__experiment=experiment)
            .values('session_id')
            .distinct()
            .count()
        )
    else:
        cages_configured = weigh_ins_completed = None

    # Calculate next weigh-in and days remaining (if weight schedule exists)
    next_weigh_in_date = calculate_next_weigh_in_date(experiment) if has_weight_schedule else None
    days_until_next_weigh_in = calculate_days_until_next_weigh_in(next_weigh_in_date)

    # Calculate experiment progress percentage (if duration exists)
    progress_percentage = calculate_progress_percentage(experiment) if experiment.duration else None

    # Calculate health statuses
    healthy_count = Animal.objects.filter(experiment=experiment, is_removed=False).count()  # Assuming all non-removed are healthy
    at_risk_count = Animal.objects.filter(experiment=experiment, at_risk=True).count()  # Using the 'at_risk' field
    removal_count = Animal.objects.filter(experiment=experiment, is_removed=True).count()

    # Fetch tasks and order by completion status (completed tasks at the bottom)
    tasks = Task.objects.filter(experiment=experiment, assignees=request.user).order_by('is_completed', 'id')

    context = {
        'experiment': experiment,
        'org_id': org_id,
        'has_weight_schedule': has_weight_schedule,
        'total_animals': total_animals,  # Total animals in all groups
        'total_groups': total_groups,
        'cages_configured': cages_configured,
        'weigh_ins_completed': weigh_ins_completed,  # Count of sessions instead of individual weigh-ins
        'next_weigh_in_date': next_weigh_in_date,
        'days_until_next_weigh_in': days_until_next_weigh_in,
        'progress_percentage': progress_percentage,
        'healthy_count': healthy_count,
        'at_risk_count': at_risk_count,
        'removal_count': removal_count,
        'tasks': tasks,
        'investigators': investigators,  # Full investigator User objects
        'collaborators': collaborators,
        'experiment_ended': experiment.ended,
        'experiment_end_date': experiment.end_date,
    }

    return render(request, 'experiments/experiment-home.html', context)

@login_required
def experiment_tasks(request, org_id, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)
    
    # Fetch all tasks associated with the user in the experiment
    user_tasks = Task.objects.filter(experiment=experiment, assignees=request.user).order_by('start_date')

    # Check if recurring tasks generate calendar events
    task_events = CalendarEvent.objects.filter(
        experiment=experiment, 
        user=request.user, 
        start_date__gte=timezone.now()
    ).order_by('start_date')

    context = {
        'experiment': experiment,
        'org_id': org_id,
        'tasks': user_tasks,  # Direct tasks
        'task_events': task_events,  # Recurring events derived from tasks
    }
    return render(request, 'experiments/experiment_tasks.html', context)

@login_required
def map_rfid(request, org_id, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)

    # Group animals by groups in the experiment
    groups = Group.objects.filter(experiment=experiment)
    grouped_animals_data = defaultdict(list)

    for group in groups:
        animals_in_group = Animal.objects.filter(group=group).order_by('animal_index')
        for animal in animals_in_group:
            assigned_rfid = RFIDAssignment.objects.filter(animal=animal, experiment=experiment).first()
            rfid = assigned_rfid.rfid if assigned_rfid else "Pending"
            grouped_animals_data[group.name].append({
                'animal_index': animal.animal_index,
                'rfid': rfid
            })

    context = {
        'experiment': experiment,
        'org_id': org_id,
        'grouped_animals_data': dict(grouped_animals_data)
    }

    return render(request, 'experiments/mapRFID.html', context)

def get_used_rfids(organization):
    # Fetch all the used RFIDs for the specific organization
    return RFIDAssignment.objects.filter(experiment__organization=organization).values_list('rfid', flat=True)

@login_required
def get_available_rfids(request, org_id, experiment_id):
    # Fetch all assigned RFID numbers to avoid duplication
    assigned_rfids = set(RFIDAssignment.objects.values_list('rfid', flat=True))

    # Get unassigned RFIDs in the model first
    available_rfids = list(RFID.objects.filter(assigned=False).exclude(rfid__in=assigned_rfids).values_list('rfid', flat=True))

    # Generate unique RFIDs in the range if no available RFIDs are in the database
    def generate_unique_rfids(count):
        generated_rfids = set()
        while len(generated_rfids) < count:
            new_rfid = f"RFID_{randint(1000, 3000)}"
            if new_rfid not in assigned_rfids and new_rfid not in generated_rfids:
                generated_rfids.add(new_rfid)
        return list(generated_rfids)

    # Fallback: Generate up to 10 unique RFIDs if none found
    if not available_rfids:
        available_rfids = generate_unique_rfids(10)

    return JsonResponse({'available_rfids': available_rfids})


def available_rfids_pdf(request, org_id):
    # Fetch organization
    organization = get_object_or_404(Organization, id=org_id)

    # Fetch used and available RFIDs for this specific organization
    used_rfids = get_used_rfids(organization)
    available_rfids = get_available_rfids(used_rfids)

    # Create PDF
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # Title
    pdf.cell(200, 10, txt=f"Available RFIDs for {organization.name}", ln=True, align='C')

    # Add the RFIDs
    pdf.ln(10)  # Line break
    pdf.cell(200, 10, txt="RFID Numbers:", ln=True)

    # List RFIDs in the PDF
    for rfid in available_rfids:
        pdf.cell(200, 10, txt=str(rfid), ln=True)

    # Prepare the response as a downloadable PDF
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="available_rfids_{organization.name}.pdf"'

    # Output the PDF content to the response (write the PDF in memory)
    pdf_output = pdf.output(dest='S')  # No encoding needed, it returns a byte array

    response.write(pdf_output)

    return response

@login_required
@csrf_exempt
def save_rfids(request, org_id, experiment_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            rfids_data = data.get('rfids')
            experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=request.user.organization)

            with transaction.atomic():
                for item in rfids_data:
                    animal_index = item.get('animal_index')
                    rfid_value = item.get('rfid')

                    if rfid_value:
                        # Mark RFID as assigned in the RFID model
                        rfid = RFID.objects.filter(rfid=rfid_value, assigned=False).first()
                        if not rfid:
                            return JsonResponse({'status': 'error', 'message': f'RFID {rfid_value} is unavailable.'}, status=400)

                        rfid.assigned = True
                        rfid.save()

                        # Assign RFID to the animal in the experiment
                        animal, created = Animal.objects.update_or_create(
                            experiment=experiment,
                            animal_index=animal_index,
                            defaults={'rfid_tag': rfid_value}
                        )

                        RFIDAssignment.objects.update_or_create(
                            experiment=experiment,
                            animal=animal,
                            defaults={'rfid': rfid_value}
                        )

            return JsonResponse({'status': 'success'}, status=200)

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)

@login_required
@require_POST
def update_rfids(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization=request.user.organization)  # Check organization
    data = json.loads(request.body)
    rfid_assignments = data.get('rfid_assignments', [])

    used_rfids = get_used_rfids()  # Get all used RFIDs
    available_rfids = get_available_rfids(used_rfids)  # Get list of available RFIDs

    with transaction.atomic():
        for assignment in rfid_assignments:
            animal_index = assignment['animal_index']
            rfid = assignment.get('rfid')

            # Assign an available RFID if not already provided
            if not rfid:
                if not available_rfids:
                    return JsonResponse({'status': 'error', 'message': 'No available RFIDs.'}, status=400)
                rfid = random.choice(available_rfids)
                available_rfids.remove(rfid)  # Remove this RFID from available list after assignment

            # Ensure that RFID is not already in use in any experiment
            if RFIDAssignment.objects.filter(rfid=rfid).exclude(animal__experiment_id=experiment_id).exists():
                return JsonResponse({'status': 'error', 'message': f'RFID {rfid} is already in use in another experiment.'}, status=400)

            animal, created = Animal.objects.get_or_create(
                experiment_id=experiment_id,
                animal_index=animal_index,
                defaults={'rfid_tag': rfid}
            )

            # Ensure unique assignment per experiment and animal
            RFIDAssignment.objects.update_or_create(
                experiment=animal.experiment,
                animal=animal,
                defaults={'rfid': rfid}
            )

    return JsonResponse({'status': 'success', 'message': 'RFID assignments updated successfully.'})

@login_required
@user_passes_test(is_data_collector)
def cage_configuration(request, org_id, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)
    groups = Group.objects.filter(experiment=experiment)
    group_colors = {group.name: group.color for group in groups}


    # Initialize a dictionary to hold cages and their animals
    cages = defaultdict(list)

    # Fetch available animals that are not assigned to any experiment
    available_animals = Animal.objects.filter(
        organization_id=org_id,
        experiment__isnull=True,
        is_available=True
    )

    # Loop through each group and gather animals
    for group in groups:
        animals_in_group = Animal.objects.filter(group=group).order_by('animal_index')
        for animal in animals_in_group:
            animal_data = {
                'animal_index': animal.animal_index,
                'cage_number': 'N/A',
                'weight': 'N/A',
                'tumor_size': 'N/A',
                'tracking_date': 'N/A',
                'weight_change_first': None,
                'tumor_size_change_first': None,
            }

            # Fetch the RFID assignment for this animal within the experiment
            rfid_assignment = RFIDAssignment.objects.filter(animal=animal, experiment=experiment).first()
            if rfid_assignment:
                animal_data['cage_number'] = rfid_assignment.cage_number
                animal_data['tracking_date'] = rfid_assignment.initial_weight_date

                # Get weight and tumor size measurements
                measurements = WeightMeasurement.objects.filter(rfid_assignment=rfid_assignment).order_by('timestamp')
                if measurements.exists():
                    first_measurement = measurements.first()
                    last_measurement = measurements.last()

                    # Assign weight and tumor size from last measurement
                    animal_data['weight'] = last_measurement.weight if last_measurement.weight else 'N/A'
                    animal_data['tumor_size'] = last_measurement.tumor_size if last_measurement.tumor_size else 'N/A'

                    # Calculate changes from the first measurement
                    if first_measurement and last_measurement:
                        animal_data['weight_change_first'] = (
                            last_measurement.weight - first_measurement.weight
                            if first_measurement.weight and last_measurement.weight
                            else None
                        )
                        animal_data['tumor_size_change_first'] = (
                            last_measurement.tumor_size - first_measurement.tumor_size
                            if first_measurement.tumor_size and last_measurement.tumor_size
                            else None
                        )

            cages[group.name].append(animal_data)

    context = {
        'experiment': experiment,
        'cages': dict(cages),
        'group_colors': group_colors,
        'available_animals': available_animals,  # Add available animals to context
        'org_id': org_id,
    }

    return render(request, 'vivarium/cage-configuration.html', context)




@login_required
@require_POST
@csrf_exempt
def update_cage_configuration(request, org_id, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)
    
    try:
        data = json.loads(request.body)  # Parse the cage configuration from the request body
        cage_configuration = data.get('configuration', {})

        if not cage_configuration:
            logger.error(f"Invalid data format received for experiment {experiment_id}")
            return JsonResponse({'status': 'error', 'message': 'Invalid data format'}, status=400)

        # Log the configuration data for debugging
        logger.info(f"Received cage configuration for experiment {experiment_id}: {cage_configuration}")

        # Dictionary to track assigned animals and prevent duplicate assignments
        assigned_animals = {}

        for cage_number, animals in cage_configuration.items():
            for animal_info in animals:
                animal_id = animal_info.get('animal_id')

                # Validate animal_id
                if not animal_id or not str(animal_id).isdigit():
                    logger.warning(f"Invalid or missing animal ID: '{animal_id}' for cage {cage_number}")
                    continue  # Skip invalid entries

                # Avoid reassigning an animal to multiple cages/groups
                if animal_id in assigned_animals:
                    logger.warning(f"Animal ID {animal_id} is already assigned to a group, skipping duplicate.")
                    continue

                # Mark the animal as assigned
                assigned_animals[animal_id] = cage_number

                animal = Animal.objects.filter(id=animal_id, organization_id=org_id).first()
                if not animal:
                    logger.warning(f"Animal with ID {animal_id} not found in organization {org_id}")
                    continue

                # Set animal's availability, experiment, and group information
                animal.is_available = False
                animal.experiment = experiment  # Associate the animal with the experiment

                # Check if the animal already belongs to a group
                if not animal.group or animal.group.experiment != experiment:
                    # Assign to an appropriate group if not already assigned
                    group = Group.objects.filter(name=cage_number, experiment=experiment).first()
                    if group:
                        animal.group = group
                        logger.info(f"Assigned animal ID {animal_id} to group ID {group.id}")

                animal.save()

                # Update or create the RFIDAssignment with the vivarium cage or provided cage number
                vivarium_cage_number = animal.cage.id if animal.cage else cage_number
                unique_rfid = f"RFID_{experiment.id}_{animal_id}"  # Unique RFID for each animal in the experiment

                RFIDAssignment.objects.update_or_create(
                    animal=animal,
                    experiment=experiment,
                    defaults={
                        'rfid': unique_rfid,
                        'cage_number': vivarium_cage_number,
                        'removed': False,
                    }
                )

        return JsonResponse({'status': 'success', 'message': 'Cage configuration updated'})

    except json.JSONDecodeError:
        logger.error(f"JSON decoding error for experiment {experiment_id}")
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data'}, status=400)

    except Exception as e:
        logger.exception(f"Error updating cage configuration for experiment {experiment_id}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
@login_required
@require_POST
def update_cages(request, experiment_id):
    try:
        data = json.loads(request.body).get('configuration', {})
        experiment = get_object_or_404(Experiment, id=experiment_id)

        # Log the received configuration data
        logger.info(f"Updating cages for experiment {experiment_id} with data: {data}")

        for cage_number, animals in data.items():
            for animal in animals:
                rfid = animal.get('rfid')
                index = animal.get('index')

                if not rfid or not index:
                    logger.warning(f"Missing RFID or index for animal in experiment {experiment_id}")
                    continue

                # Perform the update
                RFIDAssignment.objects.filter(
                    experiment=experiment,
                    rfid=rfid,
                    animal__animal_index=index
                ).update(cage_number=cage_number)

        return JsonResponse({"status": "success", "message": "Cage configuration updated"})

    except json.JSONDecodeError:
        logger.error(f"JSON decoding error for experiment {experiment_id}")
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data'}, status=400)

    except Exception as e:
        logger.exception(f"Error updating cages for experiment {experiment_id}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def import_measurements(request, org_id, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization=request.user.organization) 
    return render(request, 'experiments/import_measurements.html', {
        'experiment': experiment,
        'org_id': org_id  # Pass org_id to the template
    })

@login_required
@require_POST
def process_import_measurements(request, org_id, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization=request.user.organization)  # Ensure the experiment belongs to the user's organization

    if request.method == 'POST' and request.FILES.get('file'):
        uploaded_file = request.FILES['file']
        measurement_date = request.POST.get('measurement_date')

        # Validate and parse the date
        try:
            measurement_date = parse_datetime(measurement_date)
            if not measurement_date:
                messages.error(request, "Invalid date provided. Use YYYY-MM-DD format.")
                return redirect('import_measurements', experiment_id=experiment_id)
            # Ensure timezone awareness
            if timezone.is_naive(measurement_date):
                measurement_date = timezone.make_aware(measurement_date)
        except Exception as e:
            messages.error(request, f"Error parsing date: {str(e)}")
            return redirect('import_measurements', experiment_id=experiment_id)

        # Parse the CSV file with semicolon delimiter
        parsed_data = []
        if uploaded_file.name.endswith('.csv'):
            file_data = uploaded_file.read().decode('utf-8').splitlines()
            reader = csv.DictReader(file_data, delimiter=';')

            # Validate headers before proceeding
            expected_headers = ['animal number', 'cage number', 'weight', 'tumor size']
            reader.fieldnames = [field.strip().lower() for field in reader.fieldnames]
            if reader.fieldnames != expected_headers:
                messages.error(request, "CSV headers do not match the expected format. Please upload a valid file.")
                return redirect('import_measurements', experiment_id=experiment_id)

            # Process each row in the CSV
            for row in reader:
                print("Row:", row)  # Debugging: Print each row

                try:
                    # Safely convert and handle values
                    animal_number = row.get('animal number', '').strip()
                    cage_number = row.get('cage number', '').strip()
                    weight = float(row.get('weight', 0)) if row.get('weight', '').strip() else None
                    tumor_size = float(row.get('tumor size', 0)) if row.get('tumor size', '').strip() else None
                except ValueError:
                    messages.error(request, "Invalid values found in the CSV. Please check and upload again.")
                    return redirect('import_measurements', experiment_id=experiment_id)

                # Add the row to parsed_data for the confirmation page
                parsed_data.append({
                    'animal_number': animal_number,
                    'cage_number': cage_number,
                    'weight': weight,
                    'tumor_size': tumor_size
                })

            # If there is an issue with parsing, output debugging information
            print("Parsed Data:", parsed_data)

            # Pass the parsed data to the confirmation page
            parsed_data_json = json.dumps(parsed_data)  # Convert to JSON for later use
            return render(request, 'experiments/import_confirmation.html', {
                'experiment': experiment,
                'parsed_data': parsed_data,
                'parsed_data_json': parsed_data_json,
                'measurement_date': measurement_date,
                'uploaded_file': uploaded_file.name,  # Pass file name for display
                'org_id': org_id  # Make sure org_id is passed
            })
        else:
            messages.error(request, "Please upload a valid CSV file.")
            return redirect('import_measurements', org_id=org_id, experiment_id=experiment_id)

    messages.error(request, "Failed to upload the file.")
    return redirect('import_measurements', org_id=org_id, experiment_id=experiment_id)
@login_required
def confirm_import_measurements(request, org_id, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization=request.user.organization)  # Ensure the experiment belongs to the user's organization

    # Get the parsed data and measurement date from the form submission
    parsed_data_str = request.POST.get('parsed_data')
    measurement_date = request.POST.get('measurement_date')

    # Check if the parsed_data was sent correctly
    if not parsed_data_str:
        return JsonResponse({'status': 'error', 'message': 'No parsed data received'}, status=400)

    print("Parsed Data Received:", parsed_data_str)

    # Try to load the parsed data
    try:
        parsed_data = json.loads(parsed_data_str)
    except json.JSONDecodeError as e:
        return JsonResponse({'status': 'error', 'message': f"Error decoding JSON data: {str(e)}"}, status=400)

    # Parse the measurement_date into the correct format
    try:
        measurement_date = parse_datetime(measurement_date)
        if not measurement_date:
            return JsonResponse({'status': 'error', 'message': "Invalid date format. Please use YYYY-MM-DD."}, status=400)

        # Make the datetime timezone-aware if necessary
        if timezone.is_naive(measurement_date):
            measurement_date = timezone.make_aware(measurement_date)
    except ValueError as e:
        return JsonResponse({'status': 'error', 'message': f"Invalid date format: {str(e)}"}, status=400)

    # Process each row of parsed data
    for row in parsed_data:
        animal_number = row.get('animal_number')
        cage_number = row.get('cage_number')
        weight = row.get('weight')
        tumor_size = row.get('tumor_size')

        print(f"Processing Animal {animal_number}: Weight = {weight}, Tumor Size = {tumor_size}")

        try:
            # Ensure weight and tumor_size are floats
            weight = float(weight) if weight is not None else None
            tumor_size = float(tumor_size) if tumor_size is not None else None

            # Find the animal
            animal = Animal.objects.get(animal_index=animal_number, experiment=experiment)
        except Animal.DoesNotExist:
            print(f"Error: Animal {animal_number} not found.")
            return JsonResponse({'status': 'error', 'message': f"Animal {animal_number} not found in experiment."}, status=400)
        except ValueError as e:
            print(f"Error converting data for Animal {animal_number}: {e}")
            return JsonResponse({'status': 'error', 'message': f"Error converting data for Animal {animal_number}: {str(e)}"}, status=400)

        # Try to find the RFID assignment
        try:
            rfid_assignment = RFIDAssignment.objects.filter(animal=animal).first()
            if not rfid_assignment:
                return JsonResponse({'status': 'error', 'message': f"No RFID assignment found for Animal {animal_number}."}, status=400)
        except Exception as e:
            print(f"Error finding RFID assignment for Animal {animal_number}: {e}")
            return JsonResponse({'status': 'error', 'message': f"Error finding RFID assignment for Animal {animal_number}: {str(e)}"}, status=500)

        # Save the weight measurement
        try:
            WeightMeasurement.objects.create(
                rfid_assignment=rfid_assignment,
                animal=animal,
                weight=weight,
                tumor_size=tumor_size,
                timestamp=measurement_date,
                recorder=request.user
            )
            print(f"Measurement for Animal {animal_number} saved successfully.")
        except Exception as e:
            print(f"Error saving measurement for Animal {animal_number}: {e}")
            return JsonResponse({'status': 'error', 'message': f"Error saving measurement for Animal {animal_number}: {str(e)}"}, status=500)

        except Exception as e:
            print(f"Error saving measurement for Animal {animal_number}: {e}")
            return JsonResponse({'status': 'error', 'message': f"Error saving measurement for Animal {animal_number}: {str(e)}"}, status=500)

    return JsonResponse({'status': 'success', 'message': "Measurements imported successfully!"})


@login_required
def import_details(request, org_id, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization=request.user.organization)  # Ensure experiment belongs to user's organization
    return render(request, 'experiments/import_details.html', {
        'experiment': experiment,
        'org_id': org_id  # Pass org_id to the template
    })

@login_required
@require_POST
def process_import_details(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization=request.user.organization)  # Ensure experiment belongs to user's organization


    if request.method == 'POST' and request.FILES.get('file'):
        uploaded_file = request.FILES['file']

        # Parse the CSV file with semicolon delimiter
        parsed_data = []
        if uploaded_file.name.endswith('.csv'):
            file_data = uploaded_file.read().decode('utf-8').splitlines()
            reader = csv.DictReader(file_data, delimiter=';')

            # Validate headers before proceeding
            expected_headers = ['animal id', 'sex', 'species', 'tail', 'ear', 'donor']
            reader.fieldnames = [field.strip().lower() for field in reader.fieldnames]
            if reader.fieldnames != expected_headers:
                messages.error(request, "CSV headers do not match the expected format. Please upload a valid file.")
                return redirect('import_details', experiment_id=experiment_id)

            # Process each row in the CSV
            for row in reader:
                try:
                    # Safely convert and handle values
                    animal_id = row.get('animal id', '').strip()
                    sex = row.get('sex', '').strip()
                    species = row.get('species', '').strip()
                    tail = row.get('tail', '').strip()
                    ear = row.get('ear', '').strip()
                    donor = row.get('donor', '').strip()

                    # Add the row to parsed_data for the confirmation page
                    parsed_data.append({
                        'animal_id': animal_id,
                        'sex': sex,
                        'species': species,
                        'tail': tail,
                        'ear': ear,
                        'donor': donor
                    })
                except ValueError:
                    messages.error(request, "Invalid values found in the CSV. Please check and upload again.")
                    return redirect('import_details', experiment_id=experiment_id)

            # Pass the parsed data to the confirmation page
            parsed_data_json = json.dumps(parsed_data)  # Convert to JSON for later use
            return render(request, 'experiments/import_confirmation_details.html', {
                'experiment': experiment,
                'parsed_data': parsed_data,
                'parsed_data_json': parsed_data_json,
                'uploaded_file': uploaded_file.name  # Pass file name for display
            })
        else:
            messages.error(request, "Please upload a valid CSV file.")
            return redirect('import_details', experiment_id=experiment_id)

    messages.error(request, "Failed to upload the file.")
    return redirect('import_details', organization = organization, experiment_id=experiment_id)
@login_required
@require_POST
def confirm_import_details(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization=request.user.organization)  # Ensure experiment belongs to user's organization

    # Get the parsed data from the form submission
    parsed_data_str = request.POST.get('parsed_data')

    # Check if the parsed_data was sent correctly
    if not parsed_data_str:
        return JsonResponse({'status': 'error', 'message': 'No parsed data received'}, status=400)

    try:
        parsed_data = json.loads(parsed_data_str)
    except json.JSONDecodeError as e:
        return JsonResponse({'status': 'error', 'message': f"Error decoding JSON data: {str(e)}"}, status=400)

    # Process each row of parsed data
    for row in parsed_data:
        animal_id = row.get('animal_id')
        sex = row.get('sex')
        species = row.get('species')
        tail = row.get('tail')
        ear = row.get('ear')
        donor = row.get('donor')

        print(f"Processing Animal {animal_id}: Sex = {sex}, Species = {species}, Tail = {tail}, Ear = {ear}, Donor = {donor}")

        try:
            # Find the animal by Animal ID
            animal = Animal.objects.get(animal_index=animal_id, experiment=experiment)

            # Update fields if provided, leave unchanged if None
            if sex:
                animal.sex = sex
            if species:
                animal.species = species
            if tail:
                animal.tail = tail
            if ear:
                animal.ear = ear
            if donor:
                animal.donor = donor

            # Save the updated animal
            animal.save()
        except Animal.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': f"Animal {animal_id} not found in experiment."}, status=400)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f"Error updating Animal {animal_id}: {str(e)}"}, status=500)

    return JsonResponse({'status': 'success', 'message': "Details imported successfully!"})



@login_required
def experiment_qr_code(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization=request.user.organization)  # Ensure experiment belongs to user's organization
    
    # Generate QR code with the URL of the animals page
    animals_url = request.build_absolute_uri(f"/experiments/{experiment_id}/animals/")
    
    # Generate QR code image
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    qr.add_data(animals_url)
    qr.make(fit=True)
    
    # Create an in-memory image for the QR code
    img = qr.make_image(fill="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    
    # Convert image to base64
    qr_code_image = b64encode(buffer.getvalue()).decode('utf-8')

    context = {
        'experiment': experiment,
        'qr_code_image': qr_code_image,  # Pass QR code to template
    }

    return render(request, 'experiments/experiment_qr_code.html', context)

def add_investigators_to_collaborators(experiment, investigator_usernames):
    for username in investigator_usernames:
        try:
            user = User.objects.get(username=username)
            Collaborator.objects.get_or_create(experiment=experiment, user=user, role='Investigator')
        except User.DoesNotExist:
            print(f"User '{username}' not found.")

@csrf_exempt
def update_experiment(request, experiment_id):
    if request.method == 'PATCH':
        experiment = get_object_or_404(Experiment, id=experiment_id, organization=request.user.organization)  # Ensure experiment belongs to user's organization
        try:
            data = json.loads(request.body)
            rfid_assignments = data.get('rfid_assignments', [])
            investigators = data.get('investigators', [])  # Get the list of investigators from the request
            
            # Update RFID assignments
            for assignment in rfid_assignments:
                required_keys = {'animal_index', 'rfid', 'weight', 'tumor_size', 'cage_number'}
                if not all(key in assignment for key in required_keys):
                    return JsonResponse({'status': 'error', 'message': 'Missing required keys.'}, status=400)

                # Retrieve or create the corresponding animal without setting RFID
                animal, _ = Animal.objects.get_or_create(
                    experiment=experiment,
                    animal_index=assignment['animal_index'],
                )

                # Update or create the RFID assignment
                RFIDAssignment.objects.update_or_create(
                    animal=animal,
                    defaults={
                        'rfid': assignment['rfid'],
                        'weight': assignment.get('weight'),
                        'tumor_size': assignment.get('tumor_size'),
                        'cage_number': assignment.get('cage_number'),
                    }
                )

            # Update investigators as collaborators
            if investigators:
                for username in investigators:
                    try:
                        user = User.objects.get(username=username)
                        Collaborator.objects.get_or_create(experiment=experiment, user=user, role='Investigator')
                    except User.DoesNotExist:
                        return JsonResponse({'status': 'error', 'message': f"User '{username}' not found."}, status=400)

            return JsonResponse({'status': 'success', 'message': 'Experiment updated successfully.'})

        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

@login_required
@require_POST
def delete_experiment(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, owner=request.user, organization=request.user.organization)  # Check organization
    experiment.ended = True
    experiment.save()

    CalendarEvent.objects.filter(experiment=experiment).delete()

    return JsonResponse({'status': 'Experiment deleted successfully'})

@login_required
def view_experiment(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization=request.user.organization)  # Check organization
    return render(request, 'view_experiment.html', {'experiment': experiment})


def get_rfid_assignments(request, experiment_id):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=403)

    try:
        experiment = Experiment.objects.get(id=experiment_id, organization=request.user.organization)  # Check organization
        assignments = RFIDAssignment.objects.filter(experiment=experiment).values('animal__animal_index', 'rfid')
        return JsonResponse({'rfids': list(assignments)})
    except Experiment.DoesNotExist:
        return JsonResponse({'error': 'Experiment not found'}, status=404)


@login_required
def all_experiments(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    user = request.user

    # Filter only finalized experiments for the user
    active_experiments_qs = Experiment.objects.filter(
        Q(owner=user) | Q(collaborators__user=user),
        organization=organization,
        is_draft=False,  # Only finalized experiments
        ended=False  # Exclude ended experiments
    ).distinct().select_related('owner').order_by('-created_at')

    past_experiments_qs = Experiment.objects.filter(
        Q(owner=user) | Q(collaborators__user=user),
        organization=organization,
        is_draft=False,  # Only finalized experiments
        ended=True  # Only ended experiments
    ).distinct().select_related('owner').order_by('-created_at')

    # Handle pagination for active experiments
    active_page = request.GET.get('page_active', 1)
    active_paginator = Paginator(active_experiments_qs, 10)  # Show 10 active experiments per page
    try:
        active_experiments = active_paginator.page(active_page)
    except PageNotAnInteger:
        active_experiments = active_paginator.page(1)
    except EmptyPage:
        active_experiments = active_paginator.page(active_paginator.num_pages)

    # Handle pagination for past experiments
    past_page = request.GET.get('page_past', 1)
    past_paginator = Paginator(past_experiments_qs, 10)  # Show 10 past experiments per page
    try:
        past_experiments = past_paginator.page(past_page)
    except PageNotAnInteger:
        past_experiments = past_paginator.page(1)
    except EmptyPage:
        past_experiments = past_paginator.page(past_paginator.num_pages)

    return render(request, 'experiments/all-experiments.html', {
        'org_id': org_id,
        'active_experiments': active_experiments,
        'past_experiments': past_experiments,
    })


@login_required
def get_active_experiment_count(request, org_id):
    user = request.user

    # Get the count of active experiments for the specified organization where the user is involved
    active_experiment_count = Experiment.objects.filter(
        ended=False,
        organization__id=org_id
    ).filter(
        Q(owner=user) | Q(collaborators__user=user)
    ).distinct().count()

    return JsonResponse({'active_experiment_count': active_experiment_count})
@login_required
def fetch_unassigned_animals(request, org_id, experiment_id):
    """
    Fetch animals that are in the vivarium but not assigned to any cage or group in the experiment.
    """
    organization = get_object_or_404(Organization, id=org_id)
    experiment = get_object_or_404(Experiment, id=experiment_id, organization=organization)

    # Query unassigned animals in the vivarium (no group or cage assignment)
    unassigned_animals = Animal.objects.filter(
        organization=organization,
        experiment__isnull=True,  # Animal is not yet assigned to any experiment
        group__isnull=True,       # Animal is not assigned to any group
        cage__isnull=True         # Animal is not assigned to any cage
    )

    # Serialize data for the frontend
    animal_data = [
        {
            'id': animal.id,
            'animal_index': animal.animal_index,
            'rfid_tag': animal.rfid_tag,
            'sex': animal.sex,
            'species': animal.species,
            'strain': animal.strain,
            'date_of_birth': animal.date_of_birth
        }
        for animal in unassigned_animals
    ]

    return JsonResponse({'animals': animal_data})

@login_required
@require_POST
def delete_animal(request, experiment_id, animal_index):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization=request.user.organization)  # Ensure experiment belongs to user's organization
    RFIDAssignment.objects.filter(experiment=experiment, animal_index=animal_index).update(removed=True)
    return JsonResponse({'status': 'Animal deleted successfully'})

def generate_pdf_for_experiment(experiment):
    # Create a BytesIO buffer to hold the PDF data
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Fetch measurements and order by timestamp
    measurements = WeightMeasurement.objects.filter(rfid_assignment__experiment=experiment).order_by('timestamp')

    # Debugging: Check if measurements are being fetched
    print(f"Measurements found for Experiment {experiment.id}: {measurements.count()}")

    if not measurements.exists():
        p.drawString(100, height - 150, "No measurements found for this experiment.")
        p.save()
        buffer.seek(0)
        return HttpResponse(buffer, content_type='application/pdf')

    # Initialize variables to store sessions and baseline measurements
    current_session = 1
    last_timestamp = None
    baseline_measurements = {}
    session_measurements = []

    # PDF content
    p.setFont("Helvetica-Bold", 14)
    p.drawString(100, height - 100, f"Experiment {experiment.id} Data Report")
    p.setFont("Helvetica", 12)
    p.drawString(100, height - 120, f"Generated on: {now().strftime('%Y-%m-%d %H:%M:%S')}")  # Correct now usage here
    
    y_position = height - 150  # Starting position for data rows

    # Table header
    p.drawString(100, y_position, "Session | Animal Index | Weight (g) | Tumor Size (mm) | Timestamp")
    y_position -= 20  # Move down for next line

    # Iterating over measurements
    for measurement in measurements:
        animal_index = measurement.rfid_assignment.animal.animal_index
        timestamp = measurement.timestamp

        # Debugging: Print each measurement's details
        print(f"Processing Animal {animal_index}, Weight: {measurement.weight}, Tumor Size: {measurement.tumor_size}, Timestamp: {timestamp}")

        # If this is the first row or a new session is detected (60 seconds threshold)
        if last_timestamp and (timestamp - last_timestamp).total_seconds() > 60:
            # Calculate averages for the previous session
            if session_measurements:
                weight_changes = []
                tumor_size_changes = []

                for m in session_measurements:
                    initial_weight = baseline_measurements[m.rfid_assignment.animal.animal_index]['weight']
                    initial_tumor_size = baseline_measurements[m.rfid_assignment.animal.animal_index]['tumor_size']
                    weight_change = m.weight - initial_weight
                    tumor_size_change = (m.tumor_size - initial_tumor_size) if initial_tumor_size is not None and m.tumor_size is not None else 0

                    weight_changes.append(weight_change)
                    if initial_tumor_size is not None and m.tumor_size is not None:
                        tumor_size_changes.append(tumor_size_change)

                # Calculate averages
                avg_weight_change = sum(weight_changes) / len(weight_changes) if weight_changes else 0
                avg_tumor_size_change = sum(tumor_size_changes) / len(tumor_size_changes) if tumor_size_changes else 0

                # Write "End of Session" row and averages
                p.drawString(100, y_position, f"End of Session {current_session}")
                y_position -= 20
                p.drawString(100, y_position, f"Avg Weight Change: {avg_weight_change:.2f}g, Avg Tumor Size Change: {avg_tumor_size_change:.2f}mm")
                y_position -= 20

            # Start a new session
            current_session += 1
            p.drawString(100, y_position, f"Session {current_session}")
            y_position -= 20
            session_measurements = []

        # Add the current measurement to the session
        session_measurements.append(measurement)

        # Record baseline if not already recorded
        if animal_index not in baseline_measurements:
            baseline_measurements[animal_index] = {
                'weight': measurement.weight,
                'tumor_size': measurement.tumor_size,
            }

        # Write animal data
        p.drawString(100, y_position, f"{current_session} | {animal_index} | {measurement.weight}g | {measurement.tumor_size if measurement.tumor_size else 'N/A'} | {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        y_position -= 20

        # Update the last timestamp
        last_timestamp = timestamp

    # Write final "End of Session" if there are measurements
    if session_measurements:
        weight_changes = []
        tumor_size_changes = []

        for m in session_measurements:
            initial_weight = baseline_measurements[m.rfid_assignment.animal.animal_index]['weight']
            initial_tumor_size = baseline_measurements[m.rfid_assignment.animal.animal_index]['tumor_size']
            weight_change = m.weight - initial_weight
            tumor_size_change = (m.tumor_size - initial_tumor_size) if initial_tumor_size is not None and m.tumor_size is not None else 0

            weight_changes.append(weight_change)
            if initial_tumor_size is not None and m.tumor_size is not None:
                tumor_size_changes.append(tumor_size_change)

        avg_weight_change = sum(weight_changes) / len(weight_changes) if weight_changes else 0
        avg_tumor_size_change = sum(tumor_size_changes) / len(tumor_size_changes) if tumor_size_changes else 0

        p.drawString(100, y_position, f"End of Session {current_session}")
        y_position -= 20
        p.drawString(100, y_position, f"Avg Weight Change: {avg_weight_change:.2f}g, Avg Tumor Size Change: {avg_tumor_size_change:.2f}mm")

    p.save()

    # Get the PDF data from the buffer
    buffer.seek(0)
    return HttpResponse(buffer, content_type='application/pdf')

@login_required
def download_pdf(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization=request.user.organization)  # Ensure experiment belongs to user's organization
    return generate_pdf_for_experiment(experiment)

@login_required
def delete_multiple_experiments(request):
    if request.method == 'POST':
        experiment_ids = request.POST.getlist('selected_experiments')
        experiments = Experiment.objects.filter(id__in=experiment_ids)
        experiments_count = experiments.count()
        experiments.delete()
        django_messages.success(request, f"Successfully deleted {experiments_count} experiments.")
    else:
        django_messages.error(request, "Invalid request")
    
    return redirect('all_experiments')  # Redirect back to the experiments page


@login_required
def experiment_settings(request, org_id, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization=request.user.organization)

    if request.method == 'POST':
        # Retrieve existing settings for comparison
        old_warning_weight_percentage = experiment.warning_weight_percentage
        old_removal_weight_percentage = experiment.removal_weight_percentage
        old_tumor_volume_warning = experiment.tumor_volume_warning
        old_tumor_volume_removal = experiment.tumor_volume_removal

        # Get new settings from the POST request
        warning_weight_percentage = float(request.POST.get('warning_weight_percentage'))
        removal_weight_percentage = float(request.POST.get('removal_weight_percentage'))
        tumor_volume_warning = float(request.POST.get('tumor_volume_warning'))
        tumor_volume_removal = float(request.POST.get('tumor_volume_removal'))

        # Track changes for notifications
        changes = []
        if warning_weight_percentage != old_warning_weight_percentage:
            changes.append(f"Warning Weight Percentage changed from {old_warning_weight_percentage}% to {warning_weight_percentage}%")
        if removal_weight_percentage != old_removal_weight_percentage:
            changes.append(f"Removal Weight Percentage changed from {old_removal_weight_percentage}% to {removal_weight_percentage}%")
        if tumor_volume_warning != old_tumor_volume_warning:
            changes.append(f"Tumor Warning Volume changed from {old_tumor_volume_warning} mm³ to {tumor_volume_warning} mm³")
        if tumor_volume_removal != old_tumor_volume_removal:
            changes.append(f"Tumor Removal Volume changed from {old_tumor_volume_removal} mm³ to {tumor_volume_removal} mm³")

        # Update the experiment settings
        experiment.warning_weight_percentage = warning_weight_percentage
        experiment.removal_weight_percentage = removal_weight_percentage
        experiment.tumor_volume_warning = tumor_volume_warning
        experiment.tumor_volume_removal = tumor_volume_removal
        experiment.save()

        # Notify collaborators if changes were made
        if changes:
            change_details = ", ".join(changes)
            notification_message = f"The following changes were made to the experiment '{experiment.name}': {change_details}."

            # Notify collaborators involved in the experiment
            collaborators = Collaborator.objects.filter(experiment=experiment).values_list('user', flat=True)
            for collaborator_id in collaborators:
                InboxNotification.objects.create(
                    user_id=collaborator_id,
                    experiment=experiment,
                    message=notification_message
                )

            django_messages.success(request, "Experiment settings updated successfully and notifications sent to collaborators.")
        else:
            django_messages.info(request, "No changes were made to the settings.")

        return redirect('experiment_home', experiment_id=experiment.id)

    return render(request, 'dashboard/settings.html', {
        'experiment': experiment,
        'org_id': org_id  # Pass org_id to the template
    })

@require_POST
@user_passes_test(is_admin_or_principal)
def end_experiment(request, org_id, experiment_id):
    logger.info(f"Received request to end experiment with ID {experiment_id} in organization {org_id}")
    
    try:
        organization = get_object_or_404(Organization, id=org_id)
        experiment = get_object_or_404(Experiment, id=experiment_id, organization=organization)

        experiment.ended = True
        experiment.save()
        logger.info(f"Experiment {experiment_id} successfully marked as ended.")
        
        # Delete associated calendar events
        CalendarEvent.objects.filter(experiment=experiment).delete()
        logger.info(f"Deleted calendar events for experiment {experiment_id}.")
        
        return JsonResponse({'status': 'success', 'message': 'Experiment ended successfully.'})
    except Exception as e:
        logger.error(f"Error ending experiment {experiment_id}: {e}")
        return JsonResponse({'status': 'error', 'message': f"Failed to end experiment: {str(e)}"}, status=500)
@login_required
@require_POST
def remove_animal(request, experiment_id, animal_index):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization=request.user.organization)  # Ensure experiment belongs to user's organization
    RFIDAssignment.objects.filter(experiment=experiment, animal__animal_index=animal_index).update(removed=True)
    return JsonResponse({'status': 'success', 'message': 'Animal removed successfully'})

def remove_animal_view(request, experiment_id, animal_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    animal = get_object_or_404(Animal, id=animal_id, experiment=experiment)

    # Call the remove method of the animal
    animal.remove()

    return JsonResponse({'status': 'success', 'message': 'Animal removed successfully'})

@login_required
def experiment_summary(request, experiment_id, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    experiment = get_object_or_404(Experiment, id=experiment_id)
    experiment_data = {
        'name': experiment.name,
        'number_of_animals': experiment.number_of_animals,
        'number_of_groups': experiment.number_of_groups,
        'investigators': experiment.investigators,
        # Remove or correct this line if measurement_items is not a valid field
        # 'measurement_items': experiment.measurement_items, 
        'rfid_required': 'Yes' if experiment.rfid_required else 'No',
        'max_per_cage': experiment.max_per_cage
    }
    return render(request, 'dashboard/summary.html', {'experiment_data': experiment_data, 'experiment_id': experiment_id, 'org_id': org_id })

def save_rfid_assignments(request, experiment_id):
    if request.method == 'POST':
        rfids = request.POST.getlist('rfids[]')
        for index, rfid in enumerate(rfids, start=1):
            animal = Animal.objects.get(experiment_id=experiment_id, animal_index=index, experiment__organization=request.user.organization)  # Check organization
            animal.rfid = rfid
            animal.save()
        return JsonResponse({"message": "RFIDs updated successfully"}, status=200)
    return JsonResponse({"error": "Invalid request"}, status=400)

