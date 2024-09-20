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
from .models import (Conversation, Message, User, GroupMember, Experiment, RFIDAssignment, WeightMeasurement, Collaborator, CalendarEvent, Comment, Friend, Cage, Animal, Sample, Dose, Observation, Comment)
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, authenticate
import pandas as pd
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

@login_required
@csrf_exempt
def add_comment(request, experiment_id, animal_index):
    if request.method == 'POST':
        comment_text = request.POST.get('comment') or json.loads(request.body).get('comment')
        if comment_text:
            Comment.objects.create(
                experiment_id=experiment_id,
                animal_index=animal_index,
                user=request.user,
                content=comment_text
            )
            return JsonResponse({'status': 'success', 'message': 'Comment added successfully!'})
        else:
            return JsonResponse({'status': 'error', 'message': 'Comment text cannot be empty.'})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})

def animal_details_view(request, experiment_id, animal_index):
    animal = get_object_or_404(Animal, experiment_id=experiment_id, animal_index=animal_index)
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
    }
    return render(request, 'animal_details.html', context)

@login_required
def save_observations(request, animal_id):
    if request.method == 'POST':
        animal = get_object_or_404(Animal, id=animal_id)
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
        animal = get_object_or_404(Animal, id=animal_id)
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
        animal = get_object_or_404(Animal, id=animal_id)
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
def add_sample(request, experiment_id, animal_index):
    experiment = get_object_or_404(Experiment, id=experiment_id)
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
        'form': form
    }
    return render(request, 'add_sample.html', context)
@login_required
def add_dose(request, experiment_id, animal_index):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    animal = get_object_or_404(Animal, experiment=experiment, animal_index=animal_index)

    if request.method == 'POST':
        form = DoseForm(request.POST)
        if form.is_valid():
            dose = form.save(commit=False)
            dose.experiment = experiment
            dose.animal = animal
            dose.user = request.user
            dose.save()
            return redirect('animal_details', experiment_id=experiment.id, animal_index=animal.animal_index)
    else:
        form = DoseForm()

    context = {
        'experiment': experiment,
        'animal': animal,
        'form': form
    }
    return render(request, 'add_dose.html', context)

@login_required
def animals(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    
    # Fetch the RFID assignments and sort them by animal_index
    rfid_assignments = RFIDAssignment.objects.filter(experiment=experiment).order_by('animal__animal_index')

    animals_data = []

    for assignment in rfid_assignments:
        # Fetch first and last weight measurements
        first_measurement = WeightMeasurement.objects.filter(
            rfid_assignment=assignment
        ).order_by('timestamp').first()

        last_measurement = WeightMeasurement.objects.filter(
            rfid_assignment=assignment
        ).order_by('-timestamp').first()

        previous_measurement = WeightMeasurement.objects.filter(
            rfid_assignment=assignment,
            timestamp__lt=last_measurement.timestamp if last_measurement else None
        ).order_by('-timestamp').first() if last_measurement else None

        # Safely calculate weight and tumor size changes
        weight_change_first = (
            last_measurement.weight - first_measurement.weight
            if first_measurement and last_measurement and first_measurement.weight is not None and last_measurement.weight is not None
            else None
        )
        weight_change_previous = (
            last_measurement.weight - previous_measurement.weight
            if previous_measurement and last_measurement and previous_measurement.weight is not None and last_measurement.weight is not None
            else None
        )
        tumor_size_change_first = (
            last_measurement.tumor_size - first_measurement.tumor_size
            if first_measurement and last_measurement and first_measurement.tumor_size is not None and last_measurement.tumor_size is not None
            else None
        )
        tumor_size_change_previous = (
            last_measurement.tumor_size - previous_measurement.tumor_size
            if previous_measurement and last_measurement and previous_measurement.tumor_size is not None and last_measurement.tumor_size is not None
            else None
        )

        animals_data.append({
            'animal_index': assignment.animal.animal_index,
            'cage_number': assignment.cage_number,
            'weight': last_measurement.weight if last_measurement else assignment.weight,
            'tumor_size': last_measurement.tumor_size if last_measurement else assignment.tumor_size,
            'tracking_date': assignment.initial_weight_date,
            'timestamp': last_measurement.timestamp if last_measurement else 'N/A',  # Add timestamp for the latest measurement
            'weight_change_first': weight_change_first,
            'weight_change_previous': weight_change_previous,
            'tumor_size_change_first': tumor_size_change_first,
            'tumor_size_change_previous': tumor_size_change_previous,
        })

    context = {
        'experiment': experiment,
        'animals_data': animals_data,
    }

    return render(request, 'animals.html', context)



def animal_details(request, experiment_id, animal_index):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    animal = get_object_or_404(Animal, experiment_id=experiment_id, animal_index=animal_index)
    rfid_assignment = RFIDAssignment.objects.filter(animal=animal).first()
    weigh_ins = WeightMeasurement.objects.filter(animal=animal).order_by('timestamp')

    dates = [weigh_in.timestamp.strftime("%Y-%m-%d") for weigh_in in weigh_ins]
    weights = [weigh_in.weight for weigh_in in weigh_ins]
    tumor_sizes = [weigh_in.tumor_size for weigh_in in weigh_ins if weigh_in.tumor_size is not None]
    drugs = animal.drugs.all()
    strains = animal.strains.all()


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
        'samples': animal.samples.all(),  # Ensure you have a related name samples or direct attribute
        'doses': animal.doses.all(),     
         # Ensure you have a related name doses or direct attribute
    }

    return render(request, 'animal_details.html', context)

