from django.contrib import messages as django_messages
from django.core import serializers
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
import traceback
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from pprint import pprint
from django.db.models import Q, F, Avg, Max, Min, Count, Sum
from django.utils import timezone
import math
from math import pi
from .models import (Conversation, UserAction, Message, User, GroupMember, Group, Treatment, RFID, Task, Experiment, RFIDAssignment, WeightMeasurement, Collaborator, CalendarEvent, Comment, Friend, Cage, Animal, Sample, Dose, Observation, Comment, Strain, Organization)
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, authenticate
import pandas as pd
import numpy as np
from django.views.decorators.csrf import csrf_exempt
import random
from django.contrib.auth import logout
from django.db import IntegrityError, transaction
from .forms import CustomUserCreationForm, UpdateProfileForm, ExperimentForm, DataInputMethodForm, TumorSizeEntryForm
import json
from collections import defaultdict
from django.http import HttpResponseRedirect
from django.utils.safestring import mark_safe
from .forms import UserProfileForm
from .forms import ProfilePictureForm
from .forms import UpdateProfileForm, OverviewForm, ObservationForm, SampleForm, DoseForm
from django.views.decorators.http import require_http_methods
from django.utils.dateparse import parse_datetime
import csv
from .models import Invitation
from datetime import date, timedelta
from django.contrib import messages
import logging
import uuid
logger = logging.getLogger(__name__)

@login_required
@require_POST
def start_weighing_session(request, experiment_id):
    # Generate a new session ID for the weigh-in session
    new_session_id = str(uuid.uuid4())

    # Store the session ID and initialize session data
    request.session[f'current_session_id_{experiment_id}'] = new_session_id
    request.session[f'weighed_animals_{experiment_id}'] = []  # Clear previously weighed animals
    request.session[f'tumor_measured_animals_{experiment_id}'] = []
    

    print(f"Starting new weighing session with ID: {new_session_id}")
    return JsonResponse({'status': 'success', 'session_id': new_session_id})
@login_required
def reset_weigh_in_session(request, experiment_id):
    # Clear the session data for this experiment's weigh-in
    request.session[f'weighed_animals_{experiment_id}'] = []  # Reset the list of weighed animals
    return JsonResponse({'status': 'success'})
@login_required
@require_POST
def remove_animal(request, org_id, experiment_id, animal_id):
    organization = get_object_or_404(Organization, id=org_id)
    experiment = get_object_or_404(Experiment, id=experiment_id, organization=organization)

    try:
        # Fetch the animal and its assignment
        animal = get_object_or_404(Animal, id=animal_id, experiment=experiment)
        rfid_assignment = get_object_or_404(RFIDAssignment, experiment=experiment, animal=animal)

        # Remove the animal by updating status
        animal.removed = True
        animal.save()
        rfid_assignment.removed = True
        rfid_assignment.save()

        return JsonResponse({'status': 'success', 'message': f'Animal {animal_id} removed successfully.'})

    except Animal.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Animal not found.'}, status=404)
    except RFIDAssignment.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'RFID Assignment not found.'}, status=404)

    
def remove_animal_view(request, experiment_id, animal_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    animal = get_object_or_404(Animal, id=animal_id, experiment=experiment)

    # Call the remove method of the animal
    animal.remove()

    return JsonResponse({'status': 'success', 'message': 'Animal removed successfully'})


def data_collection(request, org_id, experiment_id):
    # Fetch experiment and groups within it
    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)
    groups = Group.objects.filter(experiment=experiment)

    # Initialize structures to hold animals by cage and unweighed animals
    animals_by_cage = defaultdict(list)
    unweighed_animals = []

    # Retrieve weighed animals from session
    weighed_animals = request.session.get(f'weighed_animals_{experiment_id}', [])
    logger.info(f"Currently weighed animals: {weighed_animals}")

    # Loop through each group and gather animals
    for group in groups:
        animals_in_group = Animal.objects.filter(group=group).order_by('animal_index')
        
        for animal in animals_in_group:
            # Initialize base animal data
            animal_data = {
                'id': animal.id,
                'animal_index': animal.animal_index,
                'rfid': animal.rfid_tag,
                'cage_number': 'N/A',  # Default to N/A if no cage number found
                'weight': 'N/A',
                'tumor_size': 'N/A',
                'tracking_date': 'N/A',
                'removed': animal.removed,
            }

            # Attempt to fetch RFID assignment and related measurements
            rfid_assignment = RFIDAssignment.objects.filter(animal=animal, experiment=experiment).first()
            if rfid_assignment:
                # Update cage number and tracking date if RFID assignment exists
                animal_data['cage_number'] = rfid_assignment.cage_number
                animal_data['tracking_date'] = rfid_assignment.initial_weight_date

                # Fetch latest measurements for this RFID assignment
                measurements = WeightMeasurement.objects.filter(rfid_assignment=rfid_assignment).order_by('timestamp')
                if measurements.exists():
                    last_measurement = measurements.last()
                    animal_data['weight'] = last_measurement.weight or 'N/A'
                    animal_data['tumor_size'] = last_measurement.tumor_size or 'N/A'
                    animal_data['tracking_date'] = last_measurement.timestamp.date() if last_measurement else 'N/A'

            # Add animal data to the cage grouping
            animals_by_cage[animal_data['cage_number']].append(animal_data)

            # Track unweighed animals based on session data
            if str(animal.animal_index) not in weighed_animals:
                unweighed_animals.append(animal_data)

    # Log data for debugging purposes
    logger.info(f"Unweighed animals: {unweighed_animals}")
    logger.info(f"Animals by cage: {dict(animals_by_cage)}")

    context = {
        'experiment': experiment,
        'animals_by_cage': dict(animals_by_cage),  # Convert defaultdict to regular dict for template compatibility
        'unweighed_animals': unweighed_animals,
        'org_id': org_id,
    }
    
    return render(request, 'data-collection.html', context)

