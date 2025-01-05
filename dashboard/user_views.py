from django.contrib import messages
from django.contrib import messages as django_messages
from django.contrib.auth.forms import AuthenticationForm
from django.core import serializers
from django.utils.timezone import now
import hashlib
from django.urls import reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden, HttpResponseRedirect, FileResponse, Http404
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q, F, Avg, Max, Min, Count
from django.utils import timezone
from .models import (Conversation, InboxNotification, PDFTemplate, UserFilledForm, UserAction,PDFFieldMapping, UserSignature, Organization, SignedForm, AdminForm, AdminCreatedForm, SignedAdminForm, Message, User, GroupMember, Experiment, RFIDAssignment, WeightMeasurement, Collaborator, CalendarEvent, Comment, Friend, Cage, Animal, Sample, Dose, Observation, Comment)
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, authenticate
import pandas as pd
from docx import Document
from PIL import Image as PILImage, ImageDraw, ImageFont
from django.core.files.storage import FileSystemStorage  # For file handling and storage if needed
from django.core.files.uploadedfile import InMemoryUploadedFile
from dashboard.data_collection_views import generate_unique_signature
from django.views.decorators.csrf import csrf_exempt
import random
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from django.core.files.base import ContentFile
from django.contrib.auth import logout
from django.db import IntegrityError
import logging
from .forms import CustomUserCreationForm, UpdateProfileForm, ExperimentForm, BannerUploadForm
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
from django.core.mail import send_mail
import os
import datetime
from io import BytesIO
from datetime import date



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
    try:
        # Your existing logic here
        return render(request, 'home.html')
    except Exception as e:
        logger.error(f"Error in home view: {e}")
        return HttpResponseServerError("Something went wrong")
    
@login_required
def profile(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)

    # Get all pending friend requests for the logged-in user
    pending_requests = Friend.objects.filter(user2=request.user, status='pending')

    # Get all accepted friends for the logged-in user
    friends = Friend.objects.filter(
        (Q(user1=request.user) | Q(user2=request.user)),
        status='accepted'
    )

    # Extract the friend from each Friend relationship
    friends_list = []
    for friend_relationship in friends:
        if friend_relationship.user1 == request.user:
            friends_list.append(friend_relationship.user2)  # The other user is the friend
        else:
            friends_list.append(friend_relationship.user1)  # The other user is the friend

    return render(request, 'profile.html', {
        'organization': organization,
        'org_id': org_id,  # Make sure org_id is passed to the template
        'pending_requests': pending_requests,  # Pending friend requests
        'friends': friends_list  # List of friends
    })

@login_required
def profile_view(request):
    org_id = request.user.organization.id if hasattr(request.user, 'organization') else None
    if request.method == 'POST':
        profile_form = UpdateProfileForm(request.POST, request.FILES, instance=request.user)
        if profile_form.is_valid():
            profile_form.save()
            return redirect('profile', org_id=org_id)  # Include org_id
    else:
        profile_form = UpdateProfileForm(instance=request.user)

    return render(request, 'profile.html', {
        'profile_form': profile_form,
    })

