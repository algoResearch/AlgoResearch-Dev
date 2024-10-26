from django.contrib import messages as django_messages
from django.core import serializers
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.core.paginator import Paginator
from django.db.models import Q, F, Avg, Max, Min, Count, Prefetch
from django.utils import timezone
from .models import (Conversation, Message, User, GroupMember, Group, Experiment, RFIDAssignment, WeightMeasurement, Collaborator, CalendarEvent, Comment, Friend, Cage, Animal, Sample, Dose, Observation, Comment)
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, authenticate
import pandas as pd
from collections import defaultdict
from django.views.decorators.csrf import csrf_exempt
import random
from django.core.cache import cache
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

import json
from django.contrib import messages


from .models import Experiment, Animal, Comment, WeightMeasurement, Sample, Dose, Observation
import logging


logger = logging.getLogger(__name__)


@login_required
@csrf_exempt
def add_comment(request, experiment_id, animal_index):
    if request.method == 'POST':
        comment_text = request.POST.get('comment') or json.loads(request.body).get('comment')
        if comment_text:
            Comment.objects.create(
                experiment = get_object_or_404(Experiment, id=experiment_id, organization=request.user.organization),
                animal = get_object_or_404(Animal, experiment=experiment, animal_index=animal_index),
                user=request.user,
                content=comment_text
            )
            return JsonResponse({'status': 'success', 'message': 'Comment added successfully!'})
        else:
            return JsonResponse({'status': 'error', 'message': 'Comment text cannot be empty.'})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})

def animal_details_view(request, org_id, experiment_id, animal_index):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)
    animal = get_object_or_404(Animal, experiment=experiment, animal_index=animal_index)
    observations = animal.observations.all()
    weights = WeightMeasurement.objects.filter(experiment_id=experiment_id, animal_index=animal_index).order_by('timestamp')
    samples = Sample.objects.filter(animal=animal)
    doses = Dose.objects.filter(animal=animal)

    context = {
        'animal': animal,
        'observations': observations,
        'weights': weights,
        'samples': samples,
        'doses': doses,
        'org_id': org_id,
    }
    return render(request, 'animal_details.html', context)

@login_required
def save_observations(request, animal_id):
    if request.method == 'POST':
        animal = get_object_or_404(Animal, id=animal_id, experiment__organization=request.user.organization)
        data = json.loads(request.body)
        observations = data.get('observations', [])
        
        # Update observations logic
        for obs in observations:
            # Assuming you want to update existing observations by their name
            observation, created = Observation.objects.update_or_create(
                animal=animal,
                name=obs['name'],
                defaults={'score': obs['score']}
            )
        
        return JsonResponse({'success': True})

    return JsonResponse({'success': False, 'message': 'Invalid request method'})

@login_required
def save_sample(request, animal_id):
    if request.method == 'POST':
        animal = get_object_or_404(Animal, id=animal_id, experiment__organization=request.user.organization)
        data = json.loads(request.body)
        sample_data = data.get('sample', {})

        # Update or create the sample
        if sample_data.get('sample_id') and sample_data.get('sample_type'):
            sample, created = Sample.objects.update_or_create(
                animal=animal,
                sample_id=sample_data['sample_id'],
                defaults={'sample_type': sample_data['sample_type']}
            )
            return JsonResponse({'success': True, 'message': 'Sample saved successfully'})
        else:
            return JsonResponse({'success': False, 'message': 'Missing required fields'})

    return JsonResponse({'success': False, 'message': 'Invalid request method'})
@login_required
def save_dose(request, animal_id):
    if request.method == 'POST':
        animal = get_object_or_404(Animal, id=animal_id, experiment__organization=request.user.organization)
        data = json.loads(request.body)
        dose_data = data.get('dose', {})

        # Validate necessary fields are present
        required_fields = ['drug_name', 'dose', 'stock_concentration', 'dose_volume']
        if all(key in dose_data for key in required_fields):
            dose, created = Dose.objects.update_or_create(
                animal=animal,
                drug_name=dose_data['drug_name'],
                defaults={
                    'dose': dose_data['dose'],
                    'stock_concentration': dose_data['stock_concentration'],
                    'dose_volume': dose_data['dose_volume']
                }
            )
            return JsonResponse({'success': True, 'message': 'Dose saved successfully'})
        else:
            return JsonResponse({'success': False, 'message': 'Missing required fields'})

    return JsonResponse({'success': False, 'message': 'Invalid request method'})