def data_collection_view(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    if request.method == 'POST':
        form = DataInputMethodForm(request.POST)
        if form.is_valid():
            # Save the choice in the session or update the experiment setting
            request.session['input_method'] = form.cleaned_data['input_method']
            return redirect('data-collection', experiment_id=experiment_id)
    else:
        form = DataInputMethodForm()
    
    return render(request, 'data-collection.html', {'form': form, 'experiment': experiment})

@login_required
@require_POST
def end_weighing_session(request, org_id, experiment_id):
    # Clear the weighed animals for this experiment to reset the session
    request.session.pop(f'weighed_animals_{experiment_id}', None)  # Remove the list of weighed animals
    request.session.pop(f'current_session_id_{experiment_id}', None)  # Remove the session ID
    
    logger.info(f"Ending session for experiment {experiment_id} in organization {org_id}")
    return JsonResponse({'status': 'success', 'message': 'Session ended successfully.'})

@login_required
@require_POST
def save_data_collection(request, experiment_id):
    experiment = get_object_or_404(
        Experiment.objects.for_user(request.user).filter(
            Q(id=experiment_id) & (Q(owner=request.user) | Q(collaborators__user=request.user))
        )
    )

    try:
        # Parse incoming JSON data
        data = json.loads(request.body)
        animal_index = data.get('animal_index')
        weight = data.get('weight') if experiment.monitor_weight else None
        tumor_size = data.get('tumor_size') if experiment.monitor_tumor else None

        # Validate required fields based on monitoring options
        if not animal_index or (experiment.monitor_weight and weight is None):
            return JsonResponse({'status': 'error', 'message': 'Missing required fields.'}, status=400)

        # Convert animal index and measurements to correct data types
        animal_index = int(animal_index)
        weight = float(weight) if weight is not None else None
        tumor_size = float(tumor_size) if tumor_size is not None else None

        # Retrieve the RFID assignment for the animal that hasn't been removed
        rfid_assignment = RFIDAssignment.objects.for_user(request.user).get(
            experiment=experiment, animal__animal_index=animal_index, removed=False
        )

        # Retrieve the current session ID from session data
        current_session_id = request.session.get(f'current_session_id_{experiment_id}')
        if not current_session_id:
            return JsonResponse({'status': 'error', 'message': 'Session ID not found.'}, status=400)

        # Save the weight measurement and, if applicable, tumor size with the session ID
        measurement = WeightMeasurement.objects.create(
            rfid_assignment=rfid_assignment,
            animal=rfid_assignment.animal,
            weight=weight,
            tumor_size=tumor_size,
            recorder=request.user,
            timestamp=timezone.now(),
            session_id=current_session_id  # Use the session ID to link measurements
        )

        # Update the session data to mark this animal as weighed
        weighed_animals = request.session.get(f'weighed_animals_{experiment_id}', [])
        if animal_index not in weighed_animals:
            weighed_animals.append(animal_index)
        request.session[f'weighed_animals_{experiment_id}'] = weighed_animals

        # If tumor size monitoring is off, finalize the session after recording weight
        if not experiment.monitor_tumor:
            # Check if all animals have been weighed and mark the session as ended
            total_animals = Animal.objects.filter(experiment=experiment).count()
            if len(weighed_animals) >= total_animals:
                request.session.pop(f'current_session_id_{experiment_id}', None)
                return JsonResponse({'status': 'success', 'message': 'Session ended successfully after weight recording'})

            return JsonResponse({'status': 'success', 'message': 'Weight recorded successfully'})

        # If tumor size monitoring is enabled, proceed with normal operation
        return JsonResponse({'status': 'success', 'message': 'Data recorded successfully'})

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)
    except RFIDAssignment.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Animal not found or has been removed.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