@login_required
def update_profile_picture(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    if request.method == 'POST':
        profile_form = ProfilePictureForm(request.POST, request.FILES, instance=request.user)
        if profile_form.is_valid():
            profile_form.save()
            messages.success(request, 'Profile picture updated successfully')
            return redirect('profile', org_id=org_id)  # Pass org_id here as well
        else:
            messages.error(request, 'Failed to update profile picture.')
    else:
        profile_form = ProfilePictureForm(instance=request.user)
    return render(request, 'profile.html', {'profile_form': profile_form})


def resize_image(image, width, height):
    """Resize an image to the specified width and height."""
    try:
        # Open the image using Pillow explicitly
        img = PILImage.open(image)
        img = img.convert("RGB")  # Ensure compatibility
        img = img.resize((width, height), PILImage.LANCZOS)  # Resize image with high-quality filter

        output = BytesIO()
        img.save(output, format="JPEG")  # Save as JPEG to BytesIO
        output.seek(0)
        return ContentFile(output.read())  # Return resized image as ContentFile
    except Exception as e:
        raise ValueError(f"Error resizing image: {e}")

@login_required
def update_profile_banner(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    logger.info(f"Request FILES: {request.FILES}")
    if request.method == 'POST' and request.FILES.get('profile_banner'):
        logger.info("Received POST request for profile banner update.")
        banner_file = request.FILES['profile_banner']
        logger.info(f"Uploaded banner file: {banner_file}")

        try:
            # Resize the uploaded image
            resized_image = resize_image(banner_file, width=1200, height=400)

            # Save the resized image to the user's profile
            profile = request.user
            profile.profile_banner.save(f"banner_{profile.id}.jpg", resized_image, save=True)

            messages.success(request, 'Profile banner updated successfully.')
            logger.info(f"Banner updated successfully for user {profile.username}")
        except Exception as e:
            logger.error(f"Error updating profile banner: {e}")
            messages.error(request, f'An error occurred: {e}')
    else:
        logger.warning("No file uploaded or invalid request.")
        messages.error(request, 'No file uploaded.')

    # Redirect back to the profile page
    return redirect('profile', org_id=org_id)

@login_required
def update_user_info(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    if request.method == 'POST':
        update_form = UpdateProfileForm(request.POST, instance=request.user)
        if update_form.is_valid():
            update_form.save()
            messages.success(request, 'Profile updated successfully')
        else:
            messages.error(request, 'Failed to update profile.')
    return redirect('profile', org_id=org_id)
@login_required
def user_settings(request, org_id):
    """
    Render the User Settings page.
    """
    organization = get_object_or_404(Organization, id=org_id)
    return render(request, 'user_settings.html', {'organization': organization, 'org_id': org_id})


@login_required
@require_POST
def update_user_settings(request, org_id):
    """
    Update user settings, specifically the public/private profile toggle.
    """
    organization = get_object_or_404(Organization, id=org_id)
    is_public = request.POST.get('profile_visibility') == 'on'

    # Update user profile visibility
    user = request.user
    user.is_public = is_public
    user.save()

    messages.success(request, "Settings updated successfully!")
    return redirect('user_settings', org_id=org_id)

def login_view(request):
    form = AuthenticationForm(request, data=request.POST or None)

    if request.method == 'POST' and form.is_valid():
        username = form.cleaned_data['username']
        password = form.cleaned_data['password']
        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user)
            logger.info(f"User {user.username} logged in successfully.")

            # Ensure the `organization` attribute exists and is valid
            organization = getattr(user, 'organization', None)
            if not organization:
                logger.warning(f"User {user.username} has no associated organization.")
            else:
                # Log the login action
                try:
                    logger.debug(f"Attempting to log action for user {user.username}, organization: {organization.name}")
                    action = UserAction.objects.create(
                        user=user,
                        organization=organization,
                        action="User Login",
                        additional_info=f"User {user.username} logged in.",
                        typed_signature="N/A",  # No signature required for login
                        unique_signature=generate_unique_signature(user, "User Login", now()),
                        timestamp=now()
                    )
                    logger.info(f"UserAction created: {action}")
                except Exception as e:
                    logger.error(f"Error logging login action for user {user.username}: {e}")

            return redirect('dashboard')
        else:
            form.add_error(None, 'Invalid username or password.')
            logger.warning(f"Invalid login attempt for username: {username}")

    return render(request, 'login.html', {'form': form})

def admin_login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)

            # Check if the user has an associated organization
            if hasattr(user, 'organization') and user.organization is not None:
                org_id = user.organization.id
                logger.info(f"User {user.username} logged in successfully.")
                logger.info(f"Redirecting to admin dashboard at /{org_id}/admin_dashboard/")
                return HttpResponseRedirect(reverse('admin_dashboard', args=[org_id]))
            else:
                # If the user doesn't have an organization, redirect to a default page or show an error
                logger.warning(f"User {user.username} has no organization. Returning to login page.")
                return render(request, 'admin/admin_login.html', {'error': 'This user does not have an associated organization.'})
        else:
            # If authentication fails, show an error
            logger.warning(f"Invalid login attempt for user {username}.")
            return render(request, 'admin/admin_login.html', {'error': 'Invalid username or password.'})
    else:
        # Render the login page for GET requests
        logger.info(f"Rendering login page. Current path: {request.path}")
        return render(request, 'admin/admin_login.html')
    
@login_required
@require_POST
def add_friend(request, org_id):
    # Extract the data for the friend to be added
    friend_username = request.POST.get('friend_username', None)
    
    # Ensure the organization is correct (if necessary)
    organization = get_object_or_404(Organization, id=org_id)
    
    # Validate if the username exists and belongs to the same organization
    if friend_username:
        try:
            # Fetch the user to add as a friend
            friend_user = User.objects.get(username=friend_username, organization=organization)
            
            # Check if a friend request already exists or if they are already friends
            friend_relationship = Friend.objects.filter(
                Q(user1=request.user, user2=friend_user) | Q(user1=friend_user, user2=request.user)
            ).first()

            if friend_relationship:
                if friend_relationship.status == 'pending':
                    return JsonResponse({'status': 'error', 'message': 'Friend request already sent and is pending.'})
                elif friend_relationship.status == 'accepted':
                    return JsonResponse({'status': 'error', 'message': 'You are already friends with this user.'})
            else:
                # Create a new friend request
                Friend.objects.create(user1=request.user, user2=friend_user, status='pending')

                # Send notification to the user's inbox
                notification_message = f"{request.user.username} has sent you a friend request."
                InboxNotification.objects.create(
                    user=friend_user,
                    message=notification_message,
                    is_read=False  # Mark the notification as unread
                )

                return JsonResponse({'status': 'success', 'message': 'Friend request sent successfully.'})

        except User.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'User does not exist or is not in your organization.'})

    return JsonResponse({'status': 'error', 'message': 'Could not add friend. Invalid request.'})
