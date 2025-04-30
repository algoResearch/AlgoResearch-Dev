from django.contrib import messages
from django.contrib import messages as django_messages
from django.contrib.auth.forms import AuthenticationForm
from django.core import serializers
from django.utils.timezone import now
import hashlib
from myapp.utils.get_base_template import get_base_template
from django.urls import reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden, HttpResponseRedirect, FileResponse, Http404
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test  # To res
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q, F, Avg, Max, Min, Count
from django.utils import timezone
from .models import (Conversation, UserCertification, Certification, InboxNotification, PDFTemplate, UserFilledForm, UserAction,PDFFieldMapping, UserSignature, Organization, SignedForm, AdminForm, AdminCreatedForm, SignedAdminForm, Message, User, GroupMember, Experiment, RFIDAssignment, WeightMeasurement, Collaborator, CalendarEvent, Comment, Friend, Cage, Animal, Sample, Dose, Observation, Comment)
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


def is_admin_or_principal(user):
    return user.role in ['admin', 'principal_admin']

def is_principal_admin(user):
    return user.role == 'principal_admin'
def is_researcher(user):
    return user.role in ['viewer', 'researcher', 'officer', 'admin', 'principal_admin']
def is_viewer(user):
    return user.role == 'viewer'
def is_officer(user):
    return user.role == 'officer'
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
    

def fetch_dashboard_notifications(request, org_id):
    # Fetch notifications logic
    notifications = InboxNotification.objects.filter(
        organization_id=org_id, is_read=False
    ).order_by('-timestamp')
    
    # Log notifications for debugging
    logger.debug(f"Fetched notifications: {notifications}")

    data = [
        {
            "id": notification.id,
            "title": notification.title,
            "timestamp": notification.timestamp.isoformat()
        }
        for notification in notifications
    ]
    return JsonResponse(data, safe=False)

@login_required
def admin_profile(request, org_id):
    return profile(request, org_id)  # ✅ No extra `admin`
