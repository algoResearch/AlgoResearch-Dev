from django.contrib import messages as django_messages
from django.core import serializers
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q, F, Avg, Max, Min, Count
from django.utils import timezone
from .models import (Conversation, Message, User, GroupMember, Experiment, RFIDAssignment, WeightMeasurement, Collaborator, CalendarEvent, Drug, Strain, Comment, Friend, Cage, Animal, Sample, Dose, Observation, Comment)
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, authenticate
import pandas as pd
from django.views.decorators.csrf import csrf_exempt
import random
from django.contrib.auth import logout
from django.db import IntegrityError
from .forms import CustomUserCreationForm, UpdateProfileForm, ExperimentForm, ImportForm
import json
from datetime import datetime
from django.http import HttpResponseRedirect
from django.utils.safestring import mark_safe
from .forms import UserProfileForm
from .forms import ProfilePictureForm
from .forms import UpdateProfileForm, OverviewForm, ObservationForm, SampleForm, DoseForm
from django.views.decorators.http import require_http_methods
from django.utils.dateparse import parse_datetime
import csv
from .models import Invitation, UserAction
from datetime import date
from django.urls import reverse

@login_required
def create_experiment(request):
    if request.method == 'POST':
        # Extract data from the request safely using get with default values
        name = request.POST.get('name', '')
        number_of_animals = int(request.POST.get('number_of_animals', 0))
        number_of_groups = int(request.POST.get('number_of_groups', 0))
        max_per_cage = int(request.POST.get('max_per_cage', 0))
        investigators_data = request.POST.get('investigators', '[]')  # Get investigators JSON data
        drug_data = request.POST.get('drugs', '[]')  # Get drug JSON data
        strain_data = request.POST.get('strains', '[]')  # Get strain JSON data
        rfid_required = request.POST.get('rfid_required') == '1'
        weight_schedule = request.POST.get('weight_schedule', 'no')
        weigh_in_interval = int(request.POST.get('weigh_in_interval', 0)) if weight_schedule == 'yes' else None
        experiment_duration = int(request.POST.get('experiment_duration', 0)) if weight_schedule == 'yes' else None

        # Extract monitoring options
        monitor_options = request.POST.getlist('monitor_options')
        monitor_weight = 'weight' in monitor_options
        monitor_tumor = 'tumor' in monitor_options

        # Create the Experiment object
        experiment = Experiment.objects.create(
            name=name,
            number_of_animals=number_of_animals,
            number_of_groups=number_of_groups,
            rfid_required=rfid_required,
            max_per_cage=max_per_cage,
            weigh_in_interval=weigh_in_interval,
            duration=experiment_duration,
            owner=request.user,
            monitor_weight=monitor_weight,
            monitor_tumor=monitor_tumor
        )

        # Log the action of creating the experiment
        UserAction.objects.create(
            user=request.user,
            action=f"{request.user.username} created the experiment '{experiment.name}'",
            additional_info=f"Experiment ID: {experiment.id}"
        )

        # Assign animals to cages after the experiment is created
        assign_animals_to_cages(experiment, number_of_animals, max_per_cage)

        # Parse and add drugs to the experiment
        try:
            drugs = json.loads(drug_data)  # Convert JSON string to Python list
            for drug in drugs:
                Drug.objects.create(name=drug, experiment=experiment)  # Create the drug
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid drugs data format. Please try again.'})

        # Parse and add strains to the experiment
        try:
            strains = json.loads(strain_data)  # Convert JSON string to Python list
            for strain in strains:
                Strain.objects.create(name=strain, experiment=experiment)  # Create the strain
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid strains data format. Please try again.'})

        # Parse the investigators data
        try:
            investigators = json.loads(investigators_data)  # Convert JSON string to Python list
            for investigator in investigators:
                username = investigator.get('username')
                role = investigator.get('role')

                # Get the user instance
                user = get_object_or_404(User, username=username)

                # Add user as a collaborator to the experiment
                Collaborator.objects.create(
                    experiment=experiment,
                    user=user,
                    role=role
                )

                # Log the action of adding the collaborator
                UserAction.objects.create(
                    user=user,
                    action=f"{user.username} was added as a collaborator to the experiment '{experiment.name}'",
                    additional_info=f"Experiment ID: {experiment.id}, Role: {role}"
                )

                # Find or create a single conversation between two users, regardless of order
                conversation = Conversation.objects.filter(
                    type='private'
                ).filter(
                    (Q(user1=request.user) & Q(user2=user)) | (Q(user1=user) & Q(user2=request.user))
                ).first()

                if not conversation:
                    conversation = Conversation.objects.create(
                        type='private',
                        user1=request.user,
                        user2=user,
                        name=f"Discussion with {user.username}"
                    )

                # Create a notification or message for the collaborator
                message_content = f"You have been added to the experiment '{experiment.name}' as a {role}."
                Message.objects.create(
                    sender=request.user,
                    content=message_content,
                    conversation=conversation
                )

                # Automatically add the collaborator's calendar events if the experiment has a weigh-in schedule
                if weight_schedule == 'yes' and weigh_in_interval and experiment_duration:
                    current_date = timezone.now().date()
                    while current_date < timezone.now().date() + timezone.timedelta(days=experiment_duration):
                        CalendarEvent.objects.create(
                            user=user,
                            title=f"Weigh-In for {experiment.name} (Collaborator)",
                            start_date=current_date,
                            end_date=current_date,
                            experiment=experiment,
                            color='red'  # Assign the color red for collaborator events
                        )
                        current_date += timezone.timedelta(days=weigh_in_interval)
        except json.JSONDecodeError:
            # Handle JSON parsing error
            return JsonResponse({'status': 'error', 'message': 'Invalid investigators data format. Please try again.'})

        # Create events based on weigh-in schedule for the owner
        if weight_schedule == 'yes' and weigh_in_interval and experiment_duration:
            current_date = timezone.now().date()
            while current_date < timezone.now().date() + timezone.timedelta(days=experiment_duration):
                # Add the event to the owner's calendar
                CalendarEvent.objects.create(
                    user=request.user,
                    title=f"Weigh-In for {experiment.name}",
                    start_date=current_date,
                    end_date=current_date,
                    experiment=experiment,
                    color='blue'
                )
                current_date += timezone.timedelta(days=weigh_in_interval)

        # Return a JSON response with the experiment ID for redirection
        return JsonResponse({'status': 'success', 'experiment_id': experiment.id})

    # If not a POST request, render the form again
    return render(request, 'new-experiment.html')