@require_POST
def mark_animal_weighed(request, org_id, experiment_id):
    animal_index = request.POST.get('animal_index')
    
    if not animal_index:
        return JsonResponse({'status': 'error', 'message': 'Invalid animal index'}, status=400)
    
    # Update the session data
    weighed_animals = request.session.get('weighed_animals', set())
    weighed_animals.add(animal_index)
    request.session['weighed_animals'] = weighed_animals

    return JsonResponse({'status': 'success'})
    
@login_required
@require_POST
def simulate_scan(request, org_id, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)

    # Retrieve weighed animals from session
    weighed_animals = request.session.get(f'weighed_animals_{experiment_id}', [])
    tumor_measured_animals = request.session.get(f'tumor_measured_animals_{experiment_id}', []) if experiment.monitor_tumor else []

    # Log current session data for debugging
    print(f"Currently weighed animals: {weighed_animals}")

    # Find the next unweighed animal
    unmeasured_animals = RFIDAssignment.objects.filter(
        experiment=experiment,
        removed=False
    ).exclude(animal__animal_index__in=weighed_animals)

    # Filter for tumor monitoring if necessary
    if experiment.monitor_tumor:
        unmeasured_animals = unmeasured_animals.exclude(animal__animal_index__in=tumor_measured_animals)

    if not unmeasured_animals.exists():
        # End session if no animals left
        request.session.pop(f'weighed_animals_{experiment_id}', None)
        request.session.pop(f'tumor_measured_animals_{experiment_id}', None)
        request.session.pop(f'current_session_id_{experiment_id}', None)
        return JsonResponse({'status': 'session_ended', 'message': 'All animals have been measured. Session ended successfully.'})

    next_animal = unmeasured_animals.first()
    animal_index_str = str(next_animal.animal.animal_index)

    # Update session to mark the animal as weighed
    if experiment.monitor_weight and animal_index_str not in weighed_animals:
        weighed_animals.append(animal_index_str)
    if experiment.monitor_tumor and animal_index_str not in tumor_measured_animals:
        tumor_measured_animals.append(animal_index_str)

    # Save updated session data
    request.session[f'weighed_animals_{experiment_id}'] = weighed_animals
    if experiment.monitor_tumor:
        request.session[f'tumor_measured_animals_{experiment_id}'] = tumor_measured_animals

    # Log updated session data to confirm correct update
    print(f"Updated weighed animals: {weighed_animals}")

    return JsonResponse({
        'status': 'success',
        'animal_index': next_animal.animal.animal_index,
        'animal_id': next_animal.animal.id,
        'rfid': next_animal.rfid
    })

