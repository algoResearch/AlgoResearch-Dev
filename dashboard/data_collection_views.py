from django.contrib import messages as django_messages
from django.core import serializers
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q, F, Avg, Max, Min, Count, Sum
from django.utils import timezone
from .models import (Conversation, UserAction, Message, User, GroupMember, Task, Experiment, RFIDAssignment, WeightMeasurement, Collaborator, CalendarEvent, Comment, Friend, Cage, Animal, Sample, Dose, Observation, Comment, Strain, Organization)
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, authenticate
import pandas as pd
from django.views.decorators.csrf import csrf_exempt
import random
from django.contrib.auth import logout
from django.db import IntegrityError
from .forms import CustomUserCreationForm, UpdateProfileForm, ExperimentForm, DataInputMethodForm
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
@require_POST
def remove_animal(request, org_id, experiment_id, animal_id):
    organization = get_object_or_404(Organization, id=org_id)
    experiment = get_object_or_404(Experiment, id=experiment_id, organization=organization)

    try:
        # Fetch the animal by its ID and make sure it belongs to the experiment
        animal = get_object_or_404(Animal, id=animal_id, experiment=experiment)
        rfid_assignment = get_object_or_404(RFIDAssignment, experiment=experiment, animal=animal)

        logger.info(f"Attempting to remove animal with ID: {animal_id} from experiment: {experiment_id}")

        # Parse the incoming data to get the user-typed signature
        data = json.loads(request.body)
        typed_signature = data.get('signature')

        if not typed_signature:
            return JsonResponse({'status': 'error', 'message': 'Signature is required.'}, status=400)

        # Validate the signature
        user_full_name = f"{request.user.first_name} {request.user.last_name}".strip().lower()
        if typed_signature.strip().lower() != user_full_name:
            return JsonResponse({'status': 'error', 'message': 'Signature does not match your full name.'}, status=400)

        # Mark the animal and RFID assignment as removed
        animal.removed = True
        animal.save()
        rfid_assignment.removed = True
        rfid_assignment.save()

        return JsonResponse({'status': 'success', 'message': f'Animal {animal_id} removed successfully.'})

    except Animal.DoesNotExist:
        logger.error(f"Animal with ID {animal_id} not found in experiment {experiment_id}.")
        return JsonResponse({'status': 'error', 'message': 'Animal not found.'}, status=404)
    except RFIDAssignment.DoesNotExist:
        logger.error(f"RFID assignment for animal {animal_id} not found in experiment {experiment_id}.")
        return JsonResponse({'status': 'error', 'message': 'RFID Assignment not found.'}, status=404)

    
