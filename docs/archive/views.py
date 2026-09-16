from django.core import serializers
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.db.models import Q, F, Avg, Max, Min
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.models import User
from .models import (Conversation, Message, GroupMember, Experiment, RFIDAssignment, WeightMeasurement, Collaborator, CalendarEvent, Comment, Friend, Cage, Animal)
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, authenticate
import pandas as pd
import random
from django.contrib.auth import logout
from .forms import UpdateProfileForm
import json
from .forms import ExperimentForm
from django.utils.safestring import mark_safe

@login_required
def home(request):
    return render(request, 'home.html')

@login_required
def home_view(request):
    return render(request, 'home.html')

@login_required
def events(request):
    if request.method == 'GET':
        events = CalendarEvent.objects.filter(user=request.user)
        events_list = [{'id': e.id, 'title': e.title, 'start': e.start_date, 'end': e.end_date} for e in events]
        return JsonResponse({'events': events_list})

    if request.method == 'POST':
        data = request.json()
        CalendarEvent.objects.create(
            user=request.user,
            title=data['title'],
            start_date=data['start'],
            end_date=data['end']
        )
        return JsonResponse({'success': True})
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
    return render(request, 'mpyapp/login.html')  # Make sure you have a login.html template

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

    context = {
        'selected_conversation_id': conversation_id,
        'messages': messages,
        'conversation_name': conversation.name if conversation.name else "Conversation",
        'conversation_type': conversation.type,
        'user_id': request.user.id,
    }
    return render(request, 'conversations.html', context)

@login_required
@require_POST
def send_message(request, conversation_id):
    data = request.json()
    content = data.get('content')

    if not content:
        return JsonResponse({'status': 'No content'}, status=400)

    conversation = get_object_or_404(Conversation, id=conversation_id)
    Message.objects.create(sender=request.user, content=content, conversation=conversation)
    
    return JsonResponse({'status': 'Message sent'})

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

    return render(request, 'new_message.html', {'friends': friends})

