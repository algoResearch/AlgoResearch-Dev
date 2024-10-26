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
import logging

logger = logging.getLogger(__name__)



def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
        else:
            print(form.errors)  # This will print form errors to the console
    else:
        form = CustomUserCreationForm()

    return render(request, 'register.html', {'form': form})


@login_required
def home(request):
    return render(request, 'home.html')


@login_required
def home_view(request):
    return render(request, 'home.html')

@login_required
def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('home')  # Redirect to a home page or another page after login
        else:
            messages.error(request, 'Invalid username or password')
    return render(request, 'dashboard/login.html')  # Correct template path


@login_required
def experiment_list(request):
    experiments = Experiment.objects.filter(Q(owner=request.user) | Q(collaborators__user=request.user), ended=False)
    return render(request, 'dashboard/all-experiments.html', {'experiments': experiments})

@login_required
@require_POST
def delete_conversation(request, conversation_id):
    conversation = get_object_or_404(Conversation.objects.filter(
        Q(user1=request.user) | Q(user2=request.user),
        id=conversation_id
    ))
    conversation.messages.all().delete()
    conversation.delete()
    return JsonResponse({'status': 'Conversation deleted'})

@login_required
def conversation_view(request, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id)
    messages = Message.objects.filter(conversation=conversation).order_by('timestamp')

    # Mark all messages as read when the conversation is viewed
    messages.filter(read=False).exclude(sender=request.user).update(read=True)

    # For private conversations, get the other user's profile picture
    if conversation.type == 'private':
        other_user = conversation.user2 if conversation.user1 == request.user else conversation.user1
        other_profile_picture = other_user.profile_picture.url if other_user.profile_picture else None
    else:
        other_profile_picture = None  # Or handle for group conversations if needed

    # Include invitations
    invitations = Invitation.objects.filter(receiver=request.user, experiment__conversation=conversation).select_related('experiment')
    
    context = {
        'selected_conversation_id': conversation_id,
        'messages': messages,
        'invitations': invitations,  # Pass invitations to the template
        'conversation_name': conversation.name if conversation.name else "Conversation",
        'conversation_type': conversation.type,
        'user_id': request.user.id,
        'other_profile_picture': other_profile_picture,
    }
    return render(request, 'conversations.html', context)



@login_required
@require_POST
def send_message(request, conversation_id=None):
    data = json.loads(request.body)
    content = data.get('content')
    receiver_username = data.get('receiver_username')

    if not content:
        return JsonResponse({'status': 'No content'}, status=400)

    if conversation_id:
        conversation = get_object_or_404(Conversation, id=conversation_id)
    else:
        receiver = get_object_or_404(User, username=receiver_username)
        conversation, created = Conversation.objects.get_or_create(
            type='private',
            user1=request.user,
            user2=receiver,
            defaults={'name': receiver.username}
        )

    Message.objects.create(sender=request.user, content=content, conversation=conversation)
    
    return JsonResponse({'status': 'Message sent', 'conversation_id': conversation.id})

@login_required
@require_POST
def send_invitation(request):
    data = json.loads(request.body)
    experiment_id = data['experiment_id']
    username = data['username']
    role = data['role']

    user = get_object_or_404(User, username=username)
    experiment = get_object_or_404(Experiment, id=experiment_id)

    # Find or create a single conversation for the user pair
    conversation, created = Conversation.objects.get_or_create(
        type='private',
        user1=request.user,
        user2=user,
        defaults={'name': user.username}
    )

    # Create the invitation
    invitation = Invitation.objects.create(
        sender=request.user,
        receiver=user,
        experiment=experiment,
        role=role,
        status='pending'
    )

    # Send the invitation as a message in the existing conversation
    message_content = f"You have been invited to join the experiment '{experiment.name}' as a {role}. Do you accept?"
    Message.objects.create(
        sender=request.user,
        content=message_content,
        conversation=conversation,
        invitation_id=invitation.id  # Pass the invitation_id
    )

    return JsonResponse({'status': 'Invitation sent successfully', 'conversation_id': conversation.id})

