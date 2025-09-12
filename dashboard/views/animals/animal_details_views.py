from django.contrib import messages
from django.core import serializers
from django.shortcuts import render, redirect, get_object_or_404, reverse
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test 
from django.core.serializers.json import DjangoJSONEncoder
from random import randint
from dashboard.core.permissions import check_cage_access, ensure_access
import qrcode
from io import BytesIO
import base64
from django.core.paginator import Paginator
from django.db.models import Q, F, Avg, Max, Min, Count, Prefetch
from django.utils import timezone
from django.utils.timezone import now
import hashlib
from dashboard.views.experiments.data_collection_views import generate_unique_signature
from django.utils.decorators import method_decorator
from dashboard.models import (Conversation, SpeciesEntry, Protocol,  Attachment, Message, User, UserAction, GroupMember, Group, Organization,RFID, Experiment, RFIDAssignment, WeightMeasurement, Collaborator, CalendarEvent, Comment, Friend, Cage, Animal, Sample, Dose, Observation, Comment)
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, authenticate
from uuid import uuid4
import pandas as pd
from collections import defaultdict
from django.views.decorators.csrf import csrf_exempt
import random
from django.core.cache import cache
from django.contrib.auth import logout
from django.db import IntegrityError, transaction
from dashboard.forms import CustomUserCreationForm, UpdateProfileForm, ExperimentForm, AdminCreatedFormForm, AnimalRegistrationForm , AnimalForm, CageCreationForm, AttachmentForm
import traceback
import json
from django.http import HttpResponseRedirect
from django.utils.safestring import mark_safe
from dashboard.forms import UserProfileForm
from dashboard.forms import ProfilePictureForm
from dashboard.forms import UpdateProfileForm, OverviewForm, ObservationForm, SampleForm, DoseForm
from django.views.decorators.http import require_http_methods
from django.utils.dateparse import parse_datetime
import csv
from dashboard.models import Invitation
from datetime import date, datetime
import json
from django.contrib import messages
from dashboard.models import Experiment, Animal, Comment, WeightMeasurement, Sample, Dose, Observation
import logging
logger = logging.getLogger(__name__)

def is_admin_or_principal(user):
    return user.role in ['admin', 'principal_admin']

def is_principal_admin(user):
    return user.role == 'principal_admin'