@login_required
@require_POST
def add_event(request):
    data = request.json()
    CalendarEvent.objects.create(
        user=request.user,
        title=data.get('title'),
        start_date=data.get('start'),
        end_date=data.get('end')
    )
    return JsonResponse({'status': 'success', 'message': 'Event added successfully'})
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
def experiment_summary(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    experiment_data = {
        'name': experiment.name,
        'number_of_animals': experiment.number_of_animals,
        'number_of_groups': experiment.number_of_groups,
        'investigators': experiment.investigators,
        'measurement_items': experiment.measurement_items,
        'rfid_required': 'Yes' if experiment.rfid_required else 'No',
        'max_per_cage': experiment.max_per_cage
    }
    return render(request, 'summary.html', {'experiment_data': experiment_data, 'experiment_id': experiment_id})

def assign_animals_to_cages(experiment, number_of_animals, max_per_cage):
    RFIDAssignment.objects.filter(experiment=experiment).delete()
    rfid_range = list(range(1000, 2001))
    random.shuffle(rfid_range)

    assignments = [
        RFIDAssignment(
            experiment=experiment,
            animal_index=i,
            rfid=rfid_range[i],
            cage_number=(i // max_per_cage) + 1
        ) for i in range(number_of_animals)
    ]
    RFIDAssignment.objects.bulk_create(assignments)

def profile_view(request):
    if request.method == 'POST':
        profile_form = UpdateProfileForm(request.POST, request.FILES, instance=request.user)  # Ensure request.FILES is included
        if profile_form.is_valid():
            profile_form.save()
            return redirect('profile')  # Redirect to the profile page after saving
    else:
        profile_form = UpdateProfileForm(instance=request.user)

    return render(request, 'profile.html', {
        'profile_form': profile_form,
    })

@login_required
def create_experiment(request):
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

        assign_animals_to_cages(experiment, number_of_animals, max_per_cage)

        if weight_schedule == 'yes' and weigh_in_interval and experiment_duration:
            start_date = timezone.now()
            end_date = start_date + timezone.timedelta(days=experiment_duration)
            weigh_in_date = start_date
            while weigh_in_date < end_date:
                CalendarEvent.objects.create(
                    user=request.user,
                    experiment=experiment,
                    title=f"Weigh-In: {name}",
                    start_date=weigh_in_date,
                    end_date=weigh_in_date
                )
                weigh_in_date += timezone.timedelta(days=weigh_in_interval)

        return redirect('experiment_summary', experiment_id=experiment.id)

    return render(request, 'new-experiment.html')

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
    experiment = get_object_or_404(Experiment, Q(id=experiment_id) & (Q(owner=request.user) | Q(collaborators__user=request.user)))
    collaborators = experiment.collaborators.all()
    healthy_count = RFIDAssignment.objects.filter(experiment=experiment, removed=False).count()
    removed_count = RFIDAssignment.objects.filter(experiment=experiment, removed=True).count()

    experiment_data = {
        'id': experiment.id,
        'name': experiment.name,
        'number_of_animals': experiment.number_of_animals,
        'number_of_groups': experiment.number_of_groups,
        'investigators': experiment.investigators,
        'measurement_items': experiment.measurement_items,
        'rfid_required': experiment.rfid_required,
        'max_per_cage': experiment.max_per_cage,
        'ended': experiment.ended
    }

    return render(request, 'experiment-home.html', {
        'experiment': experiment_data,
        'collaborators': collaborators,
        'health_counts': {'healthy': healthy_count, 'removed': removed_count}
    })

@login_required
def map_rfid(request, experiment_id):
    experiment = get_object_or_404(Experiment, Q(id=experiment_id) & (Q(owner=request.user) | Q(collaborators__user=request.user)))

    if request.method == 'POST':
        if not RFIDAssignment.objects.filter(experiment=experiment).exists():
            assign_animals_to_cages(experiment, experiment.number_of_animals, experiment.max_per_cage)

    assigned_rfids = RFIDAssignment.objects.filter(experiment=experiment)
    
    # Convert QuerySet to list of dictionaries and ensure JSON format with double quotes
    assigned_rfids_list = list(assigned_rfids.values('animal_index', 'rfid', 'weight', 'tumor_size'))
    assigned_rfids_json = json.dumps(assigned_rfids_list)  # Properly formatted JSON string

    return render(request, 'mapRFID.html', {
        'experiment': experiment,
        'assigned_rfids': assigned_rfids_json  # Pass the JSON string to the template
    })


@login_required
def update_experiment(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    
    if request.method == 'PATCH':
        data = json.loads(request.body)
        rfid_assignments = data.get('rfid_assignments', [])
        
        for rfid_data in rfid_assignments:
            animal_index = rfid_data['animal_index']
            rfid = rfid_data['rfid']
            
            # Update or create the RFID assignment
            RFIDAssignment.objects.update_or_create(
                experiment=experiment,
                animal_index=animal_index,
                defaults={'rfid': rfid}
            )
        
        return JsonResponse({'status': 'RFID assignments updated successfully'})
    
    # If the method is GET or something else, use the form for updating experiment details
    form = ExperimentForm(instance=experiment)
    return render(request, 'update_experiment.html', {'form': form, 'experiment': experiment})

@login_required
def update_profile(request):
    if request.method == 'POST':
        form = UpdateProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            return redirect('profile')  # Redirect to profile page after updating
    else:
        form = UpdateProfileForm(instance=request.user)
    
    return render(request, 'update_profile.html', {'form': form})

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
def data_collection(request, experiment_id):
    experiment = get_object_or_404(Experiment, Q(id=experiment_id) & (Q(owner=request.user) | Q(collaborators__user=request.user)))

    assigned_rfids = RFIDAssignment.objects.filter(experiment=experiment, removed=False)

    return render(request, 'data-collection.html', {'experiment': experiment, 'assigned_rfids': assigned_rfids})

@login_required
@require_POST
def save_data_collection(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)

    try:
        # Parse the JSON body of the request
        data = json.loads(request.body)['data']

        for animal_index, values in data.items():
            weight = float(values.get('weights', 0))
            tumor_size = float(values.get('tumor_sizes', 0))
            removed = bool(values.get('removed', False))

            # Update or create WeightMeasurement and RFIDAssignment records
            WeightMeasurement.objects.create(
                experiment=experiment,
                animal_index=int(animal_index),
                weight=weight,
                tumor_size=tumor_size
            )

            RFIDAssignment.objects.filter(experiment=experiment, animal_index=int(animal_index)).update(
                weight=weight,
                tumor_size=tumor_size,
                removed=removed
            )

        return JsonResponse({'status': 'Data collection updated successfully!'})

    except Exception as e:
        # Log the error (you can add logging here if desired)
        return JsonResponse({'status': 'Error updating data collection', 'error': str(e)}, status=500)
    
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

    # Serialize the chart_data dictionary to a JSON string
    chart_data_json = mark_safe(json.dumps(chart_data))

    return render(request, 'analytics.html', {
        'experiment': experiment,
        'chart_data': chart_data_json
    })

@login_required
def dashboard(request):
    user = request.user
    experiments = Experiment.objects.filter(Q(owner=user) | Q(collaborators__user=user), ended=False)
    
    # Assuming `initial_weight` is stored somewhere or calculated
    # For example, if initial_weight is just a fixed value or needs to be calculated
    # You could replace `F('initial_weight')` with the correct logic or field reference
    
    # If `initial_weight` is fixed (e.g., assume a placeholder)
    # initial_weight_value = 100.0  # Replace this with your logic or model reference
    
    # Example using a fixed initial weight or calculation
    animals_in_need_of_assistance = RFIDAssignment.objects.filter(
        weight__lt=F('weight') * 0.85,  # Replace with your correct calculation or field
        removed=False
    )
    animals_in_need_of_removal = RFIDAssignment.objects.filter(
        weight__lt=F('weight') * 0.80,  # Replace with your correct calculation or field
        removed=False
    )
    
    events = CalendarEvent.objects.filter(user=user)

    return render(request, 'dashboard.html', {
        'experiments': experiments,
        'animals_in_need_of_assistance': animals_in_need_of_assistance,
        'animals_in_need_of_removal': animals_in_need_of_removal,
        'events': events
    })


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

@login_required
def all_experiments(request):
    experiments = Experiment.objects.filter(Q(owner=request.user) | Q(collaborators__user=request.user), ended=False)
    return render(request, 'all-experiments.html', {'experiments': experiments})


def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = UserCreationForm()
    
    return render(request, 'register.html', {'form': form})

@login_required
def animal_details(request, experiment_id, animal_index):
    animal_data = get_object_or_404(RFIDAssignment, experiment_id=experiment_id, animal_index=animal_index)

    weights = WeightMeasurement.objects.filter(experiment_id=experiment_id, animal_index=animal_index).order_by('timestamp')

    average_weight = weights.aggregate(Avg('weight'))['weight__avg'] if weights else None
    max_weight = weights.aggregate(Max('weight'))['weight__max'] if weights else None
    min_weight = weights.aggregate(Min('weight'))['weight__min'] if weights else None

    comments = Comment.objects.filter(experiment_id=experiment_id, animal_index=animal_index).select_related('user')

    return render(request, 'animal_details.html', {
        'animal': animal_data,
        'weights': weights,
        'comments': comments,
        'average_weight': average_weight,
        'max_weight': max_weight,
        'min_weight': min_weight
    })

@login_required
@require_POST
def delete_animal(request, experiment_id, animal_index):
    RFIDAssignment.objects.filter(experiment_id=experiment_id, animal_index=animal_index).update(removed=True)
    return JsonResponse({'status': 'Animal deleted successfully'})

@login_required
@require_POST
def add_comment(request, experiment_id, animal_index):
    data = request.json()
    comment_text = data.get('comment')

    Comment.objects.create(
        experiment_id=experiment_id,
        animal_index=animal_index,
        user=request.user,
        comment=comment_text
    )

    return JsonResponse({'status': 'Comment added'})

@login_required
def download_csv(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)

    data = RFIDAssignment.objects.filter(experiment=experiment).select_related('experiment', 'user')
    df = pd.DataFrame(list(data.values('animal_index', 'rfid', 'weight', 'timestamp', 'tumor_size', 'removed', 'user__username')))
    
    csv_file = f'experiment_{experiment_id}_data.csv'
    df.to_csv(f'static/{csv_file}', index=False)

    return HttpResponse(f'static/{csv_file}', content_type='text/csv')

@login_required
@require_POST
def end_experiment(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    experiment.ended = True
    experiment.save()

    CalendarEvent.objects.filter(experiment=experiment).delete()

    return JsonResponse({"status": "Experiment ended"})

@login_required
@require_POST
def add_collaborator(request):
    data = request.json()
    experiment_id = data['experiment_id']
    username = data['username']
    role = data['role']

    user = get_object_or_404(User, username=username)
    experiment = get_object_or_404(Experiment, id=experiment_id)

    Collaborator.objects.create(experiment=experiment, user=user, role=role)
    
    return JsonResponse({'status': 'Collaborator added'})

@login_required
@require_POST
def respond_invitation(request):
    data = request.json()
    invitation_id = data['invitation_id']
    response = data['response']

    invitation = get_object_or_404(Invitation, id=invitation_id)

    if response == 'accept':
        Collaborator.objects.create(experiment=invitation.experiment, user=invitation.receiver, role=invitation.role)
        invitation.status = 'accepted'
        invitation.save()
        message = f"{request.user.username} has joined the experiment as a {invitation.role}."
    else:
        invitation.status = 'declined'
        invitation.save()
        message = f"{request.user.username} has declined the invitation to join the experiment."

    return JsonResponse({'status': f'Invitation {invitation.status}'})

@login_required
@require_POST
def remove_animal(request, experiment_id, animal_index):
    RFIDAssignment.objects.filter(experiment_id=experiment_id, animal_index=animal_index).update(removed=True)
    return JsonResponse({'status': 'Animal removed successfully'})

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

@login_required
def profile(request):
    if request.method == 'POST':
        form = UpdateProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            return redirect('profile')  # Redirect after saving
    else:
        form = UpdateProfileForm(instance=request.user)
    
    return render(request, 'profile.html', {'form': form})

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
            conversation_list.append({
                'id': convo.id,
                'type': convo.type,
                'username': other_user.username,
                'profile_picture': other_user.profile_picture.url if other_user.profile_picture else 'default.png'
            })
        else:
            conversation_list.append({
                'id': convo.id,
                'type': convo.type,
                'name': convo.name or 'Unnamed Group',
                'profile_picture': 'group.png'
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
@login_required
@require_POST
def send_new_message(request):
    data = request.json()
    sender = request.user
    receiver_usernames = data['receiver_usernames']
    content = data['content']

    if not receiver_usernames or not content:
        return JsonResponse({'status': 'Invalid data'}, status=400)

    friends = Friend.objects.filter(Q(user1=sender) | Q(user2=sender), status='accepted').values_list('friend__username', flat=True)
    invalid_users = [username for username in receiver_usernames if username not in friends]

    if invalid_users:
        return JsonResponse({'status': 'Error', 'message': f'Invalid friends: {", ".join(invalid_users)}'}, status=400)

    for receiver_username in receiver_usernames:
        receiver = get_object_or_404(User, username=receiver_username)
        conversation, created = Conversation.objects.get_or_create(
            type='private',
            user1=sender if sender.id < receiver.id else receiver,
            user2=receiver if sender.id < receiver.id else sender
        )
        Message.objects.create(sender=sender, content=content, conversation=conversation)

    return JsonResponse({'status': 'Message sent', 'conversation_id': conversation.id})