@login_required
def add_sample(request, org_id, experiment_id, animal_index):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)
    animal = get_object_or_404(Animal, experiment=experiment, animal_index=animal_index)
    if request.method == 'POST':
        form = SampleForm(request.POST)
        if form.is_valid():
            sample = form.save(commit=False)
            sample.experiment = experiment
            sample.animal = animal
            sample.user = request.user
            sample.save()
            return redirect('animal_details', experiment_id=experiment.id, animal_index=animal.animal_index)
    else:
        form = SampleForm()

    context = {
        'experiment': experiment,
        'animal': animal,
        'form': form,
        'org_id': org_id,
    }
    return render(request, 'add_sample.html', context)
@login_required
def add_dose(request, org_id, experiment_id, animal_index):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)
    animal = get_object_or_404(Animal, experiment=experiment, animal_index=animal_index)

    if request.method == 'POST':
        form = DoseForm(request.POST)
        if form.is_valid():
            dose = form.save(commit=False)
            dose.experiment = experiment
            dose.animal = animal
            dose.user = request.user
            dose.save()
            return redirect('animal_details', org_id = org_id, experiment_id=experiment.id, animal_index=animal.animal_index)
    else:
        form = DoseForm()

    context = {
        'experiment': experiment,
        'animal': animal,
        'form': form,
        'org_id': org_id,
    }
    return render(request, 'add_dose.html', context)

def animals(request, experiment_id, org_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)
    groups = Group.objects.filter(experiment=experiment)

    # Initialize a dictionary to hold groups and their animals
    grouped_animals_data = defaultdict(list)

    # Loop through each group and gather animals
    for group in groups:
        # Get all animals in the current group
        animals_in_group = Animal.objects.filter(group=group).order_by('animal_index')

        for animal in animals_in_group:
            # Initialize base animal data
            animal_data = {
                'animal_index': animal.animal_index,
                'cage_number': 'N/A',
                'weight': 'N/A',
                'tumor_size': 'N/A',
                'tracking_date': 'N/A',
                'weight_change_first': None,
                'tumor_size_change_first': None,
            }

            # Attempt to fetch RFID assignment and related measurements
            rfid_assignment = RFIDAssignment.objects.filter(animal=animal, experiment=experiment).first()
            if rfid_assignment:
                # Update cage number and tracking date if RFID assignment exists
                animal_data['cage_number'] = rfid_assignment.cage_number
                animal_data['tracking_date'] = rfid_assignment.initial_weight_date

                # Fetch measurements for this RFID assignment
                measurements = WeightMeasurement.objects.filter(rfid_assignment=rfid_assignment).order_by('timestamp')
                if measurements.exists():
                    first_measurement = measurements.first()
                    last_measurement = measurements.last()

                    # Update weight and tumor size from the latest measurement
                    animal_data['weight'] = last_measurement.weight if last_measurement.weight is not None else 'N/A'
                    animal_data['tumor_size'] = last_measurement.tumor_size if last_measurement.tumor_size is not None else 'N/A'

                    # Calculate changes in weight and tumor size from the first to the latest measurement
                    if first_measurement and last_measurement:
                        animal_data['weight_change_first'] = (
                            last_measurement.weight - first_measurement.weight
                            if first_measurement.weight is not None and last_measurement.weight is not None
                            else None
                        )
                        animal_data['tumor_size_change_first'] = (
                            last_measurement.tumor_size - first_measurement.tumor_size
                            if first_measurement.tumor_size is not None and last_measurement.tumor_size is not None
                            else None
                        )

            # Append the animal data to the group in grouped_animals_data
            grouped_animals_data[group.name].append(animal_data)

    context = {
        'experiment': experiment,
        'grouped_animals_data': dict(grouped_animals_data),  # Convert to a regular dictionary for easier template handling
        'org_id': org_id,
    }

    return render(request, 'animals.html', context)

