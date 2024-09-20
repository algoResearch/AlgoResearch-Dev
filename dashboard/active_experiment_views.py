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
from django.db import transaction
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io
import logging
import traceback

logger = logging.getLogger(__name__)




@login_required
def experiment_list(request):
    experiments = Experiment.objects.filter(Q(owner=request.user) | Q(collaborators__user=request.user), ended=False)
    return render(request, 'dashboard/all-experiments.html', {'experiments': experiments})

@login_required
def experiment_home(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    assignments = RFIDAssignment.objects.filter(experiment=experiment)

    healthy_count = 0
    at_risk_count = 0
    removal_count = 0

    for assignment in assignments:
        # Accessing the related Animal's animal_index
        animal = Animal.objects.filter(experiment=experiment, id=assignment.animal_id).first()

        if animal:
            latest_measurement = WeightMeasurement.objects.filter(animal=animal).order_by('-timestamp').first()

            if latest_measurement and assignment.initial_weight:
                # Calculate weight change percentage based on the initial weight
                weight_change_percentage = ((assignment.initial_weight - latest_measurement.weight) / assignment.initial_weight) * 100

                # Categorize based on the weight change percentage
                if weight_change_percentage < 15:
                    healthy_count += 1
                elif 15 <= weight_change_percentage < 20:
                    at_risk_count += 1
                else:
                    removal_count += 1

    context = {
        'experiment': experiment,
        'healthy_count': healthy_count,
        'at_risk_count': at_risk_count,
        'removal_count': removal_count,
        'collaborators': experiment.collaborators.all(),
    }

    return render(request, 'experiment-home.html', context)
@login_required
def map_rfid(request, experiment_id):
    # Fetch the experiment
    experiment = get_object_or_404(Experiment, id=experiment_id)

    # Fetch all assigned RFID numbers for this experiment
    assigned_rfids = RFIDAssignment.objects.filter(experiment=experiment).values('animal__animal_index', 'rfid', 'weight', 'tumor_size', 'cage_number')

    context = {
        'experiment': experiment,
        'assigned_rfids': list(assigned_rfids)  # Convert to list for easier handling in the template
    }

    return render(request, 'mapRFID.html', context)


@login_required
@csrf_exempt
def save_rfids(request, experiment_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            rfids_data = data.get('rfids')
            experiment = Experiment.objects.get(id=experiment_id, owner=request.user)
            
            with transaction.atomic():  # Ensure atomicity
                for item in rfids_data:
                    animal_index = item.get('animal_index')
                    rfid = item.get('rfid')

                    # Check if RFID is already assigned to another animal
                    if RFIDAssignment.objects.filter(rfid=rfid).exists():
                        return JsonResponse({'status': 'error', 'message': f'RFID {rfid} is already in use.'}, status=400)

                    # Update or create the animal with the new RFID
                    animal, created = Animal.objects.update_or_create(
                        experiment=experiment,
                        animal_index=animal_index,
                        defaults={'rfid_tag': rfid}
                    )

                    # Update or create the RFID assignment
                    RFIDAssignment.objects.update_or_create(
                        experiment=experiment,
                        animal=animal,
                        defaults={'rfid': rfid}
                    )
            return JsonResponse({'status': 'success'}, status=200)

        except IntegrityError as e:
            return JsonResponse({'status': 'error', 'message': 'Database integrity error: ' + str(e)}, status=500)
        except Experiment.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Experiment not found'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)
    
@login_required
@require_POST
def update_rfids(request, experiment_id):
    data = json.loads(request.body)
    rfid_assignments = data.get('rfid_assignments', [])

    with transaction.atomic():
        for assignment in rfid_assignments:
            animal_index = assignment['animal_index']
            rfid = assignment['rfid']

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


def get_rfids(request, experiment_id):
    if request.method == 'GET':
        try:
            animals = Animal.objects.filter(experiment_id=experiment_id).values('animal_index', 'rfid_tag', 'weight', 'tumor_size', 'cage_number')
            rfids = list(animals)  # Convert QuerySet to a list for easy serialization
            return JsonResponse({'rfids': rfids})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


@login_required
def cage_configuration(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)

    cages = {}
    assignments = RFIDAssignment.objects.filter(experiment=experiment, removed=False).order_by('animal__animal_index')

    for assignment in assignments:
        if assignment.cage_number not in cages:
            cages[assignment.cage_number] = []
        cages[assignment.cage_number].append(assignment)

    # Also fetch the removed animals for display under 'Past Animals'
    removed_animals = RFIDAssignment.objects.filter(experiment=experiment, removed=True).order_by('animal__animal_index')

    return render(request, 'cage-configuration.html', {
        'experiment': experiment,
        'cages': cages,
        'removed_animals': removed_animals,  # Send removed animals to the template
    })

@login_required
@require_POST
@csrf_exempt
def update_cage_configuration(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)

    try:
        data = json.loads(request.body)  # Get the cage configuration data from the request body
        cage_configuration = data.get('configuration', {})

        if not cage_configuration:
            return JsonResponse({'status': 'error', 'message': 'Invalid data format'}, status=400)

        # Update each cage and its animals
        for cage_number, animals in cage_configuration.items():
            for animal in animals:
                RFIDAssignment.objects.filter(
                    experiment=experiment,
                    rfid=animal['rfid'], 
                    animal__animal_index=animal['index']
                ).update(cage_number=cage_number)

        return JsonResponse({'status': 'success', 'message': 'Cage configuration updated'})

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
@require_POST
def update_cages(request, experiment_id):
    data = request.json['configuration']
    experiment = get_object_or_404(Experiment, id=experiment_id)

    for cage_number, animals in data.items():
        for animal in animals:
            RFIDAssignment.objects.filter(experiment=experiment, rfid=animal['rfid'], animal_index=animal['index']).update(cage_number=cage_number)

    return JsonResponse({"status": "Cage configuration updated"})

@csrf_exempt
def update_experiment(request, experiment_id):
    if request.method == 'PATCH':
        try:
            data = json.loads(request.body)
            rfid_assignments = data.get('rfid_assignments', [])
            experiment = get_object_or_404(Experiment, id=experiment_id)

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

            return JsonResponse({'status': 'success', 'message': 'RFID numbers updated successfully.'})

        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


@login_required
@require_POST
def delete_experiment(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, owner=request.user)
    experiment.ended = True
    experiment.save()

    CalendarEvent.objects.filter(experiment=experiment).delete()

    return JsonResponse({'status': 'Experiment deleted successfully'})

@login_required
def view_experiment(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    return render(request, 'view_experiment.html', {'experiment': experiment})


def get_rfid_assignments(request, experiment_id):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=403)

    try:
        experiment = Experiment.objects.get(id=experiment_id)
        assignments = RFIDAssignment.objects.filter(experiment=experiment).values('animal__animal_index', 'rfid')
        return JsonResponse({'rfids': list(assignments)})
    except Experiment.DoesNotExist:
        return JsonResponse({'error': 'Experiment not found'}, status=404)
    
@login_required
def all_experiments(request):
    # Get the current user
    user = request.user

    # Get sorting parameters from request
    sort_by = request.GET.get('sort_by', 'created_at')  # Default sort by date of creation
    order = request.GET.get('order', 'desc')  # Default order is descending

    # Get search query from request
    search_query = request.GET.get('search', '')

    # Filter active experiments based on search query and user involvement
    active_experiments = Experiment.objects.filter(
        ended=False
    ).filter(
        Q(name__icontains=search_query) |
        Q(drug_list__name__icontains=search_query) |
        Q(strain_list__name__icontains=search_query)
    ).filter(
        Q(owner=user) | Q(collaborators__user=user)  # Filter where user is the owner or a collaborator
    ).distinct()

    # Filter past experiments based on search query and user involvement
    past_experiments = Experiment.objects.filter(
        ended=True
    ).filter(
        Q(name__icontains=search_query) |
        Q(drug_list__name__icontains=search_query) |
        Q(strain_list__name__icontains=search_query)
    ).filter(
        Q(owner=user) | Q(collaborators__user=user)  # Filter where user is the owner or a collaborator
    ).distinct()

    # Sort experiments based on sort_by and order
    if order == 'asc':
        active_experiments = active_experiments.order_by(sort_by)
        past_experiments = past_experiments.order_by(sort_by)
    else:
        active_experiments = active_experiments.order_by(f'-{sort_by}')
        past_experiments = past_experiments.order_by(f'-{sort_by}')

    return render(request, 'all-experiments.html', {
        'active_experiments': active_experiments,
        'past_experiments': past_experiments,
        'search_query': search_query,
        'sort_by': sort_by,
        'order': order,
    })
@login_required
def get_active_experiment_count(request):
    user = request.user

    # Get the count of active experiments where the user is involved
    active_experiment_count = Experiment.objects.filter(
        ended=False
    ).filter(
        Q(owner=user) | Q(collaborators__user=user)
    ).distinct().count()

    return JsonResponse({'active_experiment_count': active_experiment_count})

@login_required
@require_POST
def delete_animal(request, experiment_id, animal_index):
    RFIDAssignment.objects.filter(experiment_id=experiment_id, animal_index=animal_index).update(removed=True)
    return JsonResponse({'status': 'Animal deleted successfully'})

def generate_pdf_for_experiment(experiment):
    # Create a BytesIO buffer to hold the PDF data
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Fetch measurements and order by timestamp
    measurements = WeightMeasurement.objects.filter(rfid_assignment__experiment=experiment).order_by('timestamp')

    # Initialize variables to store sessions and baseline measurements
    current_session = 1
    last_timestamp = None
    baseline_measurements = {}
    session_measurements = []

    # PDF content
    p.drawString(100, height - 100, f"Experiment {experiment.id} Data")
    y_position = height - 130  # Starting position for data rows

    p.drawString(100, y_position, "Session | Animal Index | Weight | Tumor Size | Timestamp")
    y_position -= 20  # Move down for next line

    for measurement in measurements:
        animal_index = measurement.rfid_assignment.animal.animal_index
        timestamp = measurement.timestamp

        # If this is the first row or a new session is detected
        if last_timestamp and (timestamp - last_timestamp).total_seconds() > 60:  # 60 seconds threshold for new session
            # Calculate averages and write them
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
                avg_weight_change = sum(weight_changes) / len(weight_changes)
                avg_tumor_size_change = (sum(tumor_size_changes) / len(tumor_size_changes)) if tumor_size_changes else 0

                # Write "End of Session" row and averages
                p.drawString(100, y_position, f"End of Session {current_session}")
                y_position -= 20
                p.drawString(100, y_position, f"Average Weight Change: {avg_weight_change}, Average Tumor Size Change: {avg_tumor_size_change}")
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
        p.drawString(100, y_position, f"{current_session} | {animal_index} | {measurement.weight} | {measurement.tumor_size if measurement.tumor_size else 'N/A'} | {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
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

        avg_weight_change = sum(weight_changes) / len(weight_changes)
        avg_tumor_size_change = (sum(tumor_size_changes) / len(tumor_size_changes)) if tumor_size_changes else 0

        p.drawString(100, y_position, f"End of Session {current_session}")
        y_position -= 20
        p.drawString(100, y_position, f"Average Weight Change: {avg_weight_change}, Average Tumor Size Change: {avg_tumor_size_change}")

    p.save()

    # Get the PDF data from the buffer
    buffer.seek(0)
    return HttpResponse(buffer, content_type='application/pdf')

@login_required
def download_pdf(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
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
def experiment_settings(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, owner=request.user)

    if request.method == 'POST':
        warning_weight_percentage = request.POST.get('warning_weight_percentage')
        removal_weight_percentage = request.POST.get('removal_weight_percentage')

        experiment.warning_weight_percentage = float(warning_weight_percentage)
        experiment.removal_weight_percentage = float(removal_weight_percentage)
        experiment.save()

        django_messages.success(request, "Experiment settings updated successfully.")
        return redirect('experiment_home', experiment_id=experiment.id)

    return render(request, 'settings.html', {'experiment': experiment})


@login_required
@require_POST
def end_experiment(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    experiment.ended = True
    experiment.save()

    # Delete associated calendar events
    CalendarEvent.objects.filter(experiment=experiment).delete()

    # Automatically download CSV
    return generate_pdf_for_experiment(experiment, request.user)


@login_required
@require_POST
def remove_animal(request, experiment_id, animal_index):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    RFIDAssignment.objects.filter(experiment=experiment, animal__animal_index=animal_index).update(removed=True)
    return JsonResponse({'status': 'success', 'message': 'Animal removed successfully'})

@login_required
def experiment_summary(request, experiment_id):
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
    return render(request, 'summary.html', {'experiment_data': experiment_data, 'experiment_id': experiment_id})


def save_rfid_assignments(request, experiment_id):
    if request.method == 'POST':
        rfids = request.POST.getlist('rfids[]')
        for index, rfid in enumerate(rfids, start=1):
            animal = Animal.objects.get(experiment_id=experiment_id, animal_index=index)
            animal.rfid = rfid
            animal.save()
        return JsonResponse({"message": "RFIDs updated successfully"}, status=200)
    return JsonResponse({"error": "Invalid request"}, status=400)
