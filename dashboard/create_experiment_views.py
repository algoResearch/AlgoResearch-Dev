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
def create_experiment(request):
    if request.method == 'POST':
        # Extract data from the request safely using `get` with default values
        name = request.POST.get('name', '')
        number_of_animals = int(request.POST.get('number_of_animals', 0))
        number_of_groups = int(request.POST.get('number_of_groups', 0))
        max_per_cage = int(request.POST.get('max_per_cage', 0))
        investigators = request.POST.get('investigators', '')
        rfid_required = request.POST.get('rfid_required') == '1'
        weight_schedule = request.POST.get('weight_schedule', 'no')
        weigh_in_interval = int(request.POST.get('weigh_in_interval', 0)) if weight_schedule == 'yes' else None
        experiment_duration = int(request.POST.get('experiment_duration', 0)) if weight_schedule == 'yes' else None
        drug = request.POST.get('drug', '')  # Safely get the 'drug' field
        strain = request.POST.get('strain', '')

        # Extract monitoring options
        monitor_options = request.POST.getlist('monitor_options')
        monitor_weight = 'weight' in monitor_options
        monitor_tumor = 'tumor' in monitor_options

        # Create the Experiment object
        experiment = Experiment.objects.create(
            name=name,
            number_of_animals=number_of_animals,
            number_of_groups=number_of_groups,
            investigators=investigators,
            rfid_required=rfid_required,
            max_per_cage=max_per_cage,
            weigh_in_interval=weigh_in_interval,
            duration=experiment_duration,
            owner=request.user,
            drug=drug,
            strain=strain,
            monitor_weight=monitor_weight,
            monitor_tumor=monitor_tumor
        )

        # Assign animals to cages after the experiment is created
        assign_animals_to_cages(experiment, number_of_animals, max_per_cage)

        # Create events based on weigh-in schedule
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

                # Add the event to collaborators' calendars in red
                for collaborator in experiment.collaborators.all():
                    CalendarEvent.objects.create(
                        user=collaborator.user,
                        title=f"Weigh-In for {experiment.name} (Collaborator)",
                        start_date=current_date,
                        end_date=current_date,
                        experiment=experiment,
                        color='red'
                    )

                current_date += timezone.timedelta(days=weigh_in_interval)

        return redirect('experiment_summary', experiment_id=experiment.id)

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