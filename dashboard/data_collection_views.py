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

@login_required
@require_POST
def start_weighing_session(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    # Ensure the session for weighed animals is cleared at the start of the session
    request.session[f'weighed_animals_{experiment_id}'] = []
    return JsonResponse({'status': 'success'})


@login_required
def reset_weigh_in_session(request, experiment_id):
    # Clear the session data for this experiment's weigh-in
    request.session[f'weighed_animals_{experiment_id}'] = []  # Reset the list of weighed animals
    return JsonResponse({'status': 'success'})


@login_required
def data_collection(request, experiment_id):
    # Fetch the experiment for the logged-in user who is either the owner or a collaborator
    experiment = get_object_or_404(
        Experiment,
        Q(id=experiment_id),
        Q(owner=request.user) | Q(collaborators__user=request.user)
    )

    # Fetch RFID assignments related to this experiment
    assigned_rfids = RFIDAssignment.objects.filter(experiment=experiment, removed=False).select_related('animal')

    animals_by_cage = {}
    all_animals_weighed = True  # Assume all animals are weighed initially

    # Organize animals by their cage numbers and gather their RFID data
    for assignment in assigned_rfids:
        animal = assignment.animal
        cage_number = assignment.cage_number
        
        if cage_number not in animals_by_cage:
            animals_by_cage[cage_number] = []
        
        animals_by_cage[cage_number].append({
            'animal_index': animal.animal_index,
            'rfid': assignment.rfid,
            'weight': assignment.weight,
            'tumor_size': assignment.tumor_size,
        })

        # Check if the animal has been weighed in the current session
        weighed_animals = request.session.get(f'weighed_animals_{experiment_id}', [])
        if animal.animal_index not in weighed_animals:
            all_animals_weighed = False

    context = {
        'experiment': experiment,
        'animals_by_cage': animals_by_cage,
        'all_animals_weighed': all_animals_weighed,
        'monitor_weight': experiment.monitor_weight,
        'monitor_tumor': experiment.monitor_tumor,
    }

    return render(request, 'data-collection.html', context)


@login_required
def end_weigh_in_session(request, experiment_id):
    # Clear the session data for this experiment's weigh-in
    request.session.pop(f'weighed_animals_{experiment_id}', None)
    
    # Redirect to experiment home or another page
    return redirect('experiment_home', experiment_id=experiment_id)

@login_required
@require_POST
def save_data_collection(request, experiment_id):
    experiment = get_object_or_404(
        Experiment,
        Q(id=experiment_id) & (Q(owner=request.user) | Q(collaborators__user=request.user))
    )

    try:
        data = json.loads(request.body)
        animal_index = data.get('animal_index')
        weight = data.get('weight') if experiment.monitor_weight else None
        tumor_size = data.get('tumor_size') if experiment.monitor_tumor else None

        if not animal_index or (experiment.monitor_weight and weight is None):
            return JsonResponse({'status': 'error', 'message': 'Missing required fields.'}, status=400)

        animal_index = int(animal_index)
        weight = float(weight) if weight else None
        tumor_size = float(tumor_size) if tumor_size else None

        rfid_assignment = RFIDAssignment.objects.get(experiment=experiment, animal_index=animal_index)

        weight_loss_percentage = 0.0

        if experiment.monitor_weight:
            if rfid_assignment.initial_weight:
                weight_loss_percentage = ((rfid_assignment.initial_weight - weight) / rfid_assignment.initial_weight) * 100
            else:
                rfid_assignment.initial_weight = weight
                rfid_assignment.weight = weight
                rfid_assignment.save()

        measurement = WeightMeasurement.objects.create(
            experiment=experiment,
            animal_index=animal_index,
            weight=weight,
            tumor_size=tumor_size,
            recorder=request.user,
            timestamp=timezone.now()
        )

        if experiment.monitor_weight:
            rfid_assignment.weight = weight

        if experiment.monitor_tumor:
            rfid_assignment.tumor_size = tumor_size

        rfid_assignment.save()

        if experiment.monitor_weight and weight_loss_percentage >= 19.99:
            rfid_assignment.removed = True
            rfid_assignment.save()

            return JsonResponse({
                'status': 'warning',
                'message': f"Animal {animal_index} has been removed for safety after losing {weight_loss_percentage:.2f}% of its initial weight."
            })

        return JsonResponse({'status': 'success', 'message': 'Data recorded successfully', 'weight_loss_percentage': weight_loss_percentage})

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)