def is_data_collector(user):
    return user.role in ['researcher', 'officer', 'admin', 'principal_admin']

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

    # Dynamically calculate the age
    age_in_days = (date.today() - animal.date_of_birth).days if animal.date_of_birth else None
    logger.debug(f"Calculated Age in Days: {age_in_days}")

    logger.debug(f"Animal Date of Birth: {animal.date_of_birth}, Age in Days: {age_in_days}")
    # Retrieve data
    observations = animal.observations.all()
    samples = Sample.objects.filter(animal=animal)
    doses = Dose.objects.filter(animal=animal)
    attachments = animal.attachments.all()
    weights = WeightMeasurement.objects.filter(animal=animal).order_by('timestamp')
    for attachment in attachments:
        file_name = attachment.file.name.lower()
        if file_name.endswith('.pdf'):
            attachment.file_type = 'pdf'
        elif file_name.endswith(('.jpg', '.jpeg', '.png')):
            attachment.file_type = 'image'
        else:
            attachment.file_type = 'other'
    # Handle file uploads
    if request.method == 'POST':
        attachment_form = AttachmentForm(request.POST, request.FILES)
        if attachment_form.is_valid():
            attachment = attachment_form.save(commit=False)
            attachment.animal = animal
            attachment.save()
            return redirect('animal_details', org_id=org_id, experiment_id=experiment.id, animal_index=animal.animal_index)
    else:
        attachment_form = AttachmentForm()

    context = {
        'animal': animal,
        'observations': observations,
        'samples': samples,
        'doses': doses,
        'weights': weights,
        'attachments': attachments,
        'attachment_form': attachment_form,  # Add the form to the context
        'org_id': org_id,
        'experiment': experiment,
        'age_in_days': age_in_days,  # Pass the dynamically calculated age
    }
    return render(request, 'misc/animal_details.html', context)

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
@user_passes_test(is_data_collector)
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

            # Log UserAction
            UserAction.objects.create(
                user=request.user,
                organization=request.user.organization,
                action="Add Sample",
                additional_info=f"Sample '{sample.sample_id}' of type '{sample.sample_type}' added to animal {animal_index}.",
                typed_signature="N/A",
                unique_signature=generate_unique_signature(request.user, f"Add Sample {animal_index}", now()),
                timestamp=now(),
            )

            return redirect('animal_details', org_id=org_id, experiment_id=experiment.id, animal_index=animal.animal_index)
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
@user_passes_test(is_data_collector)
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

            # Log UserAction
            UserAction.objects.create(
                user=request.user,
                organization=request.user.organization,
                action="Add Dose",
                additional_info=(
                    f"Dose for drug '{dose.drug_name}' (dose: {dose.dose}, "
                    f"concentration: {dose.stock_concentration}, volume: {dose.dose_volume}) "
                    f"added to animal {animal_index}."
                ),
                typed_signature="N/A",
                unique_signature=generate_unique_signature(request.user, f"Add Dose {animal_index}", now()),
                timestamp=now(),
            )

            return redirect('animal_details', org_id=org_id, experiment_id=experiment.id, animal_index=animal.animal_index)
    else:
        form = DoseForm()

    context = {
        'experiment': experiment,
        'animal': animal,
        'form': form,
        'org_id': org_id,
    }
    return render(request, 'add_dose.html', context)

from collections import defaultdict
from django.shortcuts import get_object_or_404, render
from django.db.models import Max
@login_required
def cage_qr_codes(request, org_id, cage_id):
    cage = get_object_or_404(Cage, id=cage_id, organization_id=org_id)
    animals = cage.animals.all()

    # Base URL for the QR code
    base_url = request.build_absolute_uri('/')[:-1]
    cage_url = f"{base_url}{reverse('cage_details', args=[org_id, cage.id])}"

    # Generate QR Code
    qr = qrcode.make(cage_url)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    qr_image = base64.b64encode(buffer.getvalue()).decode()

    # Prepare animal details
    animal_data = [
        {
            "animal_index": animal.animal_index,
            "rfid_tag": animal.rfid_tag,
            "date_of_birth": animal.date_of_birth,
            "strain": animal.strain,
        }
        for animal in animals
    ]

    return JsonResponse({
        "qr_image": f"data:image/png;base64,{qr_image}",
        "cage_name": cage.name,
        "cage_url": cage_url,
        "animal_data": animal_data,
    })