def remove_animal_view(request, experiment_id, animal_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    animal = get_object_or_404(Animal, id=animal_id, experiment=experiment)

    # Call the remove method of the animal
    animal.remove()

    return JsonResponse({'status': 'success', 'message': 'Animal removed successfully'})

@login_required
def data_collection(request, experiment_id, org_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)

    # Ensure session for weighed animals exists
    if f'weighed_animals_{experiment_id}' not in request.session:
        request.session[f'weighed_animals_{experiment_id}'] = []  # Initialize the session

    # Fetch RFID assignments related to this experiment (active animals)
    assigned_rfids = RFIDAssignment.objects.for_user(request.user).filter(experiment=experiment, removed=False).select_related('animal')

    # Fetch removed animals for display under 'Past Animals'
    removed_animals = RFIDAssignment.objects.for_user(request.user).filter(experiment=experiment, removed=True).select_related('animal')

    # Organize animals by cage
    animals_by_cage = {}
    for assignment in assigned_rfids:
        cage_number = assignment.cage_number
        if cage_number not in animals_by_cage:
            animals_by_cage[cage_number] = []
        animals_by_cage[cage_number].append({
            'animal_index': assignment.animal.animal_index,
            'id': assignment.animal.id,  # Ensure animal.id is included
            'rfid': assignment.rfid,
            'removed': assignment.removed
        })

    # Pass experiment ID and animals to the template context
    context = {
        'experiment': experiment,
        'animals_by_cage': animals_by_cage,
        'removed_animals': removed_animals,  # Send removed animals to the template
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
        data = json.loads(request.body)
        animal_index = data.get('animal_index')
        weight = data.get('weight') if experiment.monitor_weight else None
        tumor_size = data.get('tumor_size') if experiment.monitor_tumor else None

        # Ensure weight is provided when required
        if not animal_index or (experiment.monitor_weight and weight is None):
            return JsonResponse({'status': 'error', 'message': 'Missing required fields.'}, status=400)

        animal_index = int(animal_index)
        weight = float(weight) if weight else None
        tumor_size = float(tumor_size) if tumor_size else None

        # Fetch the RFID assignment for the animal that hasn't been removed
        rfid_assignment = RFIDAssignment.objects.for_user(request.user).get(
            experiment=experiment, animal__animal_index=animal_index, removed=False)

        # Retrieve the current session ID from the session data
        current_session_id = request.session.get(f'current_session_id_{experiment_id}')
        if not current_session_id:
            return JsonResponse({'status': 'error', 'message': 'Session ID not found.'}, status=400)

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

        # If tumor size is not being monitored, skip tumor size entry and mark as complete
        if not experiment.monitor_tumor:
            return JsonResponse({'status': 'success', 'message': 'Weight recorded successfully'})

        return JsonResponse({'status': 'success', 'message': 'Data recorded successfully'})

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)
    except RFIDAssignment.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Animal not found or has been removed.'}, status=404)
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
def simulate_scan(request, org_id, experiment_id):
    organization = get_object_or_404(Organization, id=org_id)
    experiment = get_object_or_404(Experiment, id=experiment_id, organization=organization)

    # Retrieve the list of animals already weighed or measured
    weighed_animals = request.session.get(f'weighed_animals_{experiment_id}', [])

    logger.info(f"Currently weighed animals: {weighed_animals}")

    # Filter animals that haven't been weighed or tumor measured
    unweighed_animals = RFIDAssignment.objects.filter(experiment=experiment, removed=False).exclude(
        animal__animal_index__in=weighed_animals
    )

    if not unweighed_animals.exists():
        logger.info("All animals have been weighed.")
        return JsonResponse({'status': 'error', 'message': 'All animals have been weighed'})

    # Get the next unweighed animal
    next_animal = unweighed_animals.first()
    
    logger.info(f"Next animal for scan: ID {next_animal.animal.id}, RFID {next_animal.rfid}")

    return JsonResponse({
        'status': 'success',
        'animal_index': next_animal.animal.animal_index,
        'animal_id': next_animal.animal.id,  # Ensure animal_id is passed here
        'rfid': next_animal.rfid
    })
@login_required
@require_POST
def enter_weight(request, org_id, experiment_id):
    experiment = get_object_or_404(Experiment.objects.filter(organization_id=org_id), id=experiment_id)

    try:
        data = json.loads(request.body)
        animal_id = data.get('animal_id')
        weight = data.get('weight')
        
        if not animal_id or not weight:
            return JsonResponse({'status': 'error', 'message': 'Invalid data'}, status=400)

        try:
            weight = float(weight)
        except ValueError:
            return JsonResponse({'status': 'error', 'message': 'Invalid weight value'}, status=400)

        # Fetch the RFIDAssignment and Animal
        rfid_assignment = RFIDAssignment.objects.filter(
            experiment=experiment, animal__id=animal_id, experiment__organization_id=org_id
        ).first()
        
        if not rfid_assignment:
            return JsonResponse({'status': 'error', 'message': 'RFID Assignment not found for the given animal ID'}, status=404)

        animal = rfid_assignment.animal

        # Create the WeightMeasurement
        previous_measurement = WeightMeasurement.objects.filter(animal=animal).order_by('-timestamp').first()
        weight_change = ((weight - previous_measurement.weight) / previous_measurement.weight) * 100 if previous_measurement else 0.0

        measurement = WeightMeasurement.objects.create(
            rfid_assignment=rfid_assignment,
            animal=animal,
            weight=weight,
            weight_change=weight_change,
            recorder=request.user
        )

        # Mark the "Take Initial Weight" task as completed
        task = Task.objects.filter(experiment=experiment, title="Take Initial Weight").first()
        if task and not task.is_completed:
            task.is_completed = True
            task.save()

        # Mark the "Weigh-In" event as completed
        event = CalendarEvent.objects.filter(experiment=experiment, title__icontains="Weigh-In", start_date__gte=timezone.now().date()).first()
        if event:
            event.completed = True
            event.completed_at = timezone.now()
            event.save()

        # Update weighed animals in session
        weighed_animals = request.session.get(f'weighed_animals_{experiment_id}', [])
        weighed_animals.append(animal.animal_index)
        request.session[f'weighed_animals_{experiment_id}'] = list(set(weighed_animals))

        return JsonResponse({'status': 'success', 'rfid': rfid_assignment.rfid})

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
@login_required
@require_POST
def enter_tumor_size(request, org_id, experiment_id):
    experiment = get_object_or_404(Experiment.objects.filter(organization_id=org_id), id=experiment_id)
    
    try:
        data = json.loads(request.body)
        animal_id = data.get('animal_id')
        tumor_size = data.get('tumor_size')
        
        if not animal_id or not tumor_size:
            return JsonResponse({'status': 'error', 'message': 'Invalid data'}, status=400)

        try:
            tumor_size = float(tumor_size)
        except ValueError:
            return JsonResponse({'status': 'error', 'message': 'Invalid tumor size value'}, status=400)

        # Retrieve RFIDAssignment and Animal
        rfid_assignment = RFIDAssignment.objects.filter(
            experiment=experiment, animal__id=animal_id, experiment__organization_id=org_id
        ).first()

        if not rfid_assignment:
            return JsonResponse({'status': 'error', 'message': 'RFID Assignment not found for the given animal ID'}, status=404)
        
        animal = rfid_assignment.animal

        # Create or update WeightMeasurement
        measurement = WeightMeasurement.objects.filter(animal=animal).order_by('-timestamp').first()
        if not measurement:
            measurement = WeightMeasurement.objects.create(
                rfid_assignment=rfid_assignment,
                animal=animal,
                tumor_size=tumor_size,
                recorder=request.user,
                timestamp=timezone.now()
            )
        else:
            measurement.tumor_size = tumor_size
            measurement.save()

        # Mark the "Take Initial Tumor Size" task as completed
        task = Task.objects.filter(experiment=experiment, title="Take Initial Tumor Size").first()
        if task and not task.is_completed:
            task.is_completed = True
            task.save()

        # Mark the "Tumor Measurement" event as completed
        event = CalendarEvent.objects.filter(experiment=experiment, title__icontains="Tumor Measurement", start_date__gte=timezone.now().date()).first()
        if event:
            event.completed = True
            event.completed_at = timezone.now()
            event.save()

        # Update weighed animals in session
        weighed_animals = request.session.get(f'weighed_animals_{experiment_id}', [])
        weighed_animals.append(animal.animal_index)
        request.session[f'weighed_animals_{experiment_id}'] = list(set(weighed_animals))

        return JsonResponse({'status': 'success', 'message': 'Tumor size recorded successfully'})

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

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

            # Fetch and delete the strain
            strain = get_object_or_404(Strain, name=strain_name)
            strain.delete()

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': 'Invalid request method.'})
@login_required
def strain_analytics(request, org_id, strain_name):
    organization = get_object_or_404(Organization, id=org_id)

    # Filter strains by experiments within the user's organization
    strains = Strain.objects.filter(
        experiment__owner=request.user,
        experiment__organization=organization  # Ensure the experiment belongs to the correct organization
    ).distinct() | Strain.objects.filter(
        experiment__collaborators__user=request.user,
        experiment__organization=organization  # Ensure collaborators are part of the correct organization
    ).distinct()

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
                        weight_changes = []
                        tumor_size_changes = []

                        for m in session_measurements:
                            initial_weight = baseline_measurements[m.rfid_assignment.animal.animal_index]['weight']
                            initial_tumor_size = baseline_measurements[m.rfid_assignment.animal.animal_index]['tumor_size']
                            weight_change = m.weight - initial_weight
                            tumor_size_change = (m.tumor_size - initial_tumor_size) if initial_tumor_size and m.tumor_size else 0

                            weight_changes.append(weight_change)
                            if initial_tumor_size and m.tumor_size:
                                tumor_size_changes.append(tumor_size_change)

                        avg_weight_change = sum(weight_changes) / len(weight_changes)
                        avg_tumor_size_change = sum(tumor_size_changes) / len(tumor_size_changes) if tumor_size_changes else 0

                        session_data.append({
                            'weigh_in_number': current_session,
                            'avg_weight_change': avg_weight_change,
                            'avg_tumor_size_change': avg_tumor_size_change
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
                weight_changes = []
                tumor_size_changes = []

                for m in session_measurements:
                    initial_weight = baseline_measurements[m.rfid_assignment.animal.animal_index]['weight']
                    initial_tumor_size = baseline_measurements[m.rfid_assignment.animal.animal_index]['tumor_size']
                    weight_change = m.weight - initial_weight
                    tumor_size_change = (m.tumor_size - initial_tumor_size) if initial_tumor_size and m.tumor_size else 0

                    weight_changes.append(weight_change)
                    if initial_tumor_size and m.tumor_size:
                        tumor_size_changes.append(tumor_size_change)

                avg_weight_change = sum(weight_changes) / len(weight_changes)
                avg_tumor_size_change = sum(tumor_size_changes) / len(tumor_size_changes) if tumor_size_changes else 0

                session_data.append({
                    'weigh_in_number': current_session,
                    'avg_weight_change': avg_weight_change,
                    'avg_tumor_size_change': avg_tumor_size_change
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
def analytics(request, experiment_id):
    experiment = get_object_or_404(Experiment.objects.for_user(request.user), id=experiment_id)

    animals = RFIDAssignment.objects.for_user(request.user).filter(experiment=experiment)
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


@csrf_exempt  # You can adjust this based on your CSRF strategy
@login_required
def save_rfids(request, org_id, experiment_id):
    if request.method == 'POST':
        experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)
        
        data = json.loads(request.body)
        rfids = data.get('rfids', [])
        
        for rfid_data in rfids:
            animal_index = rfid_data.get('animal_index')
            rfid_value = rfid_data.get('rfid')

            # Fetch the animal by its index within the experiment
            animal = get_object_or_404(Animal, experiment=experiment, animal_index=animal_index)

            # Create or update the RFIDAssignment
            RFIDAssignment.objects.update_or_create(
                experiment=experiment, animal=animal, defaults={'rfid': rfid_value}
            )

        return JsonResponse({'status': 'success', 'message': 'RFID assignments saved successfully'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)