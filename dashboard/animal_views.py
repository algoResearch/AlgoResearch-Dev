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
def animals(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    animals = Animal.objects.filter(experiment=experiment).order_by('animal_index')
    context = {
        'experiment': experiment,
        'animals': animals,
    }
    return render(request, 'animals/animals.html', context)

@login_required
def cage_configuration(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    if request.method == 'POST':
        form = CageConfigurationForm(request.POST)  # Assuming form handling
        if form.is_valid():
            form.save()
            return redirect('cage_configuration', experiment_id=experiment_id)
    else:
        cages = RFIDAssignment.objects.filter(experiment=experiment).order_by('cage_number')
        form = CageConfigurationForm(initial={'cages': cages})  # Prefill the form with existing data
    return render(request, 'cage_configuration.html', {'form': form, 'experiment': experiment})

@login_required
def map_rfid(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    rfids = RFIDAssignment.objects.filter(experiment=experiment)
    return render(request, 'map_rfid.html', {'rfids': rfids, 'experiment': experiment})

@login_required
def data_collection(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    assigned_rfids = RFIDAssignment.objects.filter(experiment=experiment)

    if request.method == 'POST':
        data = json.loads(request.body)
        for entry in data:
            animal_id = entry.get('animal_id')
            weight = entry.get('weight')
            animal = Animal.objects.get(id=animal_id)
            WeightMeasurement.objects.create(animal=animal, weight=weight)

        return JsonResponse({'status': 'success', 'message': 'Data collected successfully'})
    
    context = {
        'assigned_rfids': assigned_rfids,
        'experiment': experiment
    }
    return render(request, 'data_collection.html', context)