@login_required
@require_POST
def mark_animal_weighed(request, experiment_id):
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
def simulate_scan(request, experiment_id):
    # Retrieve the experiment object
    experiment = get_object_or_404(Experiment, id=experiment_id)

    # Retrieve the list of animals that have been weighed in this session
    weighed_animals = request.session.get(f'weighed_animals_{experiment_id}', [])

    # Find the next animal that hasn't been weighed
    next_animal_assignment = RFIDAssignment.objects.filter(
        experiment=experiment,
        removed=False
    ).exclude(
        animal__animal_index__in=weighed_animals  # Access animal_index through related Animal
    ).first()

    if not next_animal_assignment:
        return JsonResponse({'status': 'All animals have been weighed'}, status=200)

    # Add the animal index to the weighed animals list in the session
    animal = next_animal_assignment.animal
    weighed_animals.append(animal.animal_index)
    request.session[f'weighed_animals_{experiment_id}'] = weighed_animals

    # Return the animal data to the client
    return JsonResponse({
        'status': 'success',
        'animal_index': animal.animal_index,
        'rfid': next_animal_assignment.rfid
    })

@login_required
@require_POST
def enter_weight(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    
    data = json.loads(request.body)
    animal_index = data.get('animal_index')
    weight = data.get('weight')
    
    if not animal_index or not weight:
        return JsonResponse({'status': 'error', 'message': 'Invalid data'}, status=400)

    try:
        weight = float(weight)
    except ValueError:
        return JsonResponse({'status': 'error', 'message': 'Invalid weight value'}, status=400)

    # Fetch the corresponding RFIDAssignment and Animal
    rfid_assignment = RFIDAssignment.objects.filter(experiment=experiment, animal__animal_index=animal_index).first()
    if not rfid_assignment:
        return JsonResponse({'status': 'error', 'message': 'RFID Assignment not found for given animal index'}, status=404)
    
    animal = rfid_assignment.animal  # Ensure this is set correctly
    
    # Calculate the percentage weight loss
    if rfid_assignment.initial_weight is None:
        rfid_assignment.initial_weight = weight

    previous_measurement = WeightMeasurement.objects.filter(
        animal=animal
    ).order_by('-timestamp').first()

    weight_change = ((weight - previous_measurement.weight) / previous_measurement.weight) * 100 if previous_measurement else 0.0

    rfid_assignment.weight = weight
    rfid_assignment.save()

    # Create the WeightMeasurement with the associated Animal
    WeightMeasurement.objects.create(
        rfid_assignment=rfid_assignment,  # Make sure the WeightMeasurement is linked to the RFIDAssignment
        animal=animal,  # Link directly to the Animal instance
        weight=weight,
        weight_change=weight_change,
        recorder=request.user
    )

    # Mark this animal as weighed in the session
    weighed_animals = request.session.get(f'weighed_animals_{experiment_id}', [])
    weighed_animals.append(animal_index)
    request.session[f'weighed_animals_{experiment_id}'] = weighed_animals

    if weight_change <= -20.0:
        return JsonResponse({
            'status': 'warning',
            'message': f"Animal {animal_index} has lost {abs(weight_change):.2f}% of its body weight and should be removed."
        })

    return JsonResponse({'status': 'success', 'rfid': rfid_assignment.rfid})

@login_required
@require_POST
def enter_tumor_size(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    
    data = json.loads(request.body)
    animal_index = data.get('animal_index')
    tumor_size = data.get('tumor_size')
    
    if not animal_index or not tumor_size:
        return JsonResponse({'status': 'error', 'message': 'Invalid data'}, status=400)

    try:
        tumor_size = float(tumor_size)
    except ValueError:
        return JsonResponse({'status': 'error', 'message': 'Invalid tumor size value'}, status=400)

    # Retrieve the RFIDAssignment and corresponding Animal
    rfid_assignment = RFIDAssignment.objects.filter(
        experiment=experiment, 
        animal__animal_index=animal_index
    ).first()
    
    if not rfid_assignment:
        return JsonResponse({'status': 'error', 'message': 'RFID Assignment not found for given animal index'}, status=404)
    
    animal = rfid_assignment.animal  # Retrieve the Animal instance

    # Fetch the latest WeightMeasurement for the animal
    measurement = WeightMeasurement.objects.filter(
        animal=animal
    ).order_by('-timestamp').first()

    if not measurement:
        return JsonResponse({'status': 'error', 'message': 'No measurements found for the animal'}, status=404)

    # Update the tumor size
    measurement.tumor_size = tumor_size
    measurement.save()

    return JsonResponse({'status': 'success', 'message': 'Tumor size updated successfully'})


@login_required
def Studies(request):
    # Get all distinct strains where strain is not None and not an empty string
    strains = Experiment.objects.exclude(strain__isnull=True).exclude(strain='').values_list('strain', flat=True).distinct()

    strain_experiments = {}
    for strain in strains:
        experiments = Experiment.objects.filter(strain=strain)
        strain_experiments[strain] = experiments

    return render(request, 'Studies.html', {
        'strain_experiments': strain_experiments,
    })

@login_required
def strain_analytics(request, strain_name):
    # Get all experiments for the given strain
    experiments = Experiment.objects.filter(strain=strain_name)

    # Prepare a dictionary to hold data for each drug
    experiment_data = {}

    for experiment in experiments:
        drug = experiment.drug

        if drug not in experiment_data:
            experiment_data[drug] = {
                'average_weight_changes': [],
                'average_tumor_size_changes': [],
                'weigh_in_numbers': []  # This will hold weigh-in indices
            }

        # Get distinct weigh-in timestamps for this experiment
        weigh_in_timestamps = WeightMeasurement.objects.filter(experiment=experiment).values_list('timestamp', flat=True).distinct().order_by('timestamp')

        initial_avg_weight = None
        initial_avg_tumor_size = None

        for index, weigh_in_time in enumerate(weigh_in_timestamps):
            # Aggregate data for all animals at this weigh-in timestamp
            current_measurements = WeightMeasurement.objects.filter(experiment=experiment, timestamp=weigh_in_time)

            # Calculate the average weight and tumor size for all animals at this weigh-in time
            avg_weight = current_measurements.aggregate(avg_weight=Avg('weight'))['avg_weight']
            avg_tumor_size = current_measurements.aggregate(avg_tumor=Avg('tumor_size'))['avg_tumor']

            if index == 0:
                # First weigh-in is the baseline, set initial averages
                initial_avg_weight = avg_weight if avg_weight is not None else 0
                initial_avg_tumor_size = avg_tumor_size if avg_tumor_size is not None else 0

                # First point is 0 change
                experiment_data[drug]['average_weight_changes'].append(0)
                experiment_data[drug]['average_tumor_size_changes'].append(0)
            else:
                # Ensure avg_weight and avg_tumor_size are not None before calculation
                if avg_weight is not None and initial_avg_weight is not None:
                    avg_weight_change = avg_weight - initial_avg_weight
                else:
                    avg_weight_change = 0

                if avg_tumor_size is not None and initial_avg_tumor_size is not None:
                    avg_tumor_size_change = avg_tumor_size - initial_avg_tumor_size
                else:
                    avg_tumor_size_change = 0

                experiment_data[drug]['average_weight_changes'].append(avg_weight_change)
                experiment_data[drug]['average_tumor_size_changes'].append(avg_tumor_size_change)

            # Append the weigh-in index to the data (only once for each weigh-in)
            if len(experiment_data[drug]['weigh_in_numbers']) < len(weigh_in_timestamps):
                experiment_data[drug]['weigh_in_numbers'].append(index + 1)  # Use the weigh-in index

    # Now average the changes across all experiments for each drug
    for drug, data in experiment_data.items():
        # Number of weigh-ins across all experiments
        num_weigh_ins = len(data['weigh_in_numbers'])

        # Initialize lists for storing the final average changes
        final_avg_weight_changes = [0] * num_weigh_ins
        final_avg_tumor_size_changes = [0] * num_weigh_ins
        count_weigh_ins = [0] * num_weigh_ins  # To track how many experiments contributed to each weigh-in

        for experiment in experiments:
            for i in range(num_weigh_ins):
                if i < len(experiment_data[drug]['average_weight_changes']):
                    final_avg_weight_changes[i] += experiment_data[drug]['average_weight_changes'][i]
                    final_avg_tumor_size_changes[i] += experiment_data[drug]['average_tumor_size_changes'][i]
                    count_weigh_ins[i] += 1

        # Calculate the average across all experiments
        for i in range(num_weigh_ins):
            if count_weigh_ins[i] > 0:
                final_avg_weight_changes[i] /= count_weigh_ins[i]
                final_avg_tumor_size_changes[i] /= count_weigh_ins[i]

        # Update the experiment data with the final averages
        experiment_data[drug]['average_weight_changes'] = final_avg_weight_changes
        experiment_data[drug]['average_tumor_size_changes'] = final_avg_tumor_size_changes

    context = {
        'strain_name': strain_name,
        'experiment_data': experiment_data,
    }

    return render(request, 'strain_analytics.html', context)

@login_required
def analytics(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)

    animals = RFIDAssignment.objects.filter(experiment=experiment)
    weight_measurements = WeightMeasurement.objects.filter(experiment=experiment).order_by('timestamp')

    chart_data = {}
    for wm in weight_measurements:
        if wm.animal_index not in chart_data:
            chart_data[wm.animal_index] = {'dates': [], 'weights': []}
        chart_data[wm.animal_index]['dates'].append(wm.timestamp.strftime('%Y-%m-%d'))
        chart_data[wm.animal_index]['weights'].append(wm.weight)

    chart_data_json = mark_safe(json.dumps(chart_data))

    return render(request, 'analytics.html', {
        'experiment': experiment,
        'chart_data': chart_data_json
    })

@login_required
def download_csv(request, experiment_id):
    return generate_csv_for_experiment(experiment_id, request.user)



@login_required
@csrf_exempt
def save_rfids(request, experiment_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            print("Parsed JSON data:", data)  # Debug statement

            rfids_data = data.get('rfids')
            if rfids_data is None or not isinstance(rfids_data, list):
                return JsonResponse({'status': 'error', 'message': 'Expected a list of objects under the key "rfids"'}, status=400)

            experiment = Experiment.objects.get(id=experiment_id, owner=request.user)

            for item in rfids_data:
                if 'animal_index' in item and 'rfid' in item:
                    animal_index = item['animal_index']
                    rfid = item['rfid']
                    animal, created = Animal.objects.get_or_create(
                        experiment=experiment,
                        animal_index=animal_index,
                        defaults={'rfid_tag': rfid}
                    )
                    RFIDAssignment.objects.update_or_create(
                        experiment=experiment,
                        animal=animal,
                        defaults={'rfid': rfid}
                    )
                else:
                    return JsonResponse({'status': 'error', 'message': 'Missing animal_index or rfid in data'}, status=400)

            return JsonResponse({'status': 'success'}, status=200)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)