def animal_details(request, org_id, experiment_id, animal_index):
    # Fetch the experiment based on organization ID and experiment ID
    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)
    
    # Fetch the specific animal within that experiment
    animal = get_object_or_404(Animal, experiment=experiment, animal_index=animal_index)
    
    # Get the RFID assignment and weigh-ins for the animal
    rfid_assignment = RFIDAssignment.objects.filter(animal=animal).first()
    weigh_ins = WeightMeasurement.objects.filter(animal=animal).order_by('timestamp')

    # Prepare data for rendering
    dates = [weigh_in.timestamp.strftime("%Y-%m-%d") for weigh_in in weigh_ins]
    weights = [weigh_in.weight for weigh_in in weigh_ins]
    tumor_sizes = [weigh_in.tumor_size for weigh_in in weigh_ins if weigh_in.tumor_size is not None]
    drugs = animal.drugs.all()
    strains = animal.strains.all()

    # Check if RFID assignment exists
    if rfid_assignment:
        rfid_tag = rfid_assignment.rfid
    else:
        rfid_tag = "RFID Not Assigned"

    context = {
        'animal': animal,
        'rfid_tag': rfid_tag,
        'drugs': drugs,
        'strains': strains,
        'dates': dates,
        'weights': weights,
        'tumor_sizes': tumor_sizes,
        'experiment': experiment,
        'observations': animal.observations.all(),
        'samples': animal.samples.all(),
        'doses': animal.doses.all(),
        'org_id': org_id  # Ensure org_id is passed to the template
    }

    return render(request, 'animal_details.html', context)

@login_required
def add_observation(request, experiment_id, org_id, animal_index):
    # Fetch the relevant experiment and animal
    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)
    animal = get_object_or_404(Animal, experiment=experiment, animal_index=animal_index)

    if request.method == 'POST':
        form = ObservationForm(request.POST)
        if form.is_valid():
            observation = form.save(commit=False)
            observation.animal = animal
            observation.user = request.user
            observation.save()
            return redirect('animal_details', org_id=org_id,experiment_id=experiment.id, animal_index=animal.animal_index)
    else:
        form = ObservationForm()

    context = {
        'experiment': experiment,
        'animal': animal,
        'form': form,
        'org_id': org_id,
    }

    return render(request, 'add_observation.html', context)

# Overview View
def overview_view(request, experiment_id, animal_index):
    animal = get_object_or_404(Animal, experiment_id=experiment_id, animal_index=animal_index)

    if request.method == 'POST':
        # Save the updated overview details
        animal.tail = request.POST.get('tail', animal.tail)
        animal.ear = request.POST.get('ear', animal.ear)
        animal.tag = request.POST.get('tag', animal.tag)
        animal.donor = request.POST.get('donor', animal.donor)
        animal.sex = request.POST.get('sex', animal.sex)
        animal.species = request.POST.get('species', animal.species)
        animal.strain = request.POST.get('strain', animal.strain)
        animal.drug = request.POST.get('drug', animal.drug)
        animal.save()

        messages.success(request, 'Overview updated successfully.')
        return redirect('overview', experiment_id=experiment_id, animal_index=animal_index)

    return render(request, 'overview.html', {'animal': animal})


# Observations View
def observations_view(request, experiment_id, animal_index):
    animal = get_object_or_404(Animal, experiment_id=experiment_id, animal_index=animal_index)
    observations = animal.observations.all()  # Assuming related_name='observations' in the ForeignKey

    if request.method == 'POST':
        # Process form data to update observations
        # Example: Save new observation
        observation_name = request.POST.get('observation_name')
        observation_score = request.POST.get('observation_score')
        if observation_name and observation_score:
            Observation.objects.create(
                animal=animal,
                name=observation_name,
                score=observation_score,
                user=request.user  # assuming the current user is recording
            )
            messages.success(request, 'Observation added successfully.')
        return redirect('observations', experiment_id=experiment_id, animal_index=animal_index)

    return render(request, 'observations.html', {'animal': animal, 'observations': observations})


# Analytics View
def analytics_view(request, experiment_id, animal_index):
    animal = get_object_or_404(Animal, experiment_id=experiment_id, animal_index=animal_index)
    weights = WeightMeasurement.objects.filter(experiment_id=experiment_id, animal_index=animal_index).order_by('timestamp')

    return render(request, 'analytics.html', {'animal': animal, 'weights': weights})


# Samples View
def samples_view(request, experiment_id, animal_index):
    animal = get_object_or_404(Animal, experiment_id=experiment_id, animal_index=animal_index)
    samples = Sample.objects.filter(animal=animal)

    return render(request, 'samples.html', {'animal': animal, 'samples': samples})