@login_required
@require_POST
def respond_friend_request(request):
    try:
        logger.info("Friend request response received.")
        data = json.loads(request.body)
        friend_request_id = data.get('friend_id')
        action = data.get('action')

        logger.info(f"Friend ID: {friend_request_id}, Action: {action}")

        friend_request = get_object_or_404(Friend, id=friend_request_id, user2=request.user)

        if action == 'accept':
            friend_request.status = 'accepted'
            friend_request.save()
            logger.info("Friend request accepted.")
            return JsonResponse({'status': 'success', 'message': 'Friend request accepted'})
        elif action == 'decline':
            friend_request.delete()
            logger.info("Friend request declined.")
            return JsonResponse({'status': 'success', 'message': 'Friend request declined'})
        else:
            logger.warning("Invalid action provided.")
            return JsonResponse({'status': 'error', 'message': 'Invalid action'}, status=400)
    except Exception as e:
        logger.error(f"Error responding to friend request: {e}")
        return JsonResponse({'status': 'error', 'message': 'An error occurred'}, status=500)


@login_required
def update_profile_settings(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)

    if request.method == 'POST':
        profile_visibility = request.POST.get('profile_visibility')
        if profile_visibility == 'on':  # 'on' means checked (public)
            request.user.profile_visibility = 'public'
        else:
            request.user.profile_visibility = 'private'
        request.user.save()
        messages.success(request, "Profile settings updated successfully.")

    return redirect('profile', org_id=org_id)


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
def friend_info(request, org_id, friend_id):
    organization = get_object_or_404(Organization, id=org_id)
    friend = get_object_or_404(User, id=friend_id, organization=organization)

    # Check if there's an existing friendship or pending request
    friend_relationship = Friend.objects.filter(
        Q(user1=request.user, user2=friend) | Q(user1=friend, user2=request.user)
    ).first()

    is_friend = False
    request_pending = False
    if friend_relationship:
        if friend_relationship.status == 'accepted':
            is_friend = True
        elif friend_relationship.status == 'pending':
            request_pending = True

    # Determine if only basic info should be shown
    show_basic_info_only = not friend.is_public and not is_friend

    # Query for shared experiments where both users are involved
    shared_experiments = Experiment.objects.filter(
        Q(organization=organization),
        Q(owner=request.user) | Q(collaborators__user=request.user),
        Q(owner=friend) | Q(collaborators__user=friend)
    ).distinct()

    return render(request, 'friend_info.html', {
        'organization': organization,
        'friend': friend,
        'shared_experiments': shared_experiments if not show_basic_info_only else None,
        'is_friend': is_friend,
        'request_pending': request_pending,
        'show_basic_info_only': show_basic_info_only,
        'org_id': org_id
    })