@login_required
def add_observation(request, experiment_id, animal_index):
    # Fetch the relevant experiment and animal
    experiment = get_object_or_404(Experiment, id=experiment_id)
    animal = get_object_or_404(Animal, experiment=experiment, animal_index=animal_index)

    if request.method == 'POST':
        form = ObservationForm(request.POST)
        if form.is_valid():
            observation = form.save(commit=False)
            observation.animal = animal
            observation.user = request.user
            observation.save()
            return redirect('animal_details', experiment_id=experiment.id, animal_index=animal.animal_index)
    else:
        form = ObservationForm()

    context = {
        'experiment': experiment,
        'animal': animal,
        'form': form,
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

            # Update the animal fields with the provided data
            animal.rfid_tag = data.get('rfid_tag', animal.rfid_tag)
            animal.age = data.get('age', animal.age)
            animal.sex = data.get('sex', animal.sex)
            animal.species = data.get('species', animal.species)
            animal.strain = data.get('strain', animal.strain)
            animal.drug = data.get('drug', animal.drug)
            animal.tail = data.get('tail', animal.tail)
            animal.ear = data.get('ear', animal.ear)
            animal.tag = data.get('tag', animal.tag)
            animal.donor = data.get('donor', animal.donor)

            # Save the updated animal object
            animal.save()
            
            assign_drugs_and_strains_to_animals(experiment_id)


            # Return a success response with the updated data
            return JsonResponse({'success': True, 'message': 'Overview updated successfully'})

        except Exception as e:
            # Log the exception and return an error response
            print(f"Error updating overview: {str(e)}")
            return JsonResponse({'success': False, 'message': 'Error updating overview: ' + str(e)})

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
@require_POST
def delete_animal(request, experiment_id, animal_index):
    RFIDAssignment.objects.filter(experiment_id=experiment_id, animal_index=animal_index).update(removed=True)
    return JsonResponse({'status': 'Animal deleted successfully'})

@login_required
@require_POST
def remove_animal(request, experiment_id, animal_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)

    # Fetch the RFIDAssignment based on the animal's ID and mark it as removed
    RFIDAssignment.objects.filter(experiment=experiment, animal_id=animal_id).update(removed=True)

    return JsonResponse({'status': 'success', 'message': 'Animal removed successfully'})

def get_animal_data(experiments, search_query, sort_by, order):
    # Determine sorting order
    sort_order = "" if order == "asc" else "-"

    # Define a mapping for sorting fields to the actual model fields
    sort_field_mapping = {
        'rfid': 'rfid',
        'experiment_name': 'experiment__name',
    }

    # Default sorting by experiment name if sort_by field is not found in mapping
    sort_field = sort_field_mapping.get(sort_by, 'experiment__name')

    # Prefetch related weight measurements
    rfid_assignments = RFIDAssignment.objects.filter(
        experiment__in=experiments
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

        # Fetch the previous measurement if available
        previous_measurement = weight_measurements[-2] if len(weight_measurements) > 1 else None

        # Safely calculate weight and tumor size changes
        weight_change_first = (last_measurement.weight - first_measurement.weight
                               if first_measurement and last_measurement and first_measurement.weight is not None and last_measurement.weight is not None
                               else None)
        weight_change_previous = (last_measurement.weight - previous_measurement.weight
                                  if previous_measurement and last_measurement and previous_measurement.weight is not None and last_measurement.weight is not None
                                  else None)

        tumor_size_change_first = (last_measurement.tumor_size - first_measurement.tumor_size
                                   if first_measurement and last_measurement and first_measurement.tumor_size is not None and last_measurement.tumor_size is not None
                                   else None)
        tumor_size_change_previous = (last_measurement.tumor_size - previous_measurement.tumor_size
                                      if previous_measurement and last_measurement and previous_measurement.tumor_size is not None and last_measurement.tumor_size is not None
                                      else None)

        animals_data.append({
            'experiment_name': assignment.experiment.name,
            'animal_index': assignment.animal.animal_index,
            'rfid_tag': assignment.rfid,
            'cage_number': assignment.cage_number,
            'weight': last_measurement.weight if last_measurement else assignment.weight,
            'tumor_size': last_measurement.tumor_size if last_measurement else assignment.tumor_size,
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

@login_required
def colony(request):
    user = request.user
    sort_by = request.GET.get('sort_by', 'animal__animal_index')
    order = request.GET.get('order', 'asc')
    search_query = request.GET.get('search', '')

    # Filter experiments where user is the owner or collaborator
    active_experiments = Experiment.objects.filter(ended=False).filter(Q(owner=user) | Q(collaborators__user=user)).distinct()
    past_experiments = Experiment.objects.filter(ended=True).filter(Q(owner=user) | Q(collaborators__user=user)).distinct()

    # Get animal data for active and past experiments
    active_animals_data = get_animal_data(active_experiments, search_query, sort_by, order)
    past_animals_data = get_animal_data(past_experiments, search_query, sort_by, order)

    # Paginate the results for active animals
    active_paginator = Paginator(active_animals_data, 20)  # Show 20 animals per page
    active_page_number = request.GET.get('active_page', 1)
    active_page_obj = active_paginator.get_page(active_page_number)

    # Paginate the results for past animals
    past_paginator = Paginator(past_animals_data, 20)  # Show 20 animals per page
    past_page_number = request.GET.get('past_page', 1)
    past_page_obj = past_paginator.get_page(past_page_number)

    # Render the template with paginated active and past animals
    return render(request, 'colony.html', {
        'active_page_obj': active_page_obj,
        'past_page_obj': past_page_obj,
        'search_query': search_query,
        'sort_by': sort_by,
        'order': order
    })

@login_required
def get_colony_count(request):
    user = request.user
    active_experiments = Experiment.objects.filter(ended=False).filter(Q(owner=user) | Q(collaborators__user=user)).distinct()
    animal_count = Animal.objects.filter(experiment__in=active_experiments).count()
    return JsonResponse({'count': animal_count})