# Dosing View
def dosing_view(request, experiment_id, animal_index):
    animal = get_object_or_404(Animal, experiment_id=experiment_id, animal_index=animal_index)
    doses = Dose.objects.filter(animal=animal)

    return render(request, 'dosing.html', {'animal': animal, 'doses': doses})

@login_required
@csrf_exempt
def update_overview(request, experiment_id, animal_index):
    if request.method == 'POST':
        try:
            # Retrieve the animal object using experiment_id and animal_index
            animal = get_object_or_404(Animal, experiment_id=experiment_id, animal_index=animal_index)

            # Load the data from the request
            data = json.loads(request.body)

            # Call the update_overview method on the animal to update its details
            animal.update_overview(data)

            # Return a success response
            return JsonResponse({'success': True, 'message': 'Overview updated successfully'})

        except Exception as e:
            # Log the exception and return an error response
            print(f"Error updating overview: {str(e)}")
            return JsonResponse({'success': False, 'message': 'Error updating overview: ' + str(e)})

    return JsonResponse({'success': False, 'message': 'Invalid request method'})

def assign_drugs_and_strains_to_animals(experiment_id):
    """
    Assign drugs and strains to each animal in the given experiment.
    """
    # Get the experiment object
    experiment = get_object_or_404(Experiment, id=experiment_id)

    # Get all drugs and strains associated with the experiment
    drugs = experiment.drug_list.all()
    strains = experiment.strain_list.all()

    # Get all animals associated with the experiment
    animals = Animal.objects.filter(experiment=experiment)

    # Assign the drugs and strains to each animal
    for animal in animals:
        animal.drugs.set(drugs)
        animal.strains.set(strains)
        animal.save()

@login_required
def add_bulk_observation(request, experiment_id):
    if request.method == 'POST':
        # Get the selected animals
        selected_animals = json.loads(request.POST.get('selected_animals', '[]'))
        category = request.POST.get('category')
        score = request.POST.get('score')

        # Fetch the animals based on the selected animal indexes
        animals = Animal.objects.filter(experiment_id=experiment_id, animal_index__in=selected_animals, experiment__organization=request.user.organization)

        for animal in animals:
            Observation.objects.create(
                animal=animal,
                category=category,
                score=score,
                user=request.user
            )
        
        return redirect('animals', experiment_id=experiment_id)
@login_required
def add_bulk_dose(request, experiment_id):
    if request.method == 'POST':
        # Get the selected animals
        selected_animals = json.loads(request.POST.get('selected_animals', '[]'))
        drug_name = request.POST.get('drug_name')
        dose = request.POST.get('dose')
        stock_concentration = request.POST.get('stock_concentration')
        dose_volume = request.POST.get('dose_volume')

        # Fetch the animals based on the selected animal indexes
        animals = Animal.objects.filter(experiment_id=experiment_id, animal_index__in=selected_animals, experiment__organization=request.user.organization)

        for animal in animals:
            Dose.objects.create(
                animal=animal,
                experiment=animal.experiment,
                drug_name=drug_name,
                dose=dose,
                stock_concentration=stock_concentration,
                dose_volume=dose_volume,
                user=request.user  # Assume the logged-in user is the one administering the dose
            )

        # Redirect back to the animals page after the action
        return redirect('animals', experiment_id=experiment_id)
@login_required
def add_bulk_sample(request, experiment_id):
    if request.method == 'POST':
        # Get the selected animals
        selected_animals = json.loads(request.POST.get('selected_animals', '[]'))
        sample_id = request.POST.get('sample_id')
        sample_type = request.POST.get('sample_type')

        # Fetch the animals based on the selected animal indexes
        animals = Animal.objects.filter(experiment_id=experiment_id, animal_index__in=selected_animals, experiment__organization=request.user.organization)

        for animal in animals:
            Sample.objects.create(
                animal=animal,
                experiment=animal.experiment,
                sample_id=sample_id,
                sample_type=sample_type,
                user=request.user  # Assume the logged-in user is the one collecting the sample
            )

        # Redirect back to the animals page after the action
        return redirect('animals', experiment_id=experiment_id)


@login_required
@require_POST
def delete_animal(request, experiment_id, animal_index):
    animal = get_object_or_404(Animal, id=animal_id, experiment__organization=request.user.organization)
    RFIDAssignment.objects.filter(experiment_id=experiment_id, animal=animal).update(removed=True)
    return JsonResponse({'status': 'Animal deleted successfully'})