@login_required
def search_users(request):
    query = request.GET.get('query', '')
    organization = request.user.organization

    if query:
        users = User.objects.filter(
            Q(username__icontains=query) | Q(email__icontains=query),
            organization=organization  # Ensure users are from the same organization
        ).exclude(id=request.user.id)
    else:
        users = User.objects.none()

    # Return organization_id and user id
    users_list = [{
        'id': user.id,
        'username': user.username,
        'organization_id': organization.id,  # Include organization_id
        'profile_picture': user.profile_picture.url if user.profile_picture else None
    } for user in users]

    return JsonResponse({'users': users_list})


from django.contrib.auth.decorators import login_required
from django.shortcuts import render
import logging

logger = logging.getLogger(__name__)
@login_required
def dashboard(request):
    if not request.user.is_authenticated:
        logger.error(f"User {request.user.username} is not authenticated.")
        return redirect('login')

    logger.info(f"User {request.user.username} is authenticated and accessing the dashboard.")

    user = request.user

    # Skip organization check
    org_id = None
    if hasattr(user, 'organization') and user.organization:
        org_id = user.organization.id
    else:
        logger.warning(f"User {user.username} does not have an organization. Proceeding without org_id.")

    # Corrected query: Replace groupmember with group_members
    conversations = Conversation.objects.filter(
        Q(user1=user) | Q(user2=user) | Q(group_members__user=user)
    ).distinct()

    total_unread_messages = Message.objects.filter(
        conversation__in=conversations,
        is_read=False
    ).exclude(sender=user).count()

    upcoming_events_count = CalendarEvent.objects.filter(user=user, start_date__gte=timezone.now()).count()
    active_experiments_count = Experiment.objects.filter(owner=user, ended=False).count()

    context = {
        'upcoming_events_count': upcoming_events_count,
        'unread_conversations_count': total_unread_messages,
        'active_experiments_count': active_experiments_count,
        'org_id': org_id,  # Pass `None` if no organization exists
    }

    return render(request, 'dashboard.html', context)

@login_required
def aggregate_health_data(request):
    # Fetch all experiments the user has access to
    user_experiments = Experiment.objects.filter(
        Q(owner=request.user) | Q(collaborators__user=request.user)
    )

    # Initialize counts
    total_healthy = 0
    total_at_risk = 0
    total_removal_needed = 0

    # Iterate over each experiment
    for experiment in user_experiments:
        assignments = RFIDAssignment.objects.filter(experiment=experiment)

        for assignment in assignments:
            animal = Animal.objects.filter(experiment=experiment, id=assignment.animal_id).first()
            if animal:
                latest_measurement = WeightMeasurement.objects.filter(animal=animal).order_by('-timestamp').first()

                if latest_measurement and assignment.initial_weight:
                    weight_change_percentage = ((assignment.initial_weight - latest_measurement.weight) / assignment.initial_weight) * 100

                    if weight_change_percentage < 15:
                        total_healthy += 1
                    elif 15 <= weight_change_percentage < 20:
                        total_at_risk += 1
                    else:
                        total_removal_needed += 1

    # Prepare data for the response
    health_data = {
        'healthy': total_healthy,
        'at_risk': total_at_risk,
        'removal_needed': total_removal_needed,
    }

    return JsonResponse(health_data)