def animals(request, experiment_id, org_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)
    groups = Group.objects.filter(experiment=experiment)

    # Initialize a dictionary to hold groups and their animals
    grouped_animals_data = defaultdict(list)

    for group in groups:
        animals_in_group = Animal.objects.filter(group=group).select_related('cage').order_by('animal_index')

        for animal in animals_in_group:
            # Initialize base animal data
            animal_data = {
                'animal_index': animal.animal_index,
                'cage_number': animal.cage.cage_number if animal.cage else 'N/A',
                'weight': 'N/A',
                'tumor_size': 'N/A',
                'tracking_date': animal.tracking_date.strftime('%Y-%m-%d') if animal.tracking_date else 'N/A',
                'weight_change_first': 'N/A',
                'tumor_size_change_first': 'N/A',
                'weight_flag': None,
                'tumor_flag': None,
                'is_removed': animal.removed,
            }

            # Fetch the RFID assignment
            rfid_assignment = RFIDAssignment.objects.filter(animal=animal, experiment=experiment).first()
            if rfid_assignment:
                # Fetch all weight measurements for this animal
                measurements = WeightMeasurement.objects.filter(rfid_assignment=rfid_assignment).order_by('timestamp')
                
                if measurements.exists():
                    first_measurement = measurements.first()
                    last_weight_measurement = measurements.filter(weight__isnull=False).last()
                    last_tumor_measurement = measurements.filter(tumor_size__isnull=False).last()

                    # Assign the latest weight and tumor size
                    if last_weight_measurement:
                        animal_data['weight'] = last_weight_measurement.weight
                    if last_tumor_measurement:
                        animal_data['tumor_size'] = last_tumor_measurement.tumor_size

                    # Calculate weight and tumor size changes from the first measurement
                    if first_measurement:
                        if first_measurement.weight is not None and last_weight_measurement:
                            animal_data['weight_change_first'] = (
                                last_weight_measurement.weight - first_measurement.weight
                            )
                        if first_measurement.tumor_size is not None and last_tumor_measurement:
                            animal_data['tumor_size_change_first'] = (
                                last_tumor_measurement.tumor_size - first_measurement.tumor_size
                            )

                    # Check thresholds
                    weight_warning_threshold = experiment.warning_weight_percentage or 0
                    weight_removal_threshold = experiment.removal_weight_percentage or float('inf')
                    tumor_warning_threshold = experiment.tumor_volume_warning  or 0
                    tumor_removal_threshold = experiment.tumor_volume_removal or float('inf')

                    # Weight threshold checks
                    if last_weight_measurement and rfid_assignment.initial_weight:
                        weight_loss_percentage = (
                            (rfid_assignment.initial_weight - last_weight_measurement.weight)
                            / rfid_assignment.initial_weight
                        ) * 100

                        if weight_loss_percentage >= weight_removal_threshold:
                            animal_data['weight_flag'] = 'removal'
                        elif weight_loss_percentage >= weight_warning_threshold:
                            animal_data['weight_flag'] = 'warning'

                    # Tumor size threshold checks
                    if last_tumor_measurement:
                        if last_tumor_measurement.tumor_size >= tumor_removal_threshold:
                            animal_data['tumor_flag'] = 'removal'
                        elif last_tumor_measurement.tumor_size >= tumor_warning_threshold:
                            animal_data['tumor_flag'] = 'warning'

            grouped_animals_data[group.name].append(animal_data)

    context = {
        'experiment': experiment,
        'grouped_animals_data': dict(grouped_animals_data),
        'org_id': org_id,
    }

    # Debugging output
    logger.info(f"Grouped animals data: {grouped_animals_data}")
    return render(request, 'misc/animals.html', context)

