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

import json

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
def add_sample(request, experiment_id, animal_index):
    if request.method == 'POST':
        experiment = get_object_or_404(Experiment, id=experiment_id)
        animal = get_object_or_404(Animal, experiment=experiment, animal_index=animal_index)

        sample_id = request.POST.get('sample_id')
        sample_type = request.POST.get('sample_type')

        # Create the sample with the associated experiment and animal
        sample = Sample.objects.create(
            experiment=experiment,
            animal=animal,
            sample_id=sample_id,
            sample_type=sample_type,
            user=request.user
        )

        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))

    return redirect('animal_details', experiment_id=experiment_id, animal_index=animal_index)


@login_required
@csrf_exempt
def add_dose(request, experiment_id, animal_index):
    if request.method == 'POST':
        experiment = get_object_or_404(Experiment, id=experiment_id)
        animal = get_object_or_404(Animal, experiment=experiment, animal_index=animal_index)
        
        # Ensure all fields correspond to Dose model fields
        drug_name = request.POST.get('drug_name')
        dose = request.POST.get('dose')
        stock_concentration = request.POST.get('stock_concentration')
        dose_volume = request.POST.get('dose_volume')

        # Create Dose record
        dose_record = Dose.objects.create(
            experiment=experiment,
            animal=animal,
            drug_name=drug_name,
            dose=dose,
            stock_concentration=stock_concentration,
            dose_volume=dose_volume,
            user=request.user
        )

        # Redirect to the animal details page
        return redirect('animal_details', experiment_id=experiment.id, animal_index=animal.animal_index)
    
    return redirect('animal_details', experiment_id=experiment_id, animal_index=animal_index)

@login_required
def animals(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    
    # Adjust the ordering to use the related Animal model's animal_index field
    rfid_assignments = RFIDAssignment.objects.filter(experiment=experiment).order_by('animal__animal_index')

    animals_data = []

    for assignment in rfid_assignments:
        # Fetch first and last weight measurements
        first_measurement = WeightMeasurement.objects.filter(
            rfid_assignment=assignment  # Adjusted to filter by the correct relation
        ).order_by('timestamp').first()

        last_measurement = WeightMeasurement.objects.filter(
            rfid_assignment=assignment  # Adjusted to filter by the correct relation
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
            'animal_index': assignment.animal.animal_index,  # Accessing the related Animal's animal_index
            'cage_number': assignment.cage_number,
            'weight': last_measurement.weight if last_measurement else assignment.weight,
            'tumor_size': last_measurement.tumor_size if last_measurement else assignment.tumor_size,
            'tracking_date': assignment.initial_weight_date,
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
    animal = get_object_or_404(Animal, experiment_id=experiment_id, animal_index=animal_index)
    rfid_assignment = RFIDAssignment.objects.filter(animal=animal).first()
    
    if rfid_assignment:
        rfid_tag = rfid_assignment.rfid
    else:
        rfid_tag = "RFID Not Assigned"

    context = {
        'animal': animal,
        'rfid_tag': rfid_tag,
        # other context variables
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
            animal = get_object_or_404(Animal, experiment__id=experiment_id, animal_index=animal_index)

            # Load the data from the request
            data = json.loads(request.body)

            # Update the animal fields with the provided data
            animal.rfid_tag = data.get('rfid_tag', animal.rfid_tag)
            animal.age = data.get('age', animal.age)
            animal.sex = data.get('sex', animal.sex)
            animal.species = data.get('species', animal.species)
            animal.strain = data.get('strain', animal.strain)
            animal.tail = data.get('tail', animal.tail)
            animal.ear = data.get('ear', animal.ear)
            animal.tag = data.get('tag', animal.tag)
            animal.donor = data.get('donor', animal.donor)

            # Save the updated animal object
            animal.save()

            # Return a success response with the updated data
            return JsonResponse({'success': True, 'message': 'Overview updated successfully', **data})

        except Exception as e:
            # Log the exception and return an error response
            print(f"Error updating overview: {str(e)}")
            return JsonResponse({'success': False, 'message': 'Error updating overview: ' + str(e)})

@login_required
@require_POST
def delete_animal(request, experiment_id, animal_index):
    RFIDAssignment.objects.filter(experiment_id=experiment_id, animal_index=animal_index).update(removed=True)
    return JsonResponse({'status': 'Animal deleted successfully'})


@login_required
@require_POST
def remove_animal(request, experiment_id, animal_index):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    RFIDAssignment.objects.filter(experiment=experiment, animal_index=animal_index).update(removed=True)
    return JsonResponse({'status': 'success', 'message': 'Animal removed successfully'})