@login_required
@require_POST
def add_collaborator(request):
    data = json.loads(request.body)
    experiment_id = data['experiment_id']
    username = data['username']
    role = data['role']

    user = get_object_or_404(User, username=username, organization=request.user.organization)
    experiment = get_object_or_404(Experiment, id=experiment_id, organization=request.user.organization)

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
@require_POST
def update_collaborator_role(request):
    data = request.json()
    experiment_id = data['experiment_id']
    user_id = data['user_id']
    role = data['role']

    # Ensure the experiment and user belong to the same organization
    experiment = get_object_or_404(Experiment, id=experiment_id, owner__organization=request.user.organization)
    Collaborator.objects.filter(experiment=experiment, user_id=user_id).update(role=role)
    
    return JsonResponse({'status': 'Collaborator role updated'})

@login_required
@require_POST
def respond_invitation(request):
    data = json.loads(request.body)
    invitation_id = data.get('invitation_id')
    action = data.get('action')

    if not invitation_id:
        return JsonResponse({'status': 'error', 'message': 'Invitation ID is missing'}, status=400)

    try:
        invitation = Invitation.objects.get(id=invitation_id, experiment__owner__organization=request.user.organization)
    except Invitation.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Invalid Invitation ID or no permission'}, status=404)

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
def remove_collaborator(request):
    data = request.json()
    experiment_id = data['experiment_id']
    user_id = data['user_id']

    # Ensure the experiment belongs to the same organization
    experiment = get_object_or_404(Experiment, id=experiment_id, owner__organization=request.user.organization)

    Collaborator.objects.filter(experiment=experiment, user_id=user_id).delete()
    return JsonResponse({'status': 'Collaborator removed'})


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
@require_POST
def create_group(request):
    data = request.json()
    group_name = data['group_name']
    user_ids = data['user_ids']

    # Ensure the users being added to the group belong to the same organization
    users = User.objects.filter(id__in=user_ids, organization=request.user.organization)

    conversation = Conversation.objects.create(type='group', name=group_name)

    for user in users:
        GroupMember.objects.create(conversation=conversation, user=user)

    return JsonResponse({'status': 'Success', 'message': 'Group created successfully', 'conversation_id': conversation.id})

def request_demo(request):
    if request.method == 'POST':
        # Capture the form data
        name = request.POST.get('name')
        email = request.POST.get('email')
        company = request.POST.get('company')
        message = request.POST.get('message')

        # Here you can either send an email or save the request to the database
        # Example: Sending email
        send_mail(
            f"Demo Request from {name} ({company})",
            message,
            email,
            [settings.DEFAULT_FROM_EMAIL],  # Replace with your email
        )

        return HttpResponse("Thank you for requesting a demo. We will get back to you soon.")
    
    return render(request, 'request_demo.html')

@login_required
def forms(request, org_id):
    """Renders the forms page for regular users."""
    user = request.user

    # Ensure the user is in the correct organization
    if user.organization.id != int(org_id):
        return HttpResponseForbidden("You are not allowed to access forms from another organization.")

    # Get signed forms for the user within their organization
    signed_forms = SignedForm.objects.filter(user=user, form__created_by__organization=user.organization)

    # Get available admin-created forms in the user's organization (do not exclude signed forms)
    admin_forms = AdminCreatedForm.objects.filter(
        created_by__organization=user.organization
    )

    # Get available PDF templates uploaded by admins
    pdf_templates = PDFTemplate.objects.filter(
        created_by=request.user  # Assuming this links to the correct field
    )

    return render(request, 'forms.html', {
        'org_id': org_id,
        'signed_forms': signed_forms,
        'admin_forms': admin_forms,
        'pdf_templates': pdf_templates,  # Pass the PDF templates
        'MEDIA_URL': settings.MEDIA_URL
    })