@login_required
@require_POST
def enter_weight(request, org_id, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)

    try:
        data = json.loads(request.body)
        animal_id = data.get("animal_id")
        weight = float(data.get("weight"))

        # Retrieve the animal and its RFID assignment
        animal = get_object_or_404(Animal, id=animal_id, experiment=experiment)
        rfid_assignment = RFIDAssignment.objects.filter(animal=animal, experiment=experiment).first()

        # Check if a recent entry with the same weight already exists (within 1 second)
        recent_time_threshold = timezone.now() - timedelta(seconds=1)
        existing_measurement = WeightMeasurement.objects.filter(
            rfid_assignment=rfid_assignment,
            animal=animal,
            weight=weight,
            timestamp__gte=recent_time_threshold
        ).exists()
        if existing_measurement:
            logger.info(f"Duplicate weight entry detected for animal ID {animal_id} with weight {weight}")
            return JsonResponse({'status': 'duplicate', 'message': 'Duplicate entry detected, not saved.'})
        # Set initial weight if not set
        if rfid_assignment.initial_weight is None:
            rfid_assignment.initial_weight = weight
            rfid_assignment.save()
            weight_loss_percentage = 0.0  # No weight loss if this is the initial weigh-in
        else:
            # Calculate weight loss percentage
            initial_weight = rfid_assignment.initial_weight
            weight_loss_percentage = ((initial_weight - weight) / initial_weight) * 100

        # Proceed with saving if no duplicate found
        WeightMeasurement.objects.create(
            rfid_assignment=rfid_assignment,
            animal=animal,
            weight=weight,
            recorder=request.user,
            timestamp=timezone.now()
        )
        logger.info(f"Weight measurement saved for animal ID {animal_id}: {weight}")

        # Check for warning/removal thresholds
        if weight_loss_percentage >= experiment.removal_weight_percentage:
            return JsonResponse({
                'status': 'removal',
                'message': f'Weight loss {weight_loss_percentage:.2f}% exceeds removal threshold.'
            })
        elif weight_loss_percentage >= experiment.warning_weight_percentage:
            return JsonResponse({
                'status': 'warning',
                'message': f'Weight loss {weight_loss_percentage:.2f}% exceeds warning threshold.'
            })

        return JsonResponse({'status': 'success', 'message': 'Weight recorded successfully'})

    except json.JSONDecodeError as e:
        logger.error(f"JSON decoding error: {e}")
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)
    except Exception as e:
        logger.error(f"Unexpected error in enter_weight: {str(e)}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An internal error occurred'}, status=500)

@login_required
@require_POST
def enter_tumor_size(request, org_id, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)

    try:
        data = json.loads(request.body)
        animal_id = data.get("animal_id")
        tumor_length = float(data.get("tumor_length", 0))
        tumor_width = float(data.get("tumor_width", 0))

        # Calculate tumor volume as an ellipsoid: (4/3) * π * (length/2) * (width/2)^2
        tumor_volume = (4 / 3) * math.pi * (tumor_length / 2) * (tumor_width / 2) ** 2

        # Round tumor volume to 2 decimal places
        tumor_volume = round(tumor_volume, 2)

        # Retrieve RFID assignment
        rfid_assignment = RFIDAssignment.objects.filter(animal_id=animal_id, experiment=experiment, removed=False).first()
        if not rfid_assignment:
            return JsonResponse({'status': 'error', 'message': 'RFID assignment not found.'}, status=404)

        # Save tumor measurement
        WeightMeasurement.objects.create(
            rfid_assignment=rfid_assignment,
            animal_id=animal_id,
            tumor_size=tumor_volume,
            recorder=request.user,
            timestamp=timezone.now()
        )

        # Threshold checks for tumor volume
        if experiment.tumor_volume_removal and tumor_volume >= experiment.tumor_volume_removal:
            return JsonResponse({'status': 'removal', 'message': f'Tumor volume {tumor_volume:.2f} mm³ exceeds removal threshold.'})
        elif experiment.tumor_volume_warning and tumor_volume >= experiment.tumor_volume_warning:
            return JsonResponse({'status': 'warning', 'message': f'Tumor volume warning: {tumor_volume:.2f} mm³ exceeds warning threshold.'})

        return JsonResponse({'status': 'success', 'message': 'Tumor size recorded successfully'})

    except (ValueError, TypeError) as e:
        return JsonResponse({'status': 'error', 'message': 'Invalid tumor length or width.'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': 'An internal error occurred'}, status=500)

@login_required
def vivarium_data_collection(request, org_id, cage_id):
    cage = get_object_or_404(Cage, id=cage_id, organization_id=org_id)
    
    # Retrieve only unassigned animals within this cage
    animals = cage.animals.filter(organization_id=org_id, experiment__isnull=True)  # Exclude animals assigned to any experiment
    
    # Structure data for unassigned animals by cage
    animals_by_cage = {
        cage.name: [
            {
                'id': animal.id,
                'animal_index': animal.animal_index,
                'rfid': animal.rfid_tag
            }
            for animal in animals
        ]
    }
    
    context = {
        'cage': cage,
        'animals_by_cage': animals_by_cage,
        'org_id': org_id,
    }
    return render(request, 'vivarium_data_collection.html', context)
@login_required
@require_POST
def vivarium_simulate_scan(request, org_id, cage_id):
    cage = get_object_or_404(Cage, id=cage_id, organization_id=org_id)

    # Retrieve weighed animals for this session in the current cage
    weighed_animals = request.session.get(f'weighed_animals_{cage_id}', [])

    # Filter only unassigned (experiment__isnull=True) and unweighed animals
    unweighed_available_animals = cage.animals.filter(
        organization_id=org_id,
        experiment__isnull=True  # Only unassigned animals
    ).exclude(id__in=weighed_animals)

    # If no unweighed available animals remain, end the session
    if not unweighed_available_animals.exists():
        request.session.pop(f'weighed_animals_{cage_id}', None)
        return JsonResponse({
            'status': 'session_ended',
            'message': 'All available animals have been weighed. Session ended successfully.'
        })

    # Select the next available animal for scanning
    next_animal = unweighed_available_animals.first()

    # Mark this animal as weighed in the session
    weighed_animals.append(next_animal.id)
    request.session[f'weighed_animals_{cage_id}'] = weighed_animals

    # Respond with details of the next animal for the front end
    return JsonResponse({
        'status': 'success',
        'animal_id': next_animal.id,
        'animal_index': next_animal.animal_index,
        'rfid': next_animal.rfid_tag
    })

@login_required
@require_POST
def vivarium_enter_weight(request, org_id):
    data = json.loads(request.body)
    animal_id = data.get("animal_id")
    weight = data.get("weight")

    # Process data without requiring an experiment ID
    animal = get_object_or_404(Animal, id=animal_id, organization_id=org_id)
    
    # Save the weight measurement
    if weight:
        WeightMeasurement.objects.create(
            animal=animal,
            weight=weight,
            timestamp=timezone.now(),
            recorder=request.user
        )
    return JsonResponse({'status': 'success', 'message': 'Weight recorded successfully'})
@login_required
@require_POST
def vivarium_enter_tumor_size(request, org_id):
    data = json.loads(request.body)
    animal_id = data.get("animal_id")
    tumor_size = data.get("tumor_size")  # Already calculated volume

    animal = get_object_or_404(Animal, id=animal_id, organization_id=org_id)
    
    if tumor_size:
        # Save the tumor size (volume)
        WeightMeasurement.objects.create(
            animal=animal,
            tumor_size=tumor_size,
            timestamp=timezone.now(),
            recorder=request.user
        )
    return JsonResponse({'status': 'success', 'message': 'Tumor size recorded successfully'})

@login_required
def get_animal_analytics(request, org_id, experiment_id, animal_id):
    metric = request.GET.get('metric', 'weight')  # Default to 'weight' if no metric is provided

    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)
    animal = get_object_or_404(Animal, id=animal_id, experiment=experiment)

    # Initialize lists for weights and tumor_sizes
    weights, tumor_sizes, dates = [], [], []

    if metric == 'weight':
        # Retrieve only weight measurements
        weight_measurements = WeightMeasurement.objects.filter(
            animal=animal, rfid_assignment__experiment=experiment
        ).exclude(weight__isnull=True).order_by('timestamp')

        weights = [measurement.weight for measurement in weight_measurements]
        dates = [measurement.timestamp.strftime('%Y-%m-%d') for measurement in weight_measurements]
        
    elif metric == 'tumor':
        # Retrieve only tumor measurements
        tumor_measurements = WeightMeasurement.objects.filter(
            animal=animal, rfid_assignment__experiment=experiment
        ).exclude(tumor_size__isnull=True).order_by('timestamp')

        tumor_sizes = [measurement.tumor_size for measurement in tumor_measurements]
        dates = [measurement.timestamp.strftime('%Y-%m-%d') for measurement in tumor_measurements]

    return JsonResponse({
        'success': True,
        'dates': dates,
        'weights': weights,
        'tumor_sizes': tumor_sizes
    })

def animal_analytics(request, org_id, experiment_id, animal_id):
    try:
        logger.info(f"Fetching analytics for Animal ID: {animal_id}, Experiment ID: {experiment_id}")

        animal_data = Animal.objects.get(id=animal_id)
        weight_measurements = WeightMeasurement.objects.filter(animal=animal_data).order_by('timestamp')

        # Convert date to string for JSON compatibility
        dates = [measurement.timestamp.date().isoformat() for measurement in weight_measurements]
        weights = [measurement.weight for measurement in weight_measurements]
        tumor_sizes = [measurement.tumor_size for measurement in weight_measurements if measurement.tumor_size is not None]

        # Log the data being sent to the frontend
        response_data = {
            'success': True,
            'dates': dates,
            'weights': weights,
            'tumor_sizes': tumor_sizes,
        }
        logger.info(response_data)

        return JsonResponse(response_data)

    except Animal.DoesNotExist:
        logger.error(f"Animal with ID {animal_id} not found.")
        return JsonResponse({'success': False, 'message': 'Animal not found.'}, status=404)
    except Exception as e:
        logger.error(f"Error fetching analytics for Animal ID {animal_id}: {str(e)}")
        return JsonResponse({'success': False, 'message': str(e)}, status=500)
    
@login_required
def studies_view(request, org_id):
    # Get the logged-in user
    user = request.user

    # Fetch distinct strains associated with experiments where the user is the owner or a collaborator within the organization
    strains = Strain.objects.filter(
        Q(experiment__owner=user) | Q(experiment__collaborators__user=user),
        experiment__organization_id=org_id
    ).distinct()

    # Prepare a dictionary to hold strain names and their associated experiments and drugs
    strain_experiments = {}

    for strain in strains:
        strain_name = strain.name

        # Fetch experiments related to this strain where the user is involved, within the organization
        experiments = Experiment.objects.filter(
            strain_list=strain,
            organization_id=org_id  # Filtering by organization
        ).filter(
            Q(owner=user) | Q(collaborators__user=user)
        ).distinct()

        # Prepare a list to hold the experiment and drug details
        if strain_name not in strain_experiments:
            strain_experiments[strain_name] = []

        for experiment in experiments:
            # Fetch the drugs related to this experiment
            drugs = experiment.drug_list.all()

            # Collect experiment details with associated drugs
            strain_experiments[strain_name].append({
                'experiment': experiment,
                'drugs': drugs
            })

    # Handle strain deletion if necessary
    if request.method == 'POST':
        strain_name = request.POST.get('strain_to_delete')
        try:
            strain_to_delete = Strain.objects.get(name=strain_name)
            # Ensure only the user involved can delete the strain
            if Experiment.objects.filter(strain_list=strain_to_delete, owner=user).exists() or \
                    Experiment.objects.filter(strain_list=strain_to_delete, collaborators__user=user).exists():
                strain_to_delete.delete()
                messages.success(request, f'Strain "{strain_to_delete.name}" deleted successfully.')
            else:
                messages.error(request, 'You do not have permission to delete this strain.')
        except Strain.DoesNotExist:
            messages.error(request, 'Strain not found.')
        except Exception as e:
            messages.error(request, f'Error deleting strain: {str(e)}')

    context = {
        'strain_experiments': strain_experiments,
        'org_id': org_id,
    }

    return render(request, 'Studies.html', context)
@login_required
@csrf_exempt
def delete_strain(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            strain_name = data.get('strain_name')

            # Fetch and delete all strains with the given name
            strains = Strain.objects.filter(name=strain_name)
            if strains.exists():
                strains.delete()  # Deletes all matching strains
                return JsonResponse({'success': True, 'message': f'Successfully deleted strains with name {strain_name}.'})
            else:
                return JsonResponse({'success': False, 'message': f'No strain found with the name {strain_name}.'})

        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': 'Invalid request method.'})


@login_required
def strain_analytics(request, org_id, strain_name):
    organization = get_object_or_404(Organization, id=org_id)

    # Filter strains by experiments within the user's organization
    strains = Strain.objects.filter(name=strain_name, experiment__organization=organization).distinct()
    
    if not strains.exists():
        raise Http404(f"No Strains found with the name {strain_name}")

    # Filter experiments for the user and organization
    experiments = Experiment.objects.for_user(request.user).filter(
        strain_set__in=strains,
        organization=organization  # Ensure the experiment belongs to the correct organization
    ).distinct()

    experiment_data = {}

    for experiment in experiments:
        drugs = experiment.drug_set.all()

        for drug in drugs:
            drug_name = drug.name
            if drug_name not in experiment_data:
                experiment_data[drug_name] = {
                    'average_weight_changes': [],
                    'average_tumor_size_changes': [],
                    'weigh_in_numbers': []
                }

            # Fetch measurements and order by timestamp
            measurements = WeightMeasurement.objects.filter(rfid_assignment__experiment=experiment).order_by('timestamp')

            current_session = 1
            last_timestamp = None
            baseline_measurements = {}
            session_measurements = []
            session_data = []

            # Process measurements by session
            for measurement in measurements:
                animal_index = measurement.rfid_assignment.animal.animal_index
                timestamp = measurement.timestamp

                if last_timestamp and (timestamp - last_timestamp).total_seconds() > 60:
                    if session_measurements:
                        weight_percentage_changes = []
                        tumor_size_percentage_changes = []

                        for m in session_measurements:
                            initial_weight = baseline_measurements[m.rfid_assignment.animal.animal_index]['weight']
                            initial_tumor_size = baseline_measurements[m.rfid_assignment.animal.animal_index]['tumor_size']
                            
                            # Calculate weight percentage change
                            if initial_weight != 0:  # Avoid division by zero
                                weight_percentage_change = ((m.weight - initial_weight) / initial_weight) * 100
                                weight_percentage_changes.append(weight_percentage_change)
                            
                            # Calculate tumor size percentage change if applicable
                            if initial_tumor_size and m.tumor_size and initial_tumor_size != 0:
                                tumor_size_percentage_change = ((m.tumor_size - initial_tumor_size) / initial_tumor_size) * 100
                                tumor_size_percentage_changes.append(tumor_size_percentage_change)

                        avg_weight_percentage_change = sum(weight_percentage_changes) / len(weight_percentage_changes) if weight_percentage_changes else 0
                        avg_tumor_size_percentage_change = sum(tumor_size_percentage_changes) / len(tumor_size_percentage_changes) if tumor_size_percentage_changes else 0

                        session_data.append({
                            'weigh_in_number': current_session,
                            'avg_weight_change': avg_weight_percentage_change,
                            'avg_tumor_size_change': avg_tumor_size_percentage_change
                        })

                    current_session += 1
                    session_measurements = []

                session_measurements.append(measurement)

                if animal_index not in baseline_measurements:
                    baseline_measurements[animal_index] = {
                        'weight': measurement.weight,
                        'tumor_size': measurement.tumor_size
                    }

                last_timestamp = timestamp

            # Final session processing
            if session_measurements:
                weight_percentage_changes = []
                tumor_size_percentage_changes = []

                for m in session_measurements:
                    initial_weight = baseline_measurements[m.rfid_assignment.animal.animal_index]['weight']
                    initial_tumor_size = baseline_measurements[m.rfid_assignment.animal.animal_index]['tumor_size']
                    
                    if initial_weight != 0:
                        weight_percentage_change = ((m.weight - initial_weight) / initial_weight) * 100
                        weight_percentage_changes.append(weight_percentage_change)
                    
                    if initial_tumor_size and m.tumor_size and initial_tumor_size != 0:
                        tumor_size_percentage_change = ((m.tumor_size - initial_tumor_size) / initial_tumor_size) * 100
                        tumor_size_percentage_changes.append(tumor_size_percentage_change)

                avg_weight_percentage_change = sum(weight_percentage_changes) / len(weight_percentage_changes) if weight_percentage_changes else 0
                avg_tumor_size_percentage_change = sum(tumor_size_percentage_changes) / len(tumor_size_percentage_changes) if tumor_size_percentage_changes else 0

                session_data.append({
                    'weigh_in_number': current_session,
                    'avg_weight_change': avg_weight_percentage_change,
                    'avg_tumor_size_change': avg_tumor_size_percentage_change
                })

            experiment_data[drug_name]['average_weight_changes'] = [session['avg_weight_change'] for session in session_data]
            experiment_data[drug_name]['average_tumor_size_changes'] = [session['avg_tumor_size_change'] for session in session_data]
            experiment_data[drug_name]['weigh_in_numbers'] = [session['weigh_in_number'] for session in session_data]

    context = {
        'strain_name': strain_name,
        'experiment_data': experiment_data,
        'org_id': org_id  # Ensure org_id is passed to the template for links
    }

    return render(request, 'strain_analytics.html', context)



@login_required
def analytics(request, org_id, experiment_id):
    organization = get_object_or_404(Organization, id=org_id)
    experiment = get_object_or_404(Experiment.objects.for_user(request.user), id=experiment_id, organization=organization)
    # Retrieve animals and their group information
    animals = RFIDAssignment.objects.for_user(request.user).filter(experiment=experiment).select_related('animal__group')
    weight_measurements = WeightMeasurement.objects.filter(rfid_assignment__experiment=experiment).order_by('timestamp')
    
    # Organize data by groups and animals
    chart_data = {}
    group_data = {}
    weight_changes = []
    tumor_growth_rates = []

    for wm in weight_measurements:
        animal_index = wm.rfid_assignment.animal.animal_index
        group = wm.rfid_assignment.animal.group
        group_name = group.name if group else 'Ungrouped'
        group_color = group.color if group else '#CCCCCC'

        # Initialize data structures for each animal and group
        if animal_index not in chart_data:
            chart_data[animal_index] = {
                'dates': [],
                'weights': [],
                'tumor_sizes': [],
                'group_name': group_name,
                'color': group_color
            }
        if group_name not in group_data:
            group_data[group_name] = {
                'dates': [],
                'weights': [],
                'tumor_sizes': [],
                'color': group_color
            }

        # Append data for each animal
        chart_data[animal_index]['dates'].append(wm.timestamp.strftime('%Y-%m-%d'))
        chart_data[animal_index]['weights'].append(wm.weight if wm.weight is not None else None)
        chart_data[animal_index]['tumor_sizes'].append(wm.tumor_size if wm.tumor_size is not None else None)

        # Calculate group averages
        group_data[group_name]['dates'].append(wm.timestamp.strftime('%Y-%m-%d'))
        group_data[group_name]['weights'].append(wm.weight)
        group_data[group_name]['tumor_sizes'].append(wm.tumor_size)

    # Compute averages for each group
    for group_name, data in group_data.items():
        weight_averages = []
        tumor_size_averages = []

        dates = sorted(set(data['dates']))
        for date in dates:
            weights = [weight for i, weight in enumerate(data['weights']) if data['dates'][i] == date and weight is not None]
            tumor_sizes = [size for i, size in enumerate(data['tumor_sizes']) if data['dates'][i] == date and size is not None]

            weight_averages.append(sum(weights) / len(weights) if weights else None)
            tumor_size_averages.append(sum(tumor_sizes) / len(tumor_sizes) if tumor_sizes else None)

        group_data[group_name] = {
            'dates': dates,
            'weights': weight_averages,
            'tumor_sizes': tumor_size_averages,
            'color': data['color']
        }

    # Prepare data for correlation heatmap, filtering out None values
    for animal_id, data in chart_data.items():
        weight_values = np.array([w for w in data['weights'] if w is not None], dtype=np.float64)
        tumor_values = np.array([t for t in data['tumor_sizes'] if t is not None], dtype=np.float64)
        
        # Calculate percentage changes for weight and tumor size
        if len(weight_values) > 1 and len(tumor_values) > 1:
            weight_change = np.diff(weight_values) / weight_values[:-1] * 100  # % change
            tumor_growth_rate = np.diff(tumor_values) / tumor_values[:-1] * 100  # % growth rate
            
            weight_changes.extend(weight_change)
            tumor_growth_rates.extend(tumor_growth_rate)

    # Create correlation data using pandas
    if weight_changes and tumor_growth_rates:
        df = pd.DataFrame({'Weight Change (%)': weight_changes, 'Tumor Growth Rate (%)': tumor_growth_rates})
        correlation_matrix = df.corr().round(2)  # Compute correlation and round to 2 decimals
        correlation_data = correlation_matrix.values.tolist()
    else:
        correlation_data = [[1, 0], [0, 1]]  # Default values if no valid data exists

    # Convert data to JSON for JavaScript
    chart_data_json = mark_safe(json.dumps(chart_data))
    group_data_json = mark_safe(json.dumps(group_data))
    correlation_data_json = mark_safe(json.dumps(correlation_data))

    return render(request, 'analytics.html', {
        'experiment': experiment,
        'chart_data': chart_data_json,
        'group_data': group_data_json,
        'correlation_data': correlation_data_json
    })

@csrf_exempt  # You can adjust this based on your CSRF strategy
@login_required
def save_rfids(request, org_id, experiment_id):
    if request.method == 'POST':
        experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)
        
        data = json.loads(request.body)
        rfids = data.get('rfids', [])

        # Keep track of already assigned RFIDs within this experiment
        assigned_rfids = set(RFIDAssignment.objects.filter(experiment=experiment).values_list('rfid', flat=True))

        with transaction.atomic():
            for rfid_data in rfids:
                animal_index = rfid_data.get('animal_index')
                rfid_value = rfid_data.get('rfid')

                # Skip the RFID if it's already assigned within this experiment
                if rfid_value in assigned_rfids:
                    continue  # Skip duplicates within this batch to prevent the IntegrityError

                # Fetch the animal by its index within the experiment
                animal = get_object_or_404(Animal, experiment=experiment, animal_index=animal_index)

                # Update or create the RFIDAssignment for the animal
                try:
                    RFIDAssignment.objects.update_or_create(
                        experiment=experiment, 
                        animal=animal,
                        defaults={'rfid': rfid_value}
                    )
                    
                    # Mark RFID as used by adding it to the assigned set
                    assigned_rfids.add(rfid_value)

                    # Update the RFID in the RFID model to mark it as assigned
                    RFID.objects.filter(rfid=rfid_value).update(assigned=True)

                except IntegrityError:
                    # If there's a duplicate entry, log the error and skip this RFID
                    continue

        return JsonResponse({'status': 'success', 'message': 'RFID assignments saved successfully'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)
    