@csrf_exempt
@login_required
@user_passes_test(is_admin_or_principal)
def cage_creation_view(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            cages_data = data.get('cages', [])

            with transaction.atomic():
                for cage_info in cages_data:
                    assigned_user_ids = cage_info.get('assigned_user_ids', [])
                    assigned_users = User.objects.filter(id__in=assigned_user_ids, organization=organization)

                    cage = Cage.objects.create(
                        name=cage_info['name'],
                        capacity=cage_info['population'],
                        organization=organization
                    )
                    cage.assigned_users.set(assigned_users)

                    last_index = Animal.objects.filter(organization=organization).aggregate(
                        Max('animal_index')
                    )['animal_index__max'] or 0

                    for animal_info in cage_info['animals']:
                        last_index += 1
                        date_of_birth = datetime.strptime(animal_info['date_of_birth'], '%Y-%m-%d').date()

                        # Assign species directly (no need for get_or_create)
                        species_name = animal_info.get('species', "").strip()

                        animal = Animal.objects.create(
                            cage=cage,
                            organization=organization,
                            rfid_tag=animal_info['rfid_tag'],
                            sex=animal_info['sex'],
                            date_of_birth=date_of_birth,
                            species=species_name,  # ✅ Directly assign species
                            strain=animal_info.get('strain', ""),
                            animal_index=last_index,
                            tracking_date=timezone.now().date()
                            )
                        RFIDAssignment.objects.create(
                            rfid=animal.rfid_tag,
                            animal=animal,
                            experiment=animal.experiment,
                            cage_number=cage.name,
                            removed=False
                        )
            return JsonResponse({'success': True, 'message': 'Cages and animals created successfully with RFID assignments.'})

        except Exception as e:
            logger.error(f"An error occurred: {e}")
            return JsonResponse({'success': False, 'message': f'Failed to create cages and animals: {str(e)}'}, status=500)

    return render(request, 'vivarium/cage_creation.html', {'org_id': org_id})

@login_required
def cage_details(request, org_id, cage_id):
    user = request.user

    # Ensure user has access to the cage
    if not check_cage_access(user, cage_id):
        return HttpResponseForbidden("You do not have permission to view this cage.")

    # Fetch the Cage and its Animals
    cage = get_object_or_404(Cage, id=cage_id, organization_id=org_id)

    if user.role in ['admin', 'principal_admin']:
        # Admins and Principal Admins can view all animals in the cage
        animals = cage.animals.all()
    else:
        # Users can only view animals explicitly assigned to them
        animals = cage.animals.filter(assigned_users=user)

    # Prepare animal data
    animal_data = [
        {
            "id": animal.id,
            "animal_index": animal.animal_index,
            "rfid_tag": animal.rfid_tag,
            "sex": animal.sex,
            "date_of_birth": animal.date_of_birth,
            "species": animal.species,
            "strain": animal.strain,
            "age_in_days": (date.today() - animal.date_of_birth).days if animal.date_of_birth else None,
            "status": "Available" if animal.is_active else "Assigned",
        }
        for animal in animals
    ]

    return render(request, 'vivarium/cage_detail.html', {
        'cage': cage,
        'animal_data': animal_data,
        'org_id': org_id,
    })

@login_required
def vivarium_view(request, org_id):
    user = request.user
    
    if user.role in ['admin', 'principal_admin']:
        # Admins and Principal Admins see all cages and animals
        cages = Cage.objects.filter(organization_id=org_id).prefetch_related('animals')
    else:
        # Regular users see only assigned cages or animals
        cages = Cage.objects.filter(
            organization_id=org_id,
            animals__assigned_users=user
        ).distinct().prefetch_related('animals')

    vivarium_data = []
    for cage in cages:
        # Filter animals: show all for Admins, only assigned for regular users
        if user.role in ['admin', 'principal_admin']:
            animals = cage.animals.all()
        else:
            animals = cage.animals.filter(assigned_users=user)

        # Build the cage data
        cage_data = {
            "cage": cage,
            "animals": []
        }
        for animal in animals:
            age_in_days = (date.today() - animal.date_of_birth).days if animal.date_of_birth else None
            cage_data["animals"].append({
                "id": animal.id,
                "animal_index": animal.animal_index,
                "rfid_tag": animal.rfid_tag,
                "sex": animal.sex,
                "date_of_birth": animal.date_of_birth,
                "species": animal.species,
                "strain": animal.strain,
                "is_available": animal.is_active,
                "age_in_days": age_in_days
            })

        if cage_data["animals"] or user.role in ['admin', 'principal_admin']:
            vivarium_data.append(cage_data)

    return render(request, 'vivarium/vivarium.html', {
        'vivarium_data': vivarium_data,
        'org_id': org_id
    })

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

def generate_unique_rfids(count, assigned_rfids):
    generated_rfids = set()
    while len(generated_rfids) < count:
        new_rfid = f"RFID_{randint(1000, 3000)}"
        if new_rfid not in assigned_rfids and new_rfid not in generated_rfids:
            generated_rfids.add(new_rfid)
    return list(generated_rfids)
def animal_details(request, org_id, animal_index, experiment_id=None):
    # Fetch the animal, with or without an associated experiment
    if experiment_id:
        experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id)
        animal = get_object_or_404(Animal, experiment=experiment, animal_index=animal_index)
    else:
        animal = get_object_or_404(Animal, organization_id=org_id, animal_index=animal_index)
        experiment = animal.experiment if hasattr(animal, 'experiment') else None

    # Fetch the RFID tag directly from the Animal model if available
    rfid_tag = animal.rfid_tag if hasattr(animal, 'rfid_tag') and animal.rfid_tag else "RFID Not Assigned"

    # Fetch weight measurements and prepare data for chart display
    weigh_ins = WeightMeasurement.objects.filter(animal=animal).order_by('timestamp')
    dates = [weigh_in.timestamp.strftime("%Y-%m-%d") for weigh_in in weigh_ins]
    weights = [weigh_in.weight for weigh_in in weigh_ins]
    tumor_sizes = [weigh_in.tumor_size for weigh_in in weigh_ins if weigh_in.tumor_size is not None]

    # Retrieve associated drugs and strains directly from Animal model
    drugs = animal.drugs.all()
    strains = animal.strains.all()

    # Fetch doses for the animal
    doses = Dose.objects.filter(animal=animal).order_by('-timestamp')

    # Fetch attachments for the animal
    attachments = Attachment.objects.filter(animal=animal).order_by('-uploaded_at')
    for attachment in attachments:
        file_name = attachment.file.name.lower()
        attachment.is_image = file_name.endswith(('.jpg', '.jpeg', '.png'))
        attachment.is_pdf = file_name.endswith('.pdf')
        attachment.size = attachment.file.size

    # Prepare the context for rendering
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
        'doses': doses,  # Pass the dose information to the template
        'attachments': attachments,  # Pass attachments with extra attributes
        'org_id': org_id,
    }

    return render(request, 'misc/animal_details.html', context)