@login_required
def form_detail(request, org_id, form_id):
    form = get_object_or_404(AdminCreatedForm, id=form_id, created_by__organization_id=org_id)
    pdf_template = get_object_or_404(PDFTemplate, name=form.name)
    user = request.user

    if request.method == 'POST':
        signed_form = request.FILES.get('signed_form')
        is_anonymous = request.POST.get('is_anonymous') == 'on'  # Convert checkbox value to boolean
        is_high_importance = request.POST.get('is_high_importance') == 'on'  # Convert checkbox value to boolean

        if signed_form:
            # Save the signed form
            fs = FileSystemStorage()
            filename = fs.save(signed_form.name, signed_form)

            # Create a new SignedForm instance
            SignedForm.objects.create(
                user=None if is_anonymous else user,  # If anonymous, set user to None
                form=form,
                file_path=filename,
                is_anonymous=is_anonymous,
                is_high_importance=is_high_importance,
                signed_date=timezone.now()
            )

            return redirect('forms', org_id=org_id)

    return render(request, 'form_detail.html', {
        'form': form,
        'pdf_template': pdf_template,
        'org_id': org_id,
    })


# Generate PDF dynamically
def generate_pdf(name, email):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.drawString(100, 750, f"Name: {name}")
    p.drawString(100, 730, f"Email: {email}")
    p.showPage()
    p.save()
    
    buffer.seek(0)
    return HttpResponse(buffer, content_type='application/pdf')

# Generate DOCX dynamically
def generate_docx(name, email):
    buffer = BytesIO()
    doc = Document()
    doc.add_heading('Form Details', 0)
    doc.add_paragraph(f"Name: {name}")
    doc.add_paragraph(f"Email: {email}")
    doc.save(buffer)
    buffer.seek(0)
    return HttpResponse(buffer, content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')


@login_required
def fill_pdf_template(request, org_id, template_id):
    pdf_template = get_object_or_404(PDFTemplate, id=template_id, organization_id=org_id)

    # Fetch the mapped fields marked as editable
    mapped_fields = PDFFieldMapping.objects.filter(pdf_template=pdf_template, is_editable=True).select_related('form_field')

    # Prepare form fields data by getting the related FormField details
    form_fields = []
    for field_mapping in mapped_fields:
        form_field = field_mapping.form_field

        field_info = {
            'id': field_mapping.id,
            'field_name': field_mapping.field_name,
            'x': field_mapping.x,
            'y': field_mapping.y,
            'width': field_mapping.width,
            'height': field_mapping.height,
            'field_label': form_field.field_label,
            'field_type': form_field.field_type,
            'choices': form_field.choices.split(',') if form_field.field_type == 'multiple_choice' else None,
        }

        form_fields.append(field_info)

    if request.method == 'POST':
        # Gather the filled data from the form
        filled_data = {}
        for field_mapping in mapped_fields:
            filled_data[field_mapping.field_name] = request.POST.get(f'field_{field_mapping.id}')

        # Generate a PDF or store the filled data
        pdf_file_path = generate_filled_pdf(filled_data, pdf_template, request.user)

        # Save the filled PDF information to the database (or as needed)
        SignedForm.objects.create(
            user=request.user,
            form=pdf_template,
            file_path=pdf_file_path
        )

        # Redirect to a confirmation or dashboard page
        return redirect('submission_confirmation', org_id=org_id, template_id=template_id)

    return render(request, 'fill_pdf_template.html', {
        'pdf_template': pdf_template,
        'form_fields': form_fields,  # Only pass editable fields to the template
        'org_id': org_id,
    })


def generate_filled_pdf(filled_data, pdf_template, user):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)

    # Example: writing filled fields to the PDF
    p.drawString(100, 750, f"Filled by: {user.username}")
    y_position = 700
    for field_name, value in filled_data.items():
        p.drawString(100, y_position, f"{field_name}: {value}")
        y_position -= 20  # Move down for next field

    p.showPage()
    p.save()

    # Save the generated PDF to a file
    pdf_filename = f'{pdf_template.name}_filled_by_{user.username}.pdf'
    pdf_path = default_storage.save(f'signed_forms/{pdf_filename}', buffer)

    return pdf_path