@login_required
def new_message(request):
    # Retrieve friends where the current user is either user1 or user2 and the status is 'accepted'
    friends = Friend.objects.filter(
        (Q(user1=request.user) | Q(user2=request.user)) & Q(status='accepted')
    ).values_list('user1__username', 'user2__username')

    # Extract the usernames, but exclude the current user's own username
    friends = set(
        friend for pair in friends for friend in pair if friend != request.user.username
    )

    return render(request, 'new-message.html', {'friends': friends})
@login_required
@require_POST
def send_new_message(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        receiver_usernames = data.get('receiver_usernames', [])
        content = data.get('content', '')

        if receiver_usernames and content:
            # Assume only one recipient for simplicity, adjust if supporting multiple recipients
            recipient = User.objects.get(username=receiver_usernames[0])

            # Create or get the conversation
            conversation, created = Conversation.objects.get_or_create(
                type='private',
                user1=request.user,
                user2=recipient
            )

            # Create the message
            message = Message.objects.create(
                sender=request.user,
                content=content,
                conversation=conversation
            )

            return JsonResponse({
                'status': 'Message sent',
                'conversation_id': conversation.id  # Ensure this is returned
            })

        return JsonResponse({'status': 'Error', 'message': 'Invalid data'})


@login_required
def events(request):
    if request.method == 'GET':
        events = CalendarEvent.objects.filter(user=request.user)
        events_list = [{
            'id': e.id,
            'title': e.title,
            'start': e.start_date.isoformat(),
            'end': e.end_date.isoformat()
        } for e in events]
        return JsonResponse(events_list, safe=False)

    if request.method == 'POST':
        data = json.loads(request.body)
        CalendarEvent.objects.create(
            user=request.user,
            title=data['title'],
            start_date=data['start'],
            end_date=data['end'],
            experiment=None  # Set if it is associated with an experiment
        )
        return JsonResponse({'success': True})
@login_required
@require_POST
def add_event(request):
    data = json.loads(request.body)
    title = data.get('title')
    start_date = data.get('start')
    end_date = data.get('end')

    if title and start_date and end_date:
        CalendarEvent.objects.create(
            title=title,
            start_date=start_date,
            end_date=end_date,
            user=request.user
        )
        return JsonResponse({'status': 'success', 'message': 'Event added successfully'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid data'})


@login_required
@require_POST
def delete_calendar_event(request, event_id):
    event = get_object_or_404(CalendarEvent, id=event_id, user=request.user)
    event.delete()
    return JsonResponse({'status': 'Event deleted successfully'})


@login_required
def user_home(request):
    user = request.user
    experiments = Experiment.objects.filter(owner=user, ended=False)
    experiment_data = []

    for experiment in experiments:
        last_weigh_in = WeightMeasurement.objects.filter(experiment=experiment).order_by('-timestamp').first()
        last_weigh_in_date = last_weigh_in.timestamp if last_weigh_in else experiment.created_date
        next_weigh_in_date = last_weigh_in_date + timezone.timedelta(days=experiment.weigh_in_interval)
        days_until_next_weigh_in = (next_weigh_in_date - timezone.now()).days
        healthy_count = RFIDAssignment.objects.filter(experiment=experiment, removed=False).count()
        removed_count = RFIDAssignment.objects.filter(experiment=experiment, removed=True).count()

        experiment_data.append({
            'id': experiment.id,
            'name': experiment.name,
            'number_of_animals': experiment.number_of_animals,
            'number_of_groups': experiment.number_of_groups,
            'created_date': last_weigh_in_date,
            'removed_animals': removed_count,
            'available_animals': healthy_count,
            'days_until_next_weigh_in': days_until_next_weigh_in
        })

    return render(request, 'userhome.html', {'user': user, 'experiments': experiment_data})

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
def animal_details(request, experiment_id, animal_index):
    # Fetch the correct animal
    experiment = get_object_or_404(Experiment, id=experiment_id)
    animal = get_object_or_404(Animal, experiment=experiment, animal_index=animal_index)

    print(f"Animal details: RFID: {animal.rfid_tag}, Age: {animal.age}, Sex: {animal.sex}, Species: {animal.species}")

    # Fetch related observations, weights, samples, and doses if needed
    observations = animal.observations.all()
    weights = animal.weightmeasurement_set.all()
    samples = animal.sample_set.all()
    doses = animal.dose_set.all()

    context = {
        'experiment': experiment,
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
                unique_rfid = f'{experiment.id}_{animal.animal_index}'  # Example: RFID_1_1

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



def profile_view(request):
    if request.method == 'POST':
        profile_form = UpdateProfileForm(request.POST, request.FILES, instance=request.user)
        if profile_form.is_valid():
            profile_form.save()
            return redirect('profile')  # Redirect to the profile page after saving
    else:
        profile_form = UpdateProfileForm(instance=request.user)

    return render(request, 'profile.html', {
        'profile_form': profile_form,
    })

@login_required
@require_POST
def create_group(request):
    data = request.json()
    group_name = data['group_name']
    user_ids = data['user_ids']

    conversation = Conversation.objects.create(type='group', name=group_name)

    for user_id in user_ids:
        GroupMember.objects.create(conversation=conversation, user_id=user_id)

    return JsonResponse({'status': 'Success', 'message': 'Group created successfully', 'conversation_id': conversation.id})

@login_required
def experiment_home(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    assignments = RFIDAssignment.objects.filter(experiment=experiment)

    healthy_count = 0
    at_risk_count = 0
    removal_count = 0

    for assignment in assignments:
        # Accessing the related Animal's animal_index
        animal = Animal.objects.filter(experiment=experiment, id=assignment.animal_id).first()

        if animal:
            latest_measurement = WeightMeasurement.objects.filter(animal=animal).order_by('-timestamp').first()

            if latest_measurement and assignment.initial_weight:
                # Calculate weight change percentage based on the initial weight
                weight_change_percentage = ((assignment.initial_weight - latest_measurement.weight) / assignment.initial_weight) * 100

                # Categorize based on the weight change percentage
                if weight_change_percentage < 15:
                    healthy_count += 1
                elif 15 <= weight_change_percentage < 20:
                    at_risk_count += 1
                else:
                    removal_count += 1

    context = {
        'experiment': experiment,
        'healthy_count': healthy_count,
        'at_risk_count': at_risk_count,
        'removal_count': removal_count,
        'collaborators': experiment.collaborators.all(),
    }

    return render(request, 'experiment-home.html', context)

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

@login_required
def map_rfid(request, experiment_id):
    # Fetch the experiment
    experiment = get_object_or_404(Experiment, id=experiment_id)

    # Fetch all assigned RFID numbers for this experiment
    assigned_rfids = RFIDAssignment.objects.filter(experiment=experiment).values('animal__animal_index', 'rfid', 'weight', 'tumor_size', 'cage_number')

    context = {
        'experiment': experiment,
        'assigned_rfids': list(assigned_rfids)  # Convert to list for easier handling in the template
    }

    return render(request, 'mapRFID.html', context)

@login_required
def cage_configuration(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)

    if request.method == 'POST':
        # Handle the POST request to save the cage configuration
        data = request.POST['configuration']  # Adjust based on how you send data
        # Process the data and update the cage configuration here
        return JsonResponse({"status": "Cage configuration updated"})
    
    else:  # Handle GET request
        # Fetch the cages and animals for display
        cages = {}
        assignments = RFIDAssignment.objects.filter(experiment=experiment).order_by('animal_index')
        for assignment in assignments:
            if assignment.cage_number not in cages:
                cages[assignment.cage_number] = []
            cages[assignment.cage_number].append(assignment)
        
        return render(request, 'cage-configuration.html', {
            'experiment': experiment,
            'cages': cages
        })




@csrf_exempt
def update_experiment(request, experiment_id):
    if request.method == 'PATCH':
        try:
            data = json.loads(request.body)
            rfid_assignments = data.get('rfid_assignments', [])
            experiment = get_object_or_404(Experiment, id=experiment_id)

            for assignment in rfid_assignments:
                required_keys = {'animal_index', 'rfid', 'weight', 'tumor_size', 'cage_number'}
                if not all(key in assignment for key in required_keys):
                    return JsonResponse({'status': 'error', 'message': 'Missing required keys.'}, status=400)

                # Retrieve or create the corresponding animal without setting RFID
                animal, _ = Animal.objects.get_or_create(
                    experiment=experiment,
                    animal_index=assignment['animal_index'],
                )

                # Update or create the RFID assignment
                RFIDAssignment.objects.update_or_create(
                    animal=animal,
                    defaults={
                        'rfid': assignment['rfid'],
                        'weight': assignment.get('weight'),
                        'tumor_size': assignment.get('tumor_size'),
                        'cage_number': assignment.get('cage_number'),
                    }
                )

            return JsonResponse({'status': 'success', 'message': 'RFID numbers updated successfully.'})

        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

@login_required
def profile(request):
    if request.method == 'POST':
        if 'profile_picture' in request.FILES:
            profile_form = ProfilePictureForm(request.POST, request.FILES, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                django_messages.success(request, 'Profile picture updated successfully')
            else:
                django_messages.error(request, 'Failed to update profile picture.')

        elif 'first_name' in request.POST:
            update_form = UpdateProfileForm(request.POST, instance=request.user)
            if update_form.is_valid():
                update_form.save()
                django_messages.success(request, 'Profile updated successfully')
            else:
                django_messages.error(request, 'Failed to update profile.')

        return redirect('profile')

    else:
        update_form = UpdateProfileForm(instance=request.user)
        profile_form = ProfilePictureForm(instance=request.user)

    return render(request, 'profile.html', {
        'form': update_form,
        'profile_form': profile_form,
    })


@login_required
def update_profile_picture(request):
    if request.method == 'POST':
        profile_form = ProfilePictureForm(request.POST, request.FILES, instance=request.user)
        if profile_form.is_valid():
            profile_form.save()
            messages.success(request, 'Profile picture updated successfully')
            return redirect('profile')
        else:
            messages.error(request, 'Failed to update profile picture.')
    else:
        profile_form = ProfilePictureForm(instance=request.user)
    
    return render(request, 'profile.html', {
        'profile_form': profile_form,
    })


@login_required
def cage_configuration(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)

    if request.method == 'POST':
        # Handle the POST request to save the cage configuration
        data = request.POST['configuration']  # Adjust based on how you send data
        # Process the data and update the cage configuration here
        # Return a response, for example:
        return JsonResponse({"status": "Cage configuration updated"})
    
    else:  # Handle GET request
        # Fetch the cages and animals for display
        cages = {}
        assignments = RFIDAssignment.objects.filter(experiment=experiment)
        for assignment in assignments:
            if assignment.cage_number not in cages:
                cages[assignment.cage_number] = []
            cages[assignment.cage_number].append(assignment)
        
        return render(request, 'cage-configuration.html', {
            'experiment': experiment,
            'cages': cages
        })

@login_required
@require_POST
def update_cage_configuration(request, experiment_id):
    data = request.json()['configuration']
    experiment = get_object_or_404(Experiment, id=experiment_id)

    for cage_number, animals in data.items():
        for animal in animals:
            RFIDAssignment.objects.filter(experiment=experiment, rfid=animal['rfid'], animal_index=animal['index']).update(cage_number=cage_number)

    return JsonResponse({"status": "Cage configuration updated"})
@login_required
@require_POST
def update_cages(request, experiment_id):
    data = request.json['configuration']
    experiment = get_object_or_404(Experiment, id=experiment_id)

    for cage_number, animals in data.items():
        for animal in animals:
            RFIDAssignment.objects.filter(experiment=experiment, rfid=animal['rfid'], animal_index=animal['index']).update(cage_number=cage_number)

    return JsonResponse({"status": "Cage configuration updated"})
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
    experiment = Experiment.objects.filter(
        Q(id=experiment_id) & (Q(owner=request.user) | Q(collaborators__user=request.user))
    ).first()

    if not experiment:
        return HttpResponse("Experiment not found or you do not have permission to access it.", status=404)

    # Fetch RFID assignments related to this experiment
    assigned_rfids = RFIDAssignment.objects.filter(experiment=experiment, removed=False)

    animals_by_cage = {}
    all_animals_weighed = True  # Assume all animals are weighed initially

    for assignment in assigned_rfids:
        animal = assignment.animal  # Access the related Animal object
        cage_number = assignment.cage_number
        
        if cage_number not in animals_by_cage:
            animals_by_cage[cage_number] = []
        
        animals_by_cage[cage_number].append({
            'animal_index': animal.animal_index,  # Accessing animal_index through the related Animal
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
def dashboard(request):
    user = request.user
    conversations = Conversation.objects.filter(
        Q(user1=user) | Q(user2=user) | Q(groupmember__user=user)
    ).distinct()

    # Count the number of conversations with unread messages
    total_unread_conversations = conversations.filter(
        Q(messages__is_read=False)
    ).exclude(messages__sender=user).values('id').distinct().count()

    upcoming_events_count = CalendarEvent.objects.filter(user=user, start_date__gte=timezone.now()).count()
    active_experiments_count = Experiment.objects.filter(owner=user, ended=False).count()

    context = {
        'upcoming_events_count': upcoming_events_count,
        'total_unread_conversations': total_unread_conversations,
        'active_experiments_count': active_experiments_count,
    }

    return render(request, 'dashboard.html', context)


@login_required
@require_POST
def delete_experiment(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, owner=request.user)
    experiment.ended = True
    experiment.save()

    CalendarEvent.objects.filter(experiment=experiment).delete()

    return JsonResponse({'status': 'Experiment deleted successfully'})

@login_required
def view_experiment(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    return render(request, 'view_experiment.html', {'experiment': experiment})


def get_rfid_assignments(request, experiment_id):
    # Fetch the experiment by ID
    experiment = get_object_or_404(Experiment, id=experiment_id)

    # Retrieve all RFID assignments related to this experiment
    assignments = RFIDAssignment.objects.filter(experiment=experiment).values(
        'animal__animal_index', 'rfid', 'weight', 'tumor_size', 'cage_number'
    )

    # Return assignments as a JSON response
    return JsonResponse(list(assignments), safe=False)
@login_required
def all_experiments(request):
    active_experiments = Experiment.objects.filter(
        Q(owner=request.user) | Q(collaborators__user=request.user), ended=False
    )
    past_experiments = Experiment.objects.filter(
        Q(owner=request.user) | Q(collaborators__user=request.user), ended=True
    )

    return render(request, 'all-experiments.html', {
        'active_experiments': active_experiments,
        'past_experiments': past_experiments,
    })


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
@login_required
@require_POST
def delete_animal(request, experiment_id, animal_index):
    RFIDAssignment.objects.filter(experiment_id=experiment_id, animal_index=animal_index).update(removed=True)
    return JsonResponse({'status': 'Animal deleted successfully'})

def generate_csv_for_experiment(experiment_id, user):
    # Get the experiment and verify ownership/collaboration
    experiment = get_object_or_404(Experiment, id=experiment_id)
    
    # Verify that the user is either the owner or a collaborator
    if experiment.owner != user and not experiment.collaborators.filter(user=user).exists():
        return HttpResponseForbidden("You do not have permission to download this CSV.")

    # Create the HttpResponse object with the appropriate CSV header.
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="experiment_{experiment_id}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Animal Index', 'RFID', 'Weight', 'Tumor Size', 'Weigh-In Timestamp'])

    # Get all relevant data for the experiment
    measurements = WeightMeasurement.objects.filter(experiment=experiment).order_by('animal_index', 'timestamp')
    rfid_assignments = RFIDAssignment.objects.filter(experiment=experiment)

    # Create a mapping of animal_index to RFID
    rfid_map = {ra.animal_index: ra.rfid for ra in rfid_assignments}

    for measurement in measurements:
        writer.writerow([
            measurement.animal_index,
            rfid_map.get(measurement.animal_index, 'Unknown RFID'),
            measurement.weight,
            measurement.tumor_size,
            measurement.timestamp
        ])

    return response
@login_required
def download_csv(request, experiment_id):
    return generate_csv_for_experiment(experiment_id, request.user)


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
def experiment_settings(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id, owner=request.user)

    if request.method == 'POST':
        warning_weight_percentage = request.POST.get('warning_weight_percentage')
        removal_weight_percentage = request.POST.get('removal_weight_percentage')

        experiment.warning_weight_percentage = float(warning_weight_percentage)
        experiment.removal_weight_percentage = float(removal_weight_percentage)
        experiment.save()

        django_messages.success(request, "Experiment settings updated successfully.")
        return redirect('experiment_home', experiment_id=experiment.id)

    return render(request, 'settings.html', {'experiment': experiment})

@login_required
@require_POST
def end_experiment(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    experiment.ended = True
    experiment.save()

    # Delete associated calendar events
    CalendarEvent.objects.filter(experiment=experiment).delete()

    # Automatically download CSV
    return generate_csv_for_experiment(experiment_id, request.user)
@login_required
@require_POST
def respond_invitation(request):
    data = json.loads(request.body)
    invitation_id = data.get('invitation_id')
    action = data.get('action')

    if not invitation_id:
        return JsonResponse({'status': 'error', 'message': 'Invitation ID is missing'}, status=400)

    try:
        invitation = Invitation.objects.get(id=invitation_id)
    except Invitation.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Invalid Invitation ID'}, status=404)

    if invitation.status != 'pending':
        return JsonResponse({'status': 'error', 'message': f'Invitation already {invitation.status}'}, status=400)

    if action == 'accept':
        # Add the user as a collaborator
        Collaborator.objects.create(
            experiment=invitation.experiment,
            user=invitation.receiver,
            role=invitation.role
        )
        invitation.status = 'accepted'
        message = f"You have accepted the invitation to {invitation.experiment.name}. You can find it in your Experiments page."
    elif action == 'decline':
        invitation.status = 'declined'
        message = f"You have declined the invitation to {invitation.experiment.name}."

    invitation.save()

    # If you want to link to a conversation, ensure the conversation logic is handled correctly here.
    conversation = Conversation.objects.get_or_create(
        type='private',
        user1=invitation.sender,
        user2=invitation.receiver,
        defaults={'name': f"Conversation about {invitation.experiment.name}"}
    )[0]

    Message.objects.create(
        sender=request.user,
        content=message,
        conversation=conversation
    )

    return JsonResponse({'status': 'success', 'message': message})
@login_required
@require_POST
def add_collaborator(request):
    data = json.loads(request.body)
    experiment_id = data['experiment_id']
    username = data['username']
    role = data['role']

    user = get_object_or_404(User, username=username)
    experiment = get_object_or_404(Experiment, id=experiment_id)

    # Create or get the conversation between the current user and the invited user
    conversation, created = Conversation.objects.get_or_create(
        type='private',
        user1=request.user,
        user2=user,
        defaults={'name': f"Invitation to {experiment.name}"}
    )

    # Create the invitation
    invitation = Invitation.objects.create(
        sender=request.user,
        receiver=user,
        experiment=experiment,
        role=role,
        status='pending'
    )

    # Send the invitation as a message
    message_content = f"You have been invited to join the experiment '{invitation.experiment.name}' as a {invitation.role}. Do you accept?"
    Message.objects.create(
        sender=request.user,
        content=message_content,
        conversation=conversation,
        invitation_id=invitation.id
    )

    # Automatically add the collaborator's calendar events if the experiment has a weigh-in schedule
    if experiment.weigh_in_interval and experiment.duration:
        current_date = timezone.now().date()
        while current_date < timezone.now().date() + timezone.timedelta(days=experiment.duration):
            CalendarEvent.objects.create(
                user=user,
                title=f"Weigh-In for {experiment.name} (Collaborator)",
                start_date=current_date,
                end_date=current_date,
                experiment=experiment,
                color='red'  # Assign the color red for collaborator events
            )
            current_date += timezone.timedelta(days=experiment.weigh_in_interval)

    return JsonResponse({'status': 'Invitation sent successfully'})

@login_required
def pending_invitations(request):
    invitations = Invitation.objects.filter(receiver=request.user, status='pending')
    return render(request, 'pending_invitations.html', {'invitations': invitations})


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
def remove_animal(request, experiment_id, animal_index):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    RFIDAssignment.objects.filter(experiment=experiment, animal_index=animal_index).update(removed=True)
    return JsonResponse({'status': 'success', 'message': 'Animal removed successfully'})

@login_required
@require_POST
def remove_collaborator(request):
    data = request.json()
    experiment_id = data['experiment_id']
    user_id = data['user_id']

    Collaborator.objects.filter(experiment_id=experiment_id, user_id=user_id).delete()
    return JsonResponse({'status': 'Collaborator removed'})

@login_required
@require_POST
def update_collaborator_role(request):
    data = request.json()
    experiment_id = data['experiment_id']
    user_id = data['user_id']
    role = data['role']

    Collaborator.objects.filter(experiment_id=experiment_id, user_id=user_id).update(role=role)
    return JsonResponse({'status': 'Collaborator role updated'})

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
@require_POST
def add_friend(request):
    data = request.json()
    friend_username = data['friend_username']

    friend = get_object_or_404(User, username=friend_username)

    Friend.objects.create(user1=request.user, friend_id=friend.id, status='pending')
    
    return JsonResponse({'status': 'Friend request sent'})

@login_required
@require_POST
def remove_friend(request):
    data = request.json()
    friend_username = data['friend_username']

    friend = get_object_or_404(User, username=friend_username)

    Friend.objects.filter(Q(user1=request.user, friend_id=friend.id) | Q(user1=friend, friend_id=request.user)).delete()
    
    return JsonResponse({'status': 'Friend removed successfully'})

@login_required
def pending_requests(request):
    pending_requests = Friend.objects.filter(friend_id=request.user.id, status='pending').select_related('user')
    return render(request, 'pending_requests.html', {'pending_requests': pending_requests})

@login_required
@require_POST
def respond_friend_request(request):
    data = request.json()
    friend_id = data.get('friend_id')
    action = data.get('action')

    if action == 'accept':
        Friend.objects.filter(user1=friend_id, friend_id=request.user.id).update(status='accepted')
    elif action == 'decline':
        Friend.objects.filter(user1=friend_id, friend_id=request.user.id).delete()

    return JsonResponse({'status': 'success', 'message': f'Friend request {action}ed'})

@login_required
def friend_info(request, friend_id):
    user = get_object_or_404(User, id=friend_id)
    conversation = Conversation.objects.filter(Q(user1=request.user, user2=user) | Q(user1=user, user2=request.user)).first()

    return JsonResponse({'status': 'success', 'user': {
        'id': user.id,
        'username': user.username,
        'organization': user.organization,
        'title': user.title,
        'location': user.location,
        'conversation_id': conversation.id if conversation else None
    }})

@login_required
def messages(request):
    user = request.user

    conversations = Conversation.objects.filter(
        Q(user1=user) | Q(user2=user) | Q(groupmember__user=user)
    ).distinct()

    conversation_list = []

    for convo in conversations:
        if convo.type == 'private':
            other_user = convo.user2 if convo.user1 == user else convo.user1
            # Count distinct senders with unread messages
            unread_count = Message.objects.filter(conversation=convo, is_read=False).exclude(sender=user).values('sender').distinct().count()
            conversation_list.append({
                'id': convo.id,
                'type': convo.type,
                'username': other_user.username,
                'profile_picture': other_user.profile_picture.url if other_user.profile_picture else '{% static "img/default-profile.jpg" %}',
                'unread_count': unread_count
            })
        else:
            # Count distinct senders with unread messages in group conversations
            unread_count = Message.objects.filter(conversation=convo, is_read=False).exclude(sender=user).values('sender').distinct().count()
            conversation_list.append({
                'id': convo.id,
                'type': convo.type,
                'name': convo.name or 'Unnamed Group',
                'profile_picture': '{% static "img/group.png" %}',
                'unread_count': unread_count
            })

    return render(request, 'conversations.html', {'conversations': conversation_list})


@login_required
def conversation(request, conversation_id):
    # Fetch conversation and related messages
    conversation = get_object_or_404(Conversation, id=conversation_id)
    messages = Message.objects.filter(conversation=conversation).order_by('timestamp')
    
    context = {
        'conversation': conversation,
        'messages': messages,
        'selected_conversation_id': conversation_id,  # Ensure this is passed to the context
        'conversation_name': conversation.name,
        'conversation_type': conversation.type,
        'user_id': request.user.id,
    }
    return render(request, 'conversations.html', context)

@login_required
def conversations(request):
    conversations = Conversation.objects.filter(Q(user1=user) | Q(user2=user) | Q(groupmember__user=user)).distinct()
    return render(request, 'conversations.html', {'conversations': conversations})