@login_required
@require_POST
def remove_animal(request, experiment_id, animal_id):
    logger.info(f"Remove animal called with experiment_id: {experiment_id}, animal_id: {animal_id}")

    try:
        experiment = get_object_or_404(Experiment, id=experiment_id)
        animal = get_object_or_404(Animal, id=animal_id, experiment__organization=request.user.organization)
        RFIDAssignment.objects.filter(experiment_id=experiment_id, animal=animal).update(removed=True)

        # Mark the animal as removed
        animal.removed = True
        animal.save()

        # Also update the RFID assignment to mark the animal as removed
        RFIDAssignment.objects.filter(experiment=experiment, animal=animal).update(removed=True)

        logger.info(f"Animal {animal_id} successfully removed from experiment {experiment_id}")
        return JsonResponse({'status': 'success', 'message': 'Animal removed successfully'})
    
    except Exception as e:
        logger.error(f"Error removing animal: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
def get_animal_data(experiments, search_query, sort_by, order):
    sort_order = "" if order == "asc" else "-"

    # Define the sorting field
    sort_field_mapping = {
        'rfid': 'rfid',
        'experiment_name': 'experiment__name',
    }
    sort_field = sort_field_mapping.get(sort_by, 'experiment__name')

    # Fetch RFIDAssignments for animals that are not removed
    rfid_assignments = RFIDAssignment.objects.filter(
        experiment__in=experiments,
        removed=False  # Exclude removed animals
    ).filter(
        Q(animal__animal_index__icontains=search_query) | 
        Q(rfid__icontains=search_query) | 
        Q(experiment__name__icontains=search_query)
    ).select_related('experiment', 'animal').prefetch_related(
        Prefetch('weightmeasurement_set', queryset=WeightMeasurement.objects.order_by('timestamp'))
    ).order_by(f"{sort_order}{sort_field}")

    # Prepare animal data
    animals_data = []
    for assignment in rfid_assignments:
        weight_measurements = list(assignment.weightmeasurement_set.all())
        first_measurement = weight_measurements[0] if weight_measurements else None
        last_measurement = weight_measurements[-1] if weight_measurements else None
        previous_measurement = weight_measurements[-2] if len(weight_measurements) > 1 else None

        # Safely handle None values for weight
        weight_change_first = (
            (last_measurement.weight - first_measurement.weight)
            if first_measurement and last_measurement and first_measurement.weight is not None and last_measurement.weight is not None
            else None
        )
        weight_change_previous = (
            (last_measurement.weight - previous_measurement.weight)
            if previous_measurement and last_measurement and previous_measurement.weight is not None and last_measurement.weight is not None
            else None
        )

        # Safely handle None values for tumor size
        tumor_size_change_first = (
            (last_measurement.tumor_size - first_measurement.tumor_size)
            if first_measurement and last_measurement and first_measurement.tumor_size is not None and last_measurement.tumor_size is not None
            else None
        )
        tumor_size_change_previous = (
            (last_measurement.tumor_size - previous_measurement.tumor_size)
            if previous_measurement and last_measurement and previous_measurement.tumor_size is not None and last_measurement.tumor_size is not None
            else None
        )

        animals_data.append({
            'experiment_name': assignment.experiment.name,
            'animal_index': assignment.animal.animal_index,
            'rfid_tag': assignment.rfid,
            'cage_number': assignment.cage_number,
            'weight': last_measurement.weight if last_measurement and last_measurement.weight is not None else 'N/A',
            'tumor_size': last_measurement.tumor_size if last_measurement and last_measurement.tumor_size is not None else 'N/A',
            'tracking_date': assignment.initial_weight_date,
            'weight_change_first': weight_change_first,
            'weight_change_previous': weight_change_previous,
            'tumor_size_change_first': tumor_size_change_first,
            'tumor_size_change_previous': tumor_size_change_previous,
            'experiment_id': assignment.experiment.id,
            'animal_id': assignment.animal.id
        })

    return animals_data

def get_animal_data_cached(experiments, search_query, sort_by, order):
    cache_key = f"animal_data_{search_query}_{sort_by}_{order}"
    animals_data = cache.get(cache_key)

    if animals_data is None:
        animals_data = get_animal_data(experiments, search_query, sort_by, order)
        cache.set(cache_key, animals_data, timeout=300)  # Cache for 5 minutes

    return animals_data



def get_animal_data_for_experiments(experiments, search_query, sort_by, order):
    sort_order = "" if order == "asc" else "-"

    # Define the sorting field
    sort_field_mapping = {
        'rfid': 'rfid',
        'experiment_name': 'experiment__name',
    }
    sort_field = sort_field_mapping.get(sort_by, 'experiment__name')

    # Fetch RFIDAssignments for animals that are not removed
    rfid_assignments = RFIDAssignment.objects.filter(
        experiment__in=experiments,
        removed=False  # Exclude removed animals
    ).filter(
        Q(animal__animal_index__icontains=search_query) | 
        Q(rfid__icontains=search_query) | 
        Q(experiment__name__icontains=search_query)
    ).select_related('experiment', 'animal').prefetch_related(
        'weightmeasurement_set'
    ).order_by(f"{sort_order}{sort_field}")

    # Prepare animal data
    animals_data = []
    for assignment in rfid_assignments:
        weight_measurements = list(assignment.weightmeasurement_set.all())
        first_measurement = weight_measurements[0] if weight_measurements else None
        last_measurement = weight_measurements[-1] if weight_measurements else None
        previous_measurement = weight_measurements[-2] if len(weight_measurements) > 1 else None

        # Safely handle weight change calculation
        weight_change_first = (
            (last_measurement.weight - first_measurement.weight)
            if first_measurement and last_measurement and first_measurement.weight is not None and last_measurement.weight is not None
            else None
        )
        weight_change_previous = (
            (last_measurement.weight - previous_measurement.weight)
            if previous_measurement and last_measurement and previous_measurement.weight is not None and last_measurement.weight is not None
            else None
        )

        # Safely handle tumor size change calculation
        tumor_size_change_first = (
            (last_measurement.tumor_size - first_measurement.tumor_size)
            if first_measurement and last_measurement and first_measurement.tumor_size is not None and last_measurement.tumor_size is not None
            else None
        )
        tumor_size_change_previous = (
            (last_measurement.tumor_size - previous_measurement.tumor_size)
            if previous_measurement and last_measurement and previous_measurement.tumor_size is not None and last_measurement.tumor_size is not None
            else None
        )

        animals_data.append({
            'experiment_name': assignment.experiment.name,
            'animal_index': assignment.animal.animal_index,
            'rfid_tag': assignment.rfid,
            'cage_number': assignment.cage_number,
            'weight': last_measurement.weight if last_measurement and last_measurement.weight is not None else 'N/A',
            'tumor_size': last_measurement.tumor_size if last_measurement and last_measurement.tumor_size is not None else 'N/A',
            'tracking_date': assignment.initial_weight_date,
            'weight_change_first': weight_change_first,
            'weight_change_previous': weight_change_previous,
            'tumor_size_change_first': tumor_size_change_first,
            'tumor_size_change_previous': tumor_size_change_previous,
            'experiment_id': assignment.experiment.id,
            'animal_id': assignment.animal.id
        })

    return animals_data


@login_required
def colony(request, org_id):
    user = request.user
    sort_by = request.GET.get('sort_by', 'animal__animal_index')
    order = request.GET.get('order', 'asc')
    search_query = request.GET.get('search', '')

    # Filter experiments where the user is the owner or collaborator
    active_experiments = Experiment.objects.filter(
        ended=False, organization=user.organization
    ).filter(Q(owner=user) | Q(collaborators__user=user)).distinct()

    past_experiments = Experiment.objects.filter(
        ended=True, organization=user.organization
    ).filter(Q(owner=user) | Q(collaborators__user=user)).distinct()

    # Get animal data for active experiments (exclude removed animals)
    active_animals_data = get_animal_data_for_experiments(active_experiments, search_query, sort_by, order)

    # Get animal data for past experiments (include removed animals)
    past_animals_data = get_animal_data_for_experiments(past_experiments, search_query, sort_by, order)

    # Get removed animals from active experiments
    removed_animals = RFIDAssignment.objects.filter(
        experiment__in=active_experiments,
        removed=True
    ).select_related('animal', 'experiment')

    removed_animals_data = []
    for assignment in removed_animals:
        last_measurement = assignment.weightmeasurement_set.last()
        removed_animals_data.append({
            'experiment_name': assignment.experiment.name,
            'animal_index': assignment.animal.animal_index,
            'rfid_tag': assignment.rfid,
            'cage_number': assignment.cage_number,
            'weight': last_measurement.weight if last_measurement else assignment.weight,
            'tumor_size': last_measurement.tumor_size if last_measurement else assignment.tumor_size,
            'tracking_date': assignment.initial_weight_date,
            'experiment_id': assignment.experiment.id,
            'animal_id': assignment.animal.id
        })

    # Paginate active animals
    active_paginator = Paginator(active_animals_data, 20)
    active_page_number = request.GET.get('active_page', 1)
    active_page_obj = active_paginator.get_page(active_page_number)

    # Paginate past animals
    past_paginator = Paginator(past_animals_data, 20)
    past_page_number = request.GET.get('past_page', 1)
    past_page_obj = past_paginator.get_page(past_page_number)

    # Paginate removed animals
    removed_paginator = Paginator(removed_animals_data, 20)
    removed_page_number = request.GET.get('removed_page', 1)
    removed_page_obj = removed_paginator.get_page(removed_page_number)

    # Dynamically group animals into cages by cage_number
    # Dynamically group animals into cages by cage_number
    cages_data = []
    for experiment in active_experiments:
        assignments = RFIDAssignment.objects.filter(experiment=experiment, removed=False).order_by('cage_number')
        cages = {}
        for assignment in assignments:
            if assignment.cage_number not in cages:
                cages[assignment.cage_number] = []
            cages[assignment.cage_number].append(assignment)

        for cage_number, animals in cages.items():
            animals_in_cage = []
            for assignment in animals:
                last_measurement = assignment.weightmeasurement_set.last()
                animals_in_cage.append({
                    'animal_index': assignment.animal.animal_index,
                    'rfid_tag': assignment.rfid,
                    'weight': last_measurement.weight if last_measurement else 'N/A',
                    'tumor_size': last_measurement.tumor_size if last_measurement else 'N/A'
                })
            cages_data.append({
                'experiment_name': experiment.name,
                'experiment_id': experiment.id,  # Ensure experiment_id is passed here
                'cage_number': cage_number,
                'capacity': experiment.max_per_cage,
                'animals': animals_in_cage
            })
    # Apply search query to cages data
    if search_query:
        cages_data = [
            cage for cage in cages_data
            if search_query.lower() in cage['experiment_name'].lower() or
               any(search_query.lower() in str(animal['rfid_tag']).lower() or 
                   search_query.lower() in str(animal['animal_index']).lower()
                   for animal in cage['animals'])
        ]

    # Paginate cages
    cages_paginator = Paginator(cages_data, 5)  # Change 5 to however many cages per page you want
    cages_page_number = request.GET.get('cages_page', 1)
    cages_page_obj = cages_paginator.get_page(cages_page_number)

    return render(request, 'colony.html', {
        'org_id': org_id,
        'cages_page_obj': cages_page_obj,  # Send paginated cages to the template
        'active_page_obj': active_page_obj,
        'past_page_obj': past_page_obj,
        'removed_page_obj': removed_page_obj,
        'search_query': search_query,
        'sort_by': sort_by,
        'order': order
    })


def get_cages_data(experiments):
    # Retrieve cages and associated animals
    cages = Cage.objects.filter(experiment__in=experiments).prefetch_related('animal_set')

    cages_data = []
    for cage in cages:
        animals = cage.animal_set.all()
        animals_data = [
            {
                'animal_index': animal.animal_index,
                'rfid_tag': animal.rfid_tag,
                'weight': animal.weightmeasurement_set.last().weight if animal.weightmeasurement_set.exists() else 'N/A',
                'tumor_size': animal.weightmeasurement_set.last().tumor_size if animal.weightmeasurement_set.exists() else 'N/A',
            }
            for animal in animals
        ]
        cages_data.append({
            'experiment_name': cage.experiment.name,
            'cage_number': cage.cage_number,
            'capacity': cage.capacity,
            'animals': animals_data,
        })

    return cages_data

@login_required
def get_colony_count(request, org_id):
    try:
        user = request.user
        # Filter experiments where the user is the owner or collaborator
        experiments = Experiment.objects.filter(
            ended=False, organization_id=org_id
        ).filter(Q(owner=user) | Q(collaborators__user=user)).distinct()

        # Count the animals in those experiments
        colony_count = Animal.objects.filter(experiment__in=experiments).count()

        return JsonResponse({'count': colony_count})
    except Exception as e:
        print(f"Error in get_colony_count: {e}")
        return JsonResponse({'error': str(e)}, status=500)