@login_required
def vivarium_animal_details(request, org_id, animal_id):
    # Retrieve the animal using its unique primary key (id) and organization ID
    animal = get_object_or_404(Animal, organization_id=org_id, id=animal_id)
    
    # Fetch weight measurements for the animal
    weigh_ins = WeightMeasurement.objects.filter(animal=animal).order_by('timestamp')

    context = {
        'animal': animal,
        'rfid_tag': animal.rfid_tag,
        'weigh_ins': weigh_ins,
        'dates': [wi.timestamp.strftime("%Y-%m-%d %H:%M") for wi in weigh_ins],
        'weights': [wi.weight for wi in weigh_ins],
        'tumor_sizes': [wi.tumor_size for wi in weigh_ins if wi.tumor_size is not None],
        'observations': animal.observations.all(),
        'samples': animal.samples.all(),
        'doses': animal.doses.all(),
        'org_id': org_id,
    }

    return render(request, 'vivarium/vivarium_animal_details.html', context)
@login_required
@user_passes_test(is_data_collector)
def add_sample_no_experiment(request, org_id, animal_index):
    animal = get_object_or_404(Animal, organization_id=org_id, animal_index=animal_index)
    
    if request.method == 'POST':
        form = SampleForm(request.POST)
        if form.is_valid():
            sample = form.save(commit=False)
            sample.animal = animal
            sample.user = request.user
            sample.save()  # Save without experiment
            
            # Use animal.id for the redirect to vivarium_animal_details
            return redirect('vivarium_animal_details', org_id=org_id, animal_id=animal.id)
    else:
        form = SampleForm()

    context = {
        'animal': animal,
        'form': form,
        'org_id': org_id,
    }
    return render(request, 'add_sample.html', context)

@login_required
def add_dose_no_experiment(request, org_id, animal_index):
    animal = get_object_or_404(Animal, organization_id=org_id, animal_index=animal_index)
    if request.method == 'POST':
        form = DoseForm(request.POST)
        if form.is_valid():
            dose = form.save(commit=False)
            dose.animal = animal
            dose.user = request.user
            dose.save()  # Save without experiment
            return redirect('vivarium_animal_details', org_id=org_id, animal_index=animal.animal_index)
    else:
        form = DoseForm()

    context = {
        'animal': animal,
        'form': form,
        'org_id': org_id,
    }
    return render(request, 'add_dose.html', context)