def assign_animals_to_cages(experiment, number_of_animals, max_per_cage):
    # Fetch existing animals for the experiment and convert to a list
    animals = list(Animal.objects.filter(experiment=experiment))

    # Generate missing animals if needed
    for i in range(len(animals), number_of_animals):
        animal_index = i + 1  # Ensure the animal index is unique and non-null
        new_animal = Animal.objects.create(
            experiment=experiment,
            animal_index=animal_index,
        )
        animals.append(new_animal)  # Append the new animal to the list

        # Associate the strains and drugs from the experiment to the animal
        new_animal.strains.set(experiment.strain_list.all())
        new_animal.drugs.set(experiment.drug_list.all())

    # Assign animals to cages
    animal_counter = 0
    for cage_number in range(1, (number_of_animals // max_per_cage) + 2):
        for _ in range(max_per_cage):
            if animal_counter < len(animals):
                animal = animals[animal_counter]
                
                # Generate a unique RFID for each assignment
                unique_rfid = f'RFID_{experiment.id}_{animal.animal_index}'  # Example: RFID_1_1

                # Check if RFID already exists in the current experiment
                if not RFIDAssignment.objects.filter(rfid=unique_rfid).exists():
                    RFIDAssignment.objects.create(
                        rfid=unique_rfid,
                        animal=animal,
                        experiment=experiment,
                        cage_number=cage_number
                    )
                    animal_counter += 1
                else:
                    # Handle the case where RFID is already in use
                    print(f"Skipping RFID {unique_rfid} as it already exists.")
            else:
                break
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



def add_experiment(request):
    if request.method == 'POST':
        name = request.POST['name']
        number_of_animals = int(request.POST['number_of_animals'])
        number_of_groups = int(request.POST['number_of_groups'])
        max_per_cage = int(request.POST['max_per_cage'])
        investigators = request.POST['investigators']
        rfid_required = request.POST.get('rfid_required') == 'on'
        weight_schedule = request.POST['weight_schedule']
        weigh_in_interval = int(request.POST['weigh_in_interval']) if weight_schedule == 'yes' else None
        experiment_duration = int(request.POST['experiment_duration']) if weight_schedule == 'yes' else None

        experiment = Experiment.objects.create(
            name=name,
            number_of_animals=number_of_animals,
            number_of_groups=number_of_groups,
            investigators=investigators,
            rfid_required=rfid_required,
            max_per_cage=max_per_cage,
            weigh_in_interval=weigh_in_interval,
            owner=request.user,
            duration=experiment_duration
        )
        return redirect('experiment_summary', experiment_id=experiment.id)

    return render(request, 'new-experiment.html')

@login_required
def import_export(request):
    """Render a page for both importing and exporting data."""
    form = ImportForm()
    return render(request, 'import_export.html', {'form': form})


@login_required
def import_data(request):
    # Ensure the request method is POST
    if request.method == 'POST':
        form = ImportForm(request.POST, request.FILES)
        
        # Check if the form is valid
        if form.is_valid():
            file = form.cleaned_data['import_file']

            try:
                # Read and decode the CSV file
                csv_file = file.read().decode('utf-8').splitlines()
                reader = csv.reader(csv_file)
                headers = next(reader)  # Read the header row

                # Validate the CSV headers
                if headers != ['Animal Index', 'Weight', 'Tumor Size', 'Timestamp']:
                    return JsonResponse({'status': 'error', 'message': 'Invalid CSV format. Expected headers: Animal Index, Weight, Tumor Size, Timestamp'})

                # Prepare data for experiment creation
                data = []
                for row in reader:
                    print(f"Processing row: {row}")  # Debugging: Print each row
                    # Parse each row and store it in the list, converting strings to appropriate types
                    data.append({
                        'animal_index': row[0].strip(),
                        'weight': float(row[1].strip()),  # Convert weight to float
                        'tumor_size': float(row[2].strip()),  # Convert tumor size to float
                        'timestamp': row[3].strip(),
                    })

                # Extract experiment details from the form
                experiment_name = request.POST.get('experiment_name')
                weight_schedule = request.POST.get('weight_schedule')
                
                # Convert weigh_in_interval and experiment_duration to integers if provided
                weigh_in_interval = request.POST.get('weigh_in_interval', None)
                experiment_duration = request.POST.get('experiment_duration', None)
                
                # Handle empty values correctly
                weigh_in_interval = int(weigh_in_interval) if weigh_in_interval else None
                experiment_duration = int(experiment_duration) if experiment_duration else None

                # Create a new experiment
                experiment = Experiment.objects.create(
                    name=experiment_name,
                    number_of_animals=len(set([d['animal_index'] for d in data])),
                    owner=request.user,
                    weight_schedule=(weight_schedule == 'yes'),
                    weigh_in_interval=weigh_in_interval,
                    experiment_duration=experiment_duration
                )

                # Save drugs and strains
                drugs = request.POST.getlist('drugs')
                strains = request.POST.getlist('strains')
                for drug_name in drugs:
                    # Create or get the drug instance and associate with the experiment
                    drug, created = Drug.objects.get_or_create(name=drug_name)
                    experiment.drug_list.add(drug)
                
                for strain_name in strains:
                    # Create or get the strain instance and associate with the experiment
                    strain, created = Strain.objects.get_or_create(name=strain_name)
                    experiment.strain_list.add(strain)

                # Save imported data to the database
                for row in data:
                    # Create or get animal associated with the experiment
                    animal, _ = Animal.objects.get_or_create(
                        experiment=experiment,
                        animal_index=row['animal_index']
                    )
                    
                    # Create RFID assignment if not existing
                    rfid_assignment, _ = RFIDAssignment.objects.get_or_create(
                        experiment=experiment,
                        animal=animal,
                        defaults={'rfid': f"RFID_{experiment.id}_{animal.animal_index}", 'initial_weight': row['weight']}
                    )

                    # Save the weight measurement data
                    WeightMeasurement.objects.create(
                        animal=animal,
                        rfid_assignment=rfid_assignment,
                        weight=row['weight'],
                        tumor_size=row['tumor_size'],
                        timestamp=row['timestamp'],
                        recorder=request.user,  # Set the recorder to the current logged-in user
                    )

                # Redirect to experiment summary page
                return HttpResponseRedirect(reverse('experiment_summary', args=[experiment.id]))

            except Exception as e:
                return JsonResponse({'status': 'error', 'message': str(e)})

        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid file. Please upload a valid CSV file.'})

    # If request method is GET, render the import form
    form = ImportForm()
    return render(request, 'import.html', {'form': form})
@login_required
def generate_csv_for_experiment(experiment):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="experiment_{experiment.id}_data.csv"'
    writer = csv.writer(response)

    # Write CSV headers
    writer.writerow(['Animal Index', 'Weight', 'Tumor Size', 'Timestamp'])

    # Get data for each measurement in the experiment
    measurements = WeightMeasurement.objects.filter(rfid_assignment__experiment=experiment).order_by('rfid_assignment__animal__animal_index', 'timestamp')

    # Write data rows
    for measurement in measurements:
        writer.writerow([
            measurement.rfid_assignment.animal.animal_index,
            measurement.weight,
            measurement.tumor_size if measurement.tumor_size else 'N/A',
            measurement.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        ])

    return response



@login_required
def export_data(request):
    user = request.user
    
    # Filter experiments where the user is the owner or a collaborator
    experiments = Experiment.objects.filter(
        Q(owner=user) | Q(collaborators__user=user)
    ).distinct()
    
    if request.method == 'POST':
        experiment_id = request.POST.get('experiment')
        experiment = get_object_or_404(experiments, id=experiment_id)

        # Generate the CSV file
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="experiment_{experiment.id}_data.csv"'

        writer = csv.writer(response)
        
        # Retrieve the animals related to the selected experiment
        animals = experiment.animal_set.all()

        # Retrieve measurements for animals in the selected experiment
        measurements = WeightMeasurement.objects.filter(animal__in=animals)

        # Write headers
        writer.writerow(['Animal Index', 'Weight', 'Tumor Size', 'Weight Change', 'Tumor Size Change', 'Timestamp'])

        # Write data
        for measurement in measurements:
            writer.writerow([
                measurement.animal.animal_index,
                measurement.weight,
                measurement.tumor_size if measurement.tumor_size else 'N/A',
                measurement.weight_change if measurement.weight_change else 'N/A',
                measurement.tumor_size_change if measurement.tumor_size_change else 'N/A',
                measurement.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            ])

        # Track the user's export action
        UserAction.objects.create(
            user=user,
            action=f"Exported data for experiment {experiment.name}",
            additional_info=f"Experiment ID: {experiment.id}"
        )

        return response  # Return the generated CSV response
    
    # Only return experiments where the user is involved
    return render(request, 'export.html', {'experiments': experiments})

def collaborators(request, experiment_id):
    experiment = get_object_or_404(Experiment, pk=experiment_id)
    collaborators = Collaborator.objects.filter(experiment=experiment)
    
    context = {
        'experiment': experiment,
        'collaborators': collaborators,
    }
    return render(request, 'collaborators.html', context)