@login_required
def download_form(request, form_id):
    # Fetch the form
    form = get_object_or_404(UserFilledForm, id=form_id, user=request.user)

    # Fetch the file path (PDF/DOCX)
    file_path = form.file_path.path  # Ensure this points to the correct location of the file
    
    # Check if file exists
    if not os.path.exists(file_path):
        raise Http404("File does not exist")
    
    # Serve the file as a download response
    file_extension = os.path.splitext(file_path)[1]
    if file_extension == '.pdf':
        content_type = 'application/pdf'
    elif file_extension == '.docx':
        content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    else:
        raise Http404("Unsupported file type")

    response = FileResponse(open(file_path, 'rb'), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
    return response

@login_required
def forms_page(request):
    # Fetch all forms created by the admin and forms signed by the user
    admin_forms = AdminCreatedForm.objects.all()  # Fetch forms created by admin
    signed_forms = SignedForm.objects.filter(user=request.user)  # Fetch signed forms
    
    return render(request, 'forms.html', {
        'admin_forms': admin_forms,
        'signed_forms': signed_forms
    })

def fill_form(request):
    if request.method == 'POST':
        # Get form data
        name = request.POST.get('name')
        email = request.POST.get('email')
        date_of_birth = request.POST.get('date_of_birth')
        document_type = request.POST.get('document_type')

        if document_type == 'pdf':
            return generate_pdf(name, email, date_of_birth)
        elif document_type == 'docx':
            return generate_docx(name, email, date_of_birth)

    return render(request, 'fill_form.html')

@login_required
def fill_out_form(request, org_id, form_id):
    # Ensure the form belongs to the user's organization
    form_instance = get_object_or_404(AdminCreatedForm, id=form_id, created_by__organization_id=org_id)

    # Prepare fields for rendering with choices if applicable
    fields_with_choices = []
    for field in form_instance.fields.all():
        if field.field_type == 'multiple_choice' and field.choices:
            field.split_choices = [choice.strip() for choice in field.choices.split(',')]
        fields_with_choices.append(field)

    return render(request, 'fill_out_form.html', {
        'org_id': org_id,  # Pass org_id to the template
        'form_instance': form_instance,
        'fields_with_choices': fields_with_choices
    })

@login_required
def user_forms(request, org_id):
    user = request.user
    forms = UserFilledForm.objects.filter(user=user)

    return render(request, 'user/forms.html', {
        'forms': forms,
        'org_id': org_id
    })
@login_required
def submit_signed_form(request, org_id, form_id):
    admin_form = get_object_or_404(AdminForm, id=form_id)
    user = request.user

    if request.method == 'POST':
        signed_form = request.FILES.get('signed_form')
        is_anonymous = request.POST.get('is_anonymous') == 'on'  # Handle anonymous submission

        if signed_form:
            # Save the signed form
            fs = FileSystemStorage()
            filename = fs.save(signed_form.name, signed_form)

            # Create a new SignedAdminForm instance
            SignedAdminForm.objects.create(
                user=None if is_anonymous else user,  # Set user to None if anonymous
                admin_form=admin_form,
                file_path=filename,
                signed_at=timezone.now()
            )

            return redirect('admin_signed_forms', org_id=org_id)

    return render(request, 'submit_signed_admin_form.html', {
        'admin_form': admin_form,
        'org_id': org_id,
    })


@login_required
def submission_confirmation(request, org_id, pdf_template_id):
    pdf_template = get_object_or_404(PDFTemplate, id=pdf_template_id, organization_id=org_id)

    # Retrieve the filled data from the session
    filled_data = request.session.get('filled_data', {})

    if request.method == 'POST':
        # Handle final submission here, generate PDF, save it, etc.
        pdf_file_path = generate_filled_pdf(filled_data, pdf_template, request.user)

        SignedForm.objects.create(
            user=request.user,
            form=pdf_template,
            file_path=pdf_file_path
        )

        # Clear session data after submission
        request.session.pop('filled_data', None)

        return redirect('dashboard')

    return render(request, 'submission_confirmation.html', {
        'pdf_template': pdf_template,
        'filled_data': filled_data,
        'org_id': org_id,
    })