@login_required
def profile(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    base_template = get_base_template(request.user)

    # Profile update logic
    if request.method == 'POST':
        profile_form = UpdateProfileForm(request.POST, request.FILES, instance=request.user)
        if profile_form.is_valid():
            profile_form.save()
            return redirect(
                'admin_profile' if request.path.startswith(f'/{org_id}/admin/') else 'profile',
                org_id=org_id
            )
    else:
        profile_form = UpdateProfileForm(instance=request.user)

    pending_requests = Friend.objects.filter(user2=request.user, status='pending')
    friends = Friend.objects.filter(
        Q(user1=request.user) | Q(user2=request.user),
        status='accepted'
    )

    friends_list = [f.user2 if f.user1 == request.user else f.user1 for f in friends]

    return render(request, 'profile.html', {
        'organization': organization,
        'org_id': org_id,
        'pending_requests': pending_requests,
        'friends': friends_list,
        'profile_form': profile_form,
        'base_template': base_template,
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
    if request.method == 'POST' and request.FILES.get('profile_picture'):
        profile_form = ProfilePictureForm(request.POST, request.FILES, instance=request.user)
        profile_picture = request.FILES['profile_picture']
        
        try:
            # Resize the uploaded image to standard dimensions for profile pictures
            resized_image = resize_image(profile_picture, width=150, height=150)

            # Save the resized image
            profile = request.user
            profile.profile_picture.save(f"profile_{profile.id}.jpg", resized_image, save=True)

            messages.success(request, 'Profile picture updated successfully.')
            logger.info(f"Profile picture updated successfully for user {profile.username}")
        except Exception as e:
            logger.error(f"Error updating profile picture: {e}")
            messages.error(request, 'An error occurred while updating your profile picture.')
    else:
        messages.error(request, 'No file uploaded or invalid request.')

    # Redirect back to the profile page
    return redirect('profile', org_id=org_id)

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

    if request.method == 'POST':
        form = BannerUploadForm(request.POST, request.FILES, instance=request.user)

        if form.is_valid():
            banner_file = form.cleaned_data.get('profile_banner')

            if banner_file:
                try:
                    # Resize and save the banner
                    resized_banner = resize_image(banner_file, width=1200, height=400)
                    request.user.profile_banner.save(
                        f"banner_{request.user.id}.jpg", resized_banner, save=True
                    )
                    messages.success(request, "Profile banner updated successfully.")
                except Exception as e:
                    messages.error(request, f"An error occurred: {e}")
                    logger.error(f"Error updating profile banner: {e}")
            else:
                messages.error(request, "No banner file uploaded.")
        else:
            for error in form.errors.values():
                messages.error(request, error)

    return redirect('profile', org_id=org_id)

@login_required
def update_user_info(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    user = request.user

    if request.method == 'POST':
        profile_form = UpdateProfileForm(request.POST, request.FILES, instance=user)

        if profile_form.is_valid():
            # Handle profile banner removal if necessary
            if 'profile_banner' in request.FILES:
                # Remove old file if it exists
                if user.profile_banner and os.path.exists(user.profile_banner.path):
                    os.remove(user.profile_banner.path)

            # Save the form after handling the file update
            profile_form.save()
            messages.success(request, 'Profile updated successfully.')
        else:
            for error in profile_form.errors.values():
                messages.error(request, error)

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
    Update user settings: profile visibility, mute notifications, and dark mode.
    """
    organization = get_object_or_404(Organization, id=org_id)
    user = request.user

    # Profile visibility
    user.is_public = request.POST.get('profile_visibility') == 'on'

    # Mute all notifications
    user.mute_all_notifications = request.POST.get('mute_notifications') == 'on'

    # Dark mode
    user.dark_mode = request.POST.get('dark_mode') == 'on'

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

            # ✅ Check if agency user
            if user.position_type == 'agency_user' and user.agency:
                logger.info(f"Agency user {user.username} logged in.")
                return HttpResponseRedirect(reverse('agency_dashboard'))  # Define this route!

            # ✅ Otherwise, assume org user
            if hasattr(user, 'organization') and user.organization is not None:
                org_id = user.organization.id
                logger.info(f"User {user.username} logged in successfully.")
                return HttpResponseRedirect(reverse('admin_dashboard', args=[org_id]))

            # ❌ Neither org nor agency assigned
            logger.warning(f"User {user.username} has no organization or agency.")
            return render(request, 'admin/admin_login.html', {
                'error': 'This user does not have an associated organization or agency.'
            })

        else:
            logger.warning(f"Invalid login attempt for user {username}.")
            return render(request, 'admin/admin_login.html', {'error': 'Invalid username or password.'})
    
    logger.info(f"Rendering login page. Current path: {request.path}")
    return render(request, 'admin/admin_login.html')
@login_required
@require_POST
def add_friend(request, org_id):
    friend_username = request.POST.get('friend_username', None)
    organization = get_object_or_404(Organization, id=org_id)
    
    if friend_username:
        try:
            # Fetch the user to add as a friend
            
            friend_user = get_object_or_404(User, username=friend_username)

            
            # Check if a friend request already exists or if they are already friends
            friend_relationship = Friend.objects.filter(
                Q(user1=request.user, user2=friend_user) | Q(user1=friend_user, user2=request.user)
            ).first()

            if friend_relationship:
                if friend_relationship.status == 'pending':
                    messages.info(request, f"Friend request to {friend_username} is already pending.")
                elif friend_relationship.status == 'accepted':
                    messages.info(request, f"You are already friends with {friend_username}.")
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

                messages.success(request, f"Friend request sent to {friend_username}.")
        except User.DoesNotExist:
            messages.error(request, f"User {friend_username} does not exist or is not in your organization.")
    else:
        messages.error(request, "Invalid friend request.")
    return redirect('friend_info', org_id=friend_user.organization.id, friend_id=friend_user.id)

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
@require_POST
def rescind_friend_request(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    friend_username = request.POST.get('friend_username')

    if friend_username:
        try:
            # Find the friend and the friend request
            friend_user = get_object_or_404(User, username=friend_username)
            friend_request = Friend.objects.filter(
                user1=request.user, user2=friend_user, status='pending'
            ).first()

            if friend_request:
                friend_request.delete()
                messages.success(request, f"Friend request to {friend_username} has been rescinded.")
            else:
                messages.error(request, f"No pending friend request to {friend_username}.")

        except User.DoesNotExist:
            messages.error(request, f"User {friend_username} not found in your organization.")

    return redirect('friend_info', org_id=friend_user.organization.id, friend_id=friend_user.id)

@login_required
@require_POST
def unfriend_user(request, org_id):
    friend_username = request.POST.get('friend_username', None)
    organization = get_object_or_404(Organization, id=org_id)

    if friend_username:
        try:
            friend_user = get_object_or_404(User, username=friend_username)
            # Remove the friendship
            Friend.objects.filter(
                Q(user1=request.user, user2=friend_user) | Q(user1=friend_user, user2=request.user)
            ).delete()
            messages.success(request, f"You have unfriended {friend_user.username}.")
        except User.DoesNotExist:
            messages.error(request, "User not found or does not belong to your organization.")
    else:
        messages.error(request, "Invalid request.")
    return redirect('friend_info', org_id=friend_user.organization.id, friend_id=friend_user.id)
@login_required
@require_POST
def block_user(request, org_id):
    friend_username = request.POST.get('friend_username')
    organization = get_object_or_404(Organization, id=org_id)

    try:
        friend_user = get_object_or_404(User, username=friend_username)
        if friend_user != request.user:
            request.user.block_user(friend_user)
            # Remove any existing friendship
            Friend.objects.filter(
                Q(user1=request.user, user2=friend_user) | Q(user1=friend_user, user2=request.user)
            ).delete()
            messages.success(request, f"You have blocked {friend_user.username}.")
        else:
            messages.error(request, "You cannot block yourself.")
    except User.DoesNotExist:
        messages.error(request, "User not found.")
    return redirect('friend_info', org_id=friend_user.organization.id, friend_id=friend_user.id)

@login_required
@require_POST
def unblock_user(request, org_id):
    friend_username = request.POST.get('friend_username')
    organization = get_object_or_404(Organization, id=org_id)

    try:
        friend_user = get_object_or_404(User, username=friend_username)
        request.user.unblock_user(friend_user)
        messages.success(request, f"You have unblocked {friend_user.username}.")
    except User.DoesNotExist:
        messages.error(request, "User not found.")
    return redirect('friend_info', org_id=friend_user.organization.id, friend_id=friend_user.id)



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
def get_user_id(request):
    username = request.GET.get('username')
    try:
        user = get_object_or_404(User, username=username)
        return JsonResponse({'status': 'success', 'friend_id': user.id})
    except User.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'User not found'}, status=404)
from django.templatetags.static import static
@login_required
def friend_info(request, org_id, friend_id):
  
    friend = get_object_or_404(User, id=friend_id)
    organization = friend.organization

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

    is_blocked = request.user.blocked_users.filter(id=friend.id).exists()

    return render(request, 'friend_info.html', {
        'organization': organization,
        'friend': friend,
        'shared_experiments': shared_experiments if not show_basic_info_only else None,
        'is_friend': is_friend,
        'request_pending': request_pending,
        'show_basic_info_only': show_basic_info_only,
        'org_id': org_id,
        'is_blocked': is_blocked,
        'organization_color': organization.sidebar_color,  # Pass organizational color
        'organization_logo': static('img/Willie Waylons 1 .png')  # Pass default logo
    })

@login_required
def search_users(request):
    query = request.GET.get('query', '').strip()

    if query:
        # Split query by spaces
        terms = query.split()
        if len(terms) == 2:
            first, last = terms
            users = User.objects.filter(
                (Q(first_name__icontains=first) & Q(last_name__icontains=last)) |
                Q(username__icontains=query) |
                Q(email__icontains=query)
            ).exclude(id=request.user.id)
        else:
            users = User.objects.filter(
                Q(username__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(email__icontains=query)
            ).exclude(id=request.user.id)
    else:
        users = User.objects.none()

    users_list = [
        {
            'id': user.id,
            'unique_id': user.unique_id,
            'username': user.username,
            'profile_picture': user.profile_picture.url if user.profile_picture else None,
            'prefix': user.prefix,
            'first_name': user.first_name,
            'middle_name': user.middle_name,
            'last_name': user.last_name,
            'suffix': user.suffix,
            'position': user.position,
            'organization': user.organization.name if user.organization else "",
            'organization_id': user.organization.id if user.organization else None,
            'department': user.department,
            'division': user.division if hasattr(user, 'division') else "",
            'street1': user.street1,
            'street2': user.street2,
            'city': user.city,
            'county': user.county,
            'state': user.state if user.country == "USA" else None,
            'province': user.province if user.country != "USA" else None,
            'country': user.country,
            'zip_code': user.zip_code,
            'phone_number': user.phone_number,
            'fax': user.fax,
            'email': user.email,
        }
        for user in users
    ]

    return JsonResponse({'users': users_list})


@login_required
def get_user_details(request):
    user_id = request.GET.get("user_id")
    if not user_id:
        return JsonResponse({"error": "User ID not provided"}, status=400)

    user = get_object_or_404(User, id=user_id)

    # Fetch assigned certifications for the selected user
    assigned_certs = UserCertification.objects.filter(user=user).select_related("certification")

    user_certifications = [
        {
            "course_title": cert.certification.course_title,
            "course_id": cert.certification.course_id,
            "folder_name": cert.certification.folder.name if cert.certification.folder else "No Folder"
        }
        for cert in assigned_certs
    ]

    user_data = {
        "id": user.id,
        "prefix": user.prefix,  # New field: Prefix
        "first_name": user.first_name,
        "middle_name": user.middle_name,  # New field: Middle Name
        "last_name": user.last_name,
        "suffix": user.suffix,  # New field: Suffix
        "position": user.position,  # New field: Position
        "department": user.department,
        "email": user.email,
        "net_id": user.net_id,
        "phone_number": user.phone_number,
        "fax": user.fax,  # New field: Fax Number
        "mail_code": user.mail_code,
        "street1": user.street1,  # New field: Street 1
        "street2": user.street2,  # New field: Street 2 (optional)
        "city": user.city,  # New field: City
        "county": user.county,  # New field: County
        "state": user.state if user.country == "USA" else None,  # New field: State (if in US)
        "province": user.province if user.country != "USA" else None,  # New field: Province (if outside US)
        "country": user.country,  # New field: Country
        "zip_code": user.zip_code,  # New field: Zip Code
        "certifications": user_certifications,  # Include assigned certifications
    }

    return JsonResponse(user_data)

@csrf_exempt  # Use this only if you don't include the CSRF token in AJAX requests
@login_required
def save_dashboard_layout(request):
    if request.method == "POST":
        try:
            layout = json.loads(request.body).get("layout", [])
            request.user.dashboard_layout = layout
            request.user.save()
            return JsonResponse({"status": "success", "message": "Layout saved successfully."})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)
    return JsonResponse({"status": "error", "message": "Invalid request method."}, status=405)


logger = logging.getLogger(__name__)

@login_required
@user_passes_test(is_researcher)
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
        'org_id': org_id,  # Pass None if no organization exists
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

    # Get forms explicitly assigned to the user
    assigned_forms = UserFilledForm.objects.filter(user=user).select_related('form')

    # Get available admin-created forms in the user's organization (excluding signed forms)
    admin_forms = AdminCreatedForm.objects.filter(
        id__in=assigned_forms.values_list('form_id', flat=True)
    )

    return render(request, 'forms.html', {
        'org_id': org_id,
        'signed_forms': signed_forms,
        'admin_forms': admin_forms,  # Only forms assigned to the user
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
    # Get the logged-in user
    user = request.user

    # Fetch forms explicitly assigned to the user
    assigned_forms = UserFilledForm.objects.filter(user=user).select_related('form')

    # Fetch admin-created forms assigned to the user
    admin_forms = AdminCreatedForm.objects.filter(
        id__in=assigned_forms.values_list('form_id', flat=True)
    )

    # Fetch signed forms for the user
    signed_forms = SignedForm.objects.filter(user=user)

    return render(request, 'forms.html', {
        'admin_forms': admin_forms,
        'signed_forms': signed_forms
    })

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