@login_required
@csrf_exempt
def update_overview_no_experiment(request, org_id, animal_index):
    if request.method == 'POST':
        try:
            animal = get_object_or_404(Animal, organization_id=org_id, animal_index=animal_index)
            data = json.loads(request.body)
            animal.update_overview(data)
            return JsonResponse({'success': True, 'message': 'Overview updated successfully'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': 'Error updating overview: ' + str(e)})

    return JsonResponse({'success': False, 'message': 'Invalid request method'})
@login_required
@user_passes_test(is_data_collector)
def add_observation(request, org_id, animal_index, experiment_id=None):
    animal = get_object_or_404(Animal, organization_id=org_id, animal_index=animal_index)
    experiment = get_object_or_404(Experiment, id=experiment_id, organization_id=org_id) if experiment_id else None

    if request.method == 'POST':
        form = ObservationForm(request.POST)
        if form.is_valid():
            observation = form.save(commit=False)
            observation.animal = animal
            observation.user = request.user
            observation.save()

            # Log UserAction
            UserAction.objects.create(
                user=request.user,
                organization=request.user.organization,
                action="Add Observation",
                
                typed_signature="N/A",
                unique_signature=generate_unique_signature(request.user, f"Add Observation {animal_index}", now()),
                timestamp=now(),
            )

            # Redirect based on the presence of experiment_id
            if experiment_id:
                return redirect('animal_details', org_id=org_id, experiment_id=experiment_id, animal_index=animal_index)
            else:
                return redirect('animal_details_no_experiment', org_id=org_id, animal_index=animal_index)
        else:
            return JsonResponse({'errors': form.errors}, status=400)
    
    return JsonResponse({'message': 'GET method not allowed for observation creation.'}, status=405)

def overview_view(request, experiment_id, animal_index):
    animal = get_object_or_404(Animal, experiment_id=experiment_id, animal_index=animal_index)

    # Explicitly access the property
    age_in_days = (date.today() - animal.date_of_birth).days if animal.date_of_birth else None
    logger.debug(f"Animal Age in Days (via property): {age_in_days}")

    if request.method == 'POST':
        # Handle updates
        animal.tail = request.POST.get('tail', animal.tail)
        animal.ear = request.POST.get('ear', animal.ear)
        animal.tag = request.POST.get('tag', animal.tag)
        animal.donor = request.POST.get('donor', animal.donor)
        animal.sex = request.POST.get('sex', animal.sex)
        animal.species = request.POST.get('species', animal.species)
        animal.save()

        messages.success(request, 'Overview updated successfully.')
        return redirect('overview', experiment_id=experiment_id, animal_index=animal_index)

    return render(request, 'misc/animal_details.html', {
        'animal': animal,
        'age_in_days': age_in_days
    })

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

@login_required
def analytics_view(request, animal_index, experiment_id=None):
    # Fetch animal with or without an experiment ID
    if experiment_id:
        animal = get_object_or_404(Animal, experiment_id=experiment_id, animal_index=animal_index)
        measurements = WeightMeasurement.objects.filter(experiment_id=experiment_id, animal_index=animal_index).order_by('timestamp')
    else:
        animal = get_object_or_404(Animal, animal_index=animal_index, experiment__isnull=True)
        measurements = WeightMeasurement.objects.filter(animal=animal).order_by('timestamp')

    # Prepare data for charting
    dates = [measurement.timestamp.strftime("%Y-%m-%d") for measurement in measurements]
    weights = [measurement.weight for measurement in measurements]
    tumor_sizes = [measurement.tumor_size for measurement in measurements if measurement.tumor_size is not None]

    return render(request, 'analytics/analytics.html', {
        'animal': animal,
        'dates': dates,
        'weights': weights,
        'tumor_sizes': tumor_sizes
    })

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
            'tracking_date': assignment.animal.tracking_date,  # Ensure tracking_date is passed
            'weight_change_first': weight_change_first,
            'weight_change_previous': weight_change_previous,
            'tumor_size_change_first': tumor_size_change_first,
            'tumor_size_change_previous': tumor_size_change_previous,
            'experiment_id': assignment.experiment.id,
            'animal_id': assignment.animal.id
        })

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
        Prefetch(
            'weightmeasurement_set',
            queryset=WeightMeasurement.objects.order_by('-timestamp'),
            to_attr='latest_measurements'  # Use latest_measurements to get the most recent data
        )
    ).order_by(f"{sort_order}{sort_field}")

    # Prepare animal data
    animals_data = []
    for assignment in rfid_assignments:
        # Access the latest weight and tumor size measurements
        latest_measurement = assignment.latest_measurements[0] if assignment.latest_measurements else None
        first_measurement = assignment.latest_measurements[-1] if assignment.latest_measurements else None
        previous_measurement = assignment.latest_measurements[1] if len(assignment.latest_measurements) > 1 else None

        weight_change_first = (
            (latest_measurement.weight - first_measurement.weight)
            if first_measurement and latest_measurement and first_measurement.weight is not None and latest_measurement.weight is not None
            else None
        )
        weight_change_previous = (
            (latest_measurement.weight - previous_measurement.weight)
            if previous_measurement and latest_measurement and previous_measurement.weight is not None and latest_measurement.weight is not None
            else None
        )

        animals_data.append({
            'experiment_name': assignment.experiment.name,
            'animal_index': assignment.animal.animal_index,
            'rfid_tag': assignment.rfid,
            'cage_number': assignment.cage_number,
            'weight': latest_measurement.weight if latest_measurement else 'N/A',
            'tumor_size': latest_measurement.tumor_size if latest_measurement else 'N/A',
            'tracking_date': assignment.initial_weight_date,
            'weight_change_first': weight_change_first,
            'weight_change_previous': weight_change_previous,
            'tumor_size_change_first': (
                (latest_measurement.tumor_size - first_measurement.tumor_size)
                if first_measurement and latest_measurement and first_measurement.tumor_size is not None and latest_measurement.tumor_size is not None
                else None
            ),
            'tumor_size_change_previous': (
                (latest_measurement.tumor_size - previous_measurement.tumor_size)
                if previous_measurement and latest_measurement and previous_measurement.tumor_size is not None and latest_measurement.tumor_size is not None
                else None
            ),
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

    return render(request, 'misc/colony.html', {
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
@login_required
@user_passes_test(is_data_collector)
def add_attachment(request, org_id, experiment_id, animal_index):
    if request.method == 'POST':
        file = request.FILES.get('file')
        description = request.POST.get('description', '')
        animal = get_object_or_404(Animal, organization_id=org_id, experiment_id=experiment_id, animal_index=animal_index)
        
        if file:
            attachment = Attachment.objects.create(
                file=file,
                description=description,
                animal=animal,
                uploaded_at=timezone.now(),
            )
            
            # Log UserAction
            UserAction.objects.create(
                user=request.user,
                organization=request.user.organization,
                action="Add Attachment",
                additional_info=f"Attachment '{attachment.file.name}' added to animal {animal_index}.",
                typed_signature="N/A",
                unique_signature=generate_unique_signature(request.user, f"Add Attachment {animal_index}", now()),
                timestamp=now(),
            )

            messages.success(request, "Attachment uploaded successfully.")
        else:
            messages.error(request, "No file was uploaded.")
    
    return redirect('animal_details', org_id=org_id, experiment_id=experiment_id, animal_index=animal_index)

def delete_attachment(request, attachment_id):
    attachment = get_object_or_404(Attachment, id=attachment_id)
    if request.user != attachment.uploaded_by:
        return HttpResponseForbidden('You do not have permission to delete this attachment.')
    
    attachment.delete()
    return JsonResponse({'success': True, 'message': 'Attachment deleted successfully.'})
