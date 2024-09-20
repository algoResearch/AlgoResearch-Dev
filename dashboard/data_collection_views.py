from django.contrib import messages as django_messages
from django.core import serializers
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q, F, Avg, Max, Min, Count, Sum
from django.utils import timezone
from .models import (Conversation, Message, User, GroupMember, Experiment, RFIDAssignment, WeightMeasurement, Collaborator, CalendarEvent, Comment, Friend, Cage, Animal, Sample, Dose, Observation, Comment, Strain)
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

    print(f"Starting new weighing session with ID: {new_session_id}")

    return JsonResponse({'status': 'success', 'session_id': new_session_id})

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
def end_weighing_session(request, experiment_id):
    # Clear the session data for this experiment's weigh-in
    request.session.pop(f'weighed_animals_{experiment_id}', None)
    request.session.pop(f'current_session_id_{experiment_id}', None)  # Clear session ID

    print(f"Ending weighing session for experiment {experiment_id}")

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

        # Retrieve the current session ID from the session data
        current_session_id = request.session.get(f'current_session_id_{experiment_id}')
        if not current_session_id:
            return JsonResponse({'status': 'error', 'message': 'Session ID not found.'}, status=400)

        print(f"Using session ID: {current_session_id} for animal {animal_index}")

        # Save the measurement with the correct session ID
        measurement = WeightMeasurement.objects.create(
            rfid_assignment=rfid_assignment,
            animal=rfid_assignment.animal,
            weight=weight,
            tumor_size=tumor_size,
            recorder=request.user,
            timestamp=timezone.now(),
            session_id=current_session_id  # Use the same session ID for all measurements in this session
        )

        # Mark this animal as weighed in the session
        weighed_animals = request.session.get(f'weighed_animals_{experiment_id}', [])
        if animal_index not in weighed_animals:
            weighed_animals.append(animal_index)
        request.session[f'weighed_animals_{experiment_id}'] = weighed_animals

        return JsonResponse({'status': 'success', 'message': 'Data recorded successfully'})

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
    print("Simulate scan request received")  # Debugging statement
    experiment = get_object_or_404(Experiment, id=experiment_id)

    weighed_animals = request.session.get(f'weighed_animals_{experiment_id}', [])

    next_animal_assignment = RFIDAssignment.objects.filter(
        experiment=experiment,
        removed=False
    ).exclude(
        animal__animal_index__in=weighed_animals
    ).first()

    if not next_animal_assignment:
        print("All animals have been weighed")  # Debugging statement
        return JsonResponse({'status': 'All animals have been weighed'}, status=200)

    animal = next_animal_assignment.animal
    weighed_animals.append(animal.animal_index)
    request.session[f'weighed_animals_{experiment_id}'] = weighed_animals

    print(f"Animal to scan: {animal.animal_index}, RFID: {next_animal_assignment.rfid}")  # Debugging statement

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
def studies_view(request):
    # Get the logged-in user
    user = request.user

    # Fetch strains associated with experiments where the user is the owner or a collaborator
    strains = Strain.objects.filter(
        experiment__owner=user
    ).distinct() | Strain.objects.filter(
        experiment__collaborators__user=user
    ).distinct()

    # Prepare a dictionary to hold strain names and their associated experiments and drugs
    strain_experiments = {}

    for strain in strains:
        strain_name = strain.name

        # Fetch experiments related to this strain where the user is involved
        experiments = Experiment.objects.filter(
            strain_set=strain
        ).filter(
            Q(owner=user) | Q(collaborators__user=user)
        )

        # Prepare a list to hold the experiment and drug details
        if strain_name not in strain_experiments:
            strain_experiments[strain_name] = []

        for experiment in experiments:
            # Fetch the drugs related to this experiment
            drugs = experiment.drug_set.all()

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
            if Experiment.objects.filter(strain_set=strain_to_delete, owner=user).exists() or \
                    Experiment.objects.filter(strain_set=strain_to_delete, collaborators__user=user).exists():
                strain_to_delete.delete()
                messages.success(request, f'Strain "{strain_to_delete.name}" deleted successfully.')
            else:
                messages.error(request, 'You do not have permission to delete this strain.')
        except Exception as e:
            messages.error(request, f'Error deleting strain: {str(e)}')

    context = {
        'strain_experiments': strain_experiments,
    }

    return render(request, 'Studies.html', context)


@login_required
@csrf_exempt
def delete_strain(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            strain_name = data.get('strain_name')

            # Fetch and delete the strain
            strain = get_object_or_404(Strain, name=strain_name)
            strain.delete()

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': 'Invalid request method.'})

@login_required
def strain_analytics(request, strain_name):
    strains = Strain.objects.filter(name=strain_name)

    if not strains.exists():
        raise Http404(f"No Strains found with the name {strain_name}")

    experiments = Experiment.objects.filter(strain_set__in=strains).distinct()

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

            # Initialize variables to store sessions and baseline measurements
            current_session = 1
            last_timestamp = None
            baseline_measurements = {}
            session_measurements = []
            session_data = []

            print(f"Processing experiment '{experiment.name}' for drug '{drug_name}'")

            # Calculate session averages
            for measurement in measurements:
                animal_index = measurement.rfid_assignment.animal.animal_index
                timestamp = measurement.timestamp

                # If this is the first row or a new session is detected
                if last_timestamp and (timestamp - last_timestamp).total_seconds() > 60:  # 60 seconds threshold for new session
                    # Calculate the average weight and tumor size change for the session
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

                        # Append session data for plotting
                        session_data.append({
                            'weigh_in_number': current_session,
                            'avg_weight_change': avg_weight_change,
                            'avg_tumor_size_change': avg_tumor_size_change
                        })

                    # Start a new session
                    current_session += 1
                    session_measurements = []  # Reset for new session

                # Add the current measurement to the session
                session_measurements.append(measurement)

                # Record baseline if not already recorded
                if animal_index not in baseline_measurements:
                    baseline_measurements[animal_index] = {
                        'weight': measurement.weight,
                        'tumor_size': measurement.tumor_size,
                    }

                # Update the last timestamp
                last_timestamp = timestamp

            # Calculate averages for the last session
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

                # Append session data for plotting
                session_data.append({
                    'weigh_in_number': current_session,
                    'avg_weight_change': avg_weight_change,
                    'avg_tumor_size_change': avg_tumor_size_change
                })

            # Populate experiment data for plotting
            experiment_data[drug_name]['average_weight_changes'] = [session['avg_weight_change'] for session in session_data]
            experiment_data[drug_name]['average_tumor_size_changes'] = [session['avg_tumor_size_change'] for session in session_data]
            experiment_data[drug_name]['weigh_in_numbers'] = [session['weigh_in_number'] for session in session_data]

            # Print the final data that will be plotted for this drug
            print(f"Final Data for Drug '{drug_name}':", experiment_data[drug_name])

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
