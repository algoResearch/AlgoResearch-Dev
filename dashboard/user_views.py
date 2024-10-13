from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from django.core import serializers
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q, F, Avg, Max, Min, Count
from django.utils import timezone
from .models import (Conversation, PDFTemplate, UserFilledForm, UserAction,PDFFieldMapping, UserSignature, Organization, SignedForm, AdminForm, AdminCreatedForm, SignedAdminForm, Message, User, GroupMember, Experiment, RFIDAssignment, WeightMeasurement, Collaborator, CalendarEvent, Comment, Friend, Cage, Animal, Sample, Dose, Observation, Comment)
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, authenticate
import pandas as pd
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

        return redirect('profile', org_id=org_id)  # Ensure you redirect with org_id
    else:
        update_form = UpdateProfileForm(instance=request.user)
        profile_form = ProfilePictureForm(instance=request.user)

    return render(request, 'profile.html', {
        'form': update_form,
        'profile_form': profile_form,
        'organization': organization  # Pass the organization to the template if needed
    })

@login_required
def profile_view(request):
    if request.method == 'POST':
        profile_form = UpdateProfileForm(request.POST, request.FILES, instance=request.user)
        if profile_form.is_valid():
            profile_form.save()
            return redirect('profile')  # Redirect without org_id
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

def login_view(request):
    form = AuthenticationForm(request, data=request.POST or None)  # Pass request and data
    if form.is_valid():
        username = form.cleaned_data['username']
        password = form.cleaned_data['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.is_active:
                login(request, user)
                logger.debug(f"User {username} logged in successfully.")
                return redirect('/dashboard/')
            else:
                logger.error(f'User account for {username} is disabled.')
        else:
            logger.error(f'Invalid login attempt for username: {username}')
    
    return render(request, 'login.html', {'form': form})  # Pass the form to the template




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
                print(f"User {user.username} logged in successfully.")
                print(f"Redirecting to admin dashboard at /{org_id}/admin_dashboard/")  # Debug path
                return HttpResponseRedirect(f"/{org_id}/admin_dashboard/")  # Explicit redirect
            else:
                # If the user doesn't have an organization, redirect to a default page or show an error
                print(f"User {user.username} has no organization. Returning to login page.")
                return render(request, 'admin/admin_login.html', {'error': 'This user does not have an associated organization.'})
        else:
            # If authentication fails, show an error
            print(f"Invalid login attempt for user {username}.")
            return render(request, 'admin/admin_login.html', {'error': 'Invalid username or password.'})
    else:
        # Render the login page for GET requests
        print(f"Rendering login page. Current path: {request.path}")
        return render(request, 'admin/admin_login.html')
    
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
    user = get_object_or_404(User, id=friend_id, organization=request.user.organization)
    conversation = Conversation.objects.filter(Q(user1=request.user, user2=user) | Q(user1=user, user2=request.user)).first()

    return JsonResponse({
        'status': 'success', 
        'user': {
            'id': user.id,
            'username': user.username,
            'organization': user.organization,
            'title': user.title,
            'location': user.location,
            'conversation_id': conversation.id if conversation else None
        }
    })
@login_required
def search_users(request):
    query = request.GET.get('query', '')
    organization = request.user.organization

    if query:
        users = User.objects.filter(
            Q(username__icontains=query) | Q(email__icontains=query),
            organization=organization  # Ensure users are from the same organization
        ).exclude(id=request.user.id)  # Exclude the current user
    else:
        users = User.objects.none()

    users_list = [{
        'username': user.username,
        'email': user.email,
        'profile_picture': user.profile_picture.url if user.profile_picture else None
    } for user in users]

    return JsonResponse({'users': users_list})


@login_required
def dashboard(request):
    if not request.user.is_authenticated:
        logger.error(f"User {request.user.username} is not authenticated.")
        return redirect('login')
    logger.info(f"User {request.user.username} is authenticated and accessing the dashboard.")

    user = request.user
    org_id = user.organization.id if hasattr(user, 'organization') and user.organization else None
    conversations = Conversation.objects.filter(
        Q(user1=user) | Q(user2=user) | Q(groupmember__user=user)
    ).distinct()

    total_unread_messages = Message.objects.filter(
        conversation__in=conversations,
        is_read=False
    ).exclude(sender=user).count()

    upcoming_events_count = CalendarEvent.objects.filter(user=user, start_date__gte=timezone.now()).count()
    active_experiments_count = Experiment.objects.filter(owner=user, organization=user.organization, ended=False).count()

    context = {
        'upcoming_events_count': upcoming_events_count,
        'unread_conversations_count': total_unread_messages,
        'active_experiments_count': active_experiments_count,
    }

    return render(request, 'dashboard.html', {'org_id': org_id})

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

    # Get available admin-created forms in the user's organization that the user hasn't signed yet
    admin_forms = AdminCreatedForm.objects.filter(
        created_by__organization=user.organization
    ).exclude(id__in=signed_forms.values_list('form_id', flat=True))

    # Get available PDF templates uploaded by admins
    pdf_templates = PDFTemplate.objects.filter(
        created_by=request.user  # Use the correct field
    )
    return render(request, 'forms.html', {
        'org_id': org_id,
        'signed_forms': signed_forms,
        'admin_forms': admin_forms,
        'pdf_templates': pdf_templates,  # Pass the PDF templates
        'MEDIA_URL': settings.MEDIA_URL
    })
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
def forms_page(request):
    # Fetch all forms created by the admin and forms signed by the user
    admin_forms = AdminCreatedForm.objects.all()  # Fetch forms created by admin
    signed_forms = SignedForm.objects.filter(user=request.user)  # Fetch signed forms
    
    return render(request, 'forms.html', {
        'admin_forms': admin_forms,
        'signed_forms': signed_forms
    })


@login_required
def fill_form(request, form_id):
    """Handles the display and submission of a form created by the admin."""
    form_instance = get_object_or_404(AdminCreatedForm, id=form_id, created_by__organization=request.user.organization)

    if request.method == 'POST':
        for field in form_instance.fields.all():
            field_value = request.POST.get(f'field_{field.id}')
            # Handle saving the field values here
        return redirect('forms')  # Redirect back to forms or a confirmation page

    return render(request, 'fill_out_form.html', {'form_instance': form_instance})
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
def adverse_event_form(request):
    """Renders the adverse event form."""
    return render(request, 'adverse_event_form.html')

@login_required
def submit_filled_pdf_template(request, org_id, template_id):
    pdf_template = get_object_or_404(PDFTemplate, id=template_id, organization_id=org_id)
    mapped_fields = PDFFieldMapping.objects.filter(pdf_template=pdf_template, is_editable=True)

    if request.method == 'POST':
        filled_data = {}
        for field in mapped_fields:
            filled_data[field.field_name] = request.POST.get(f'field_{field.id}')

        # Store the filled data in session or pass it directly to the confirmation view
        request.session['filled_data'] = filled_data

        # Redirect to confirmation page
        return redirect('submission_confirmation', org_id=org_id, pdf_template_id=template_id)

    return render(request, 'fill_pdf_template.html', {
        'pdf_template': pdf_template,
        'form_fields': mapped_fields,
        'org_id': org_id,
    })


@login_required
def signed_forms(request):
    # Only show forms signed by the user within their organization
    signed_forms = SignedForm.objects.filter(user=request.user, form__created_by__organization=request.user.organization)

    return render(request, 'signed_forms.html', {'signed_forms': signed_forms})

def generate_pdf_from_filled_template(filled_data, pdf_template, user):
    buffer = BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    # Custom styles for larger titles and subtitles
    title_style = ParagraphStyle('TitleStyle', fontSize=20, alignment=1, spaceAfter=12)
    subtitle_style = ParagraphStyle('SubtitleStyle', fontSize=14, alignment=1, spaceAfter=10)
    field_label_style = ParagraphStyle('FieldLabelStyle', fontSize=12, spaceAfter=6, textColor=colors.black)
    user_input_style = ParagraphStyle('UserInputStyle', fontSize=11, spaceAfter=12, textColor=colors.gray)

    # Add header information
    elements.append(Paragraph(f"{pdf_template.name}", title_style))
    if pdf_template.description:
        elements.append(Paragraph(pdf_template.description, subtitle_style))
    elements.append(Spacer(1, 24))

    # Add user input fields
    for label, user_input in filled_data.items():
        if isinstance(user_input, list):  # Handle multiple-choice or checkboxes
            user_input = ', '.join(user_input)

        # Add form field label in bold
        elements.append(Paragraph(f"{label}:", field_label_style))

        # Add user input with lighter color and smaller font
        elements.append(Paragraph(f"{user_input}", user_input_style))
        elements.append(Spacer(1, 12))  # Add space after each field

    # Add submitted by info at the end
    elements.append(Paragraph(f"Submitted by: {user.username}", styles['Normal']))
    elements.append(Paragraph(f"Submission Date: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))

    # Build the PDF
    pdf.build(elements)

    # Save the PDF file
    pdf_file_name = f'{pdf_template.name}_filled_by_{user.username}_{timezone.now().strftime("%Y%m%d_%H%M%S")}.pdf'
    signed_forms_dir = os.path.join(settings.MEDIA_ROOT, 'signed_forms')
    if not os.path.exists(signed_forms_dir):
        os.makedirs(signed_forms_dir)
    pdf_file_path = os.path.join(signed_forms_dir, pdf_file_name)

    with open(pdf_file_path, 'wb') as f:
        f.write(buffer.getvalue())

    return pdf_file_path  # Return the file path for storing in SignedForm


@login_required
def submit_adverse_event(request):
    """Handles the submission of the adverse event form and generates a PDF with improved formatting."""
    if request.method == 'POST':
        # Extract form data
        asaf_no = request.POST.get('asaf_no')
        event_date = request.POST.get('event_date')
        event_location = request.POST.get('event_location')
        species = request.POST.get('species')
        num_animals = request.POST.get('num_animals')
        outcome = request.POST.getlist('outcome')  # Checkboxes may return multiple values
        related_research = request.POST.get('related_research')
        noted_protocol = request.POST.get('noted_protocol')
        event_description = request.POST.get('event_description')
        event_management = request.POST.get('event_management')
        corrective_actions = request.POST.get('corrective_actions')
        protocol_change = request.POST.get('protocol_change')
        amendment_submitted = request.POST.get('amendment_submitted')
        signature = request.POST.get('signature')
        report_date = datetime.date.today()

        # Create PDF in memory with improved formatting
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        p.setFont("Helvetica", 12)
        width, height = letter

        # Title section
        p.setFont("Helvetica-Bold", 14)
        p.drawString(100, height - 50, "INSTITUTIONAL ANIMAL CARE AND USE COMMITTEE")
        p.setFont("Helvetica", 12)
        p.drawString(100, height - 70, "ADVERSE EVENT/UNANTICIPATED OUTCOME REPORTING FORM")
        p.drawString(100, height - 85, "(Please type. Handwritten copies cannot be accepted)")

        # Line space
        line_height = 100

        # Details section
        p.setFont("Helvetica-Bold", 12)
        p.drawString(100, height - line_height, f"IACUC ASAF No(s):")
        p.setFont("Helvetica", 12)
        p.drawString(250, height - line_height, asaf_no if asaf_no else "N/A")
        line_height += 20
        
        p.setFont("Helvetica-Bold", 12)
        p.drawString(100, height - line_height, f"Adverse Event:")
        p.setFont("Helvetica", 12)
        p.drawString(250, height - line_height, "Any happening that is not consistent with routine expected outcomes ...")
        line_height += 20

        # Event Date and Location
        p.setFont("Helvetica-Bold", 12)
        p.drawString(100, height - line_height, f"Date of Event:")
        p.setFont("Helvetica", 12)
        p.drawString(250, height - line_height, event_date if event_date else "N/A")
        line_height += 20
        
        p.setFont("Helvetica-Bold", 12)
        p.drawString(100, height - line_height, f"Location of Event:")
        p.setFont("Helvetica", 12)
        p.drawString(250, height - line_height, event_location if event_location else "N/A")
        line_height += 20

        # Species and Number of Animals
        p.setFont("Helvetica-Bold", 12)
        p.drawString(100, height - line_height, f"Species:")
        p.setFont("Helvetica", 12)
        p.drawString(250, height - line_height, f"{species}   Number of animals: {num_animals if num_animals else 'N/A'}")
        line_height += 20

        # Outcome
        p.setFont("Helvetica-Bold", 12)
        p.drawString(100, height - line_height, f"Outcome:")
        p.setFont("Helvetica", 12)
        p.drawString(250, height - line_height, f"{', '.join(outcome)}")
        line_height += 20

        # Research related and Protocol
        p.setFont("Helvetica-Bold", 12)
        p.drawString(100, height - line_height, f"Is this event related to the research?")
        p.setFont("Helvetica", 12)
        p.drawString(350, height - line_height, related_research if related_research else "N/A")
        line_height += 20
        
        p.setFont("Helvetica-Bold", 12)
        p.drawString(100, height - line_height, f"Is the possibility of this event noted in the current approved protocol?")
        p.setFont("Helvetica", 12)
        p.drawString(450, height - line_height, noted_protocol if noted_protocol else "N/A")
        line_height += 20

        # Descriptions and Management
        p.setFont("Helvetica-Bold", 12)
        p.drawString(100, height - line_height, "Please provide a brief description of the adverse event/unanticipated outcome:")
        line_height += 20
        p.setFont("Helvetica", 12)
        p.drawString(100, height - line_height, event_description if event_description else "N/A")
        line_height += 40

        p.setFont("Helvetica-Bold", 12)
        p.drawString(100, height - line_height, "Please provide a description of how this event/outcome was managed:")
        line_height += 20
        p.setFont("Helvetica", 12)
        p.drawString(100, height - line_height, event_management if event_management else "N/A")
        line_height += 40

        p.setFont("Helvetica-Bold", 12)
        p.drawString(100, height - line_height, "Please provide a description, if known, of any corrective actions taken:")
        line_height += 20
        p.setFont("Helvetica", 12)
        p.drawString(100, height - line_height, corrective_actions if corrective_actions else "N/A")
        line_height += 40

        # Protocol and Amendment
        p.setFont("Helvetica-Bold", 12)
        p.drawString(100, height - line_height, f"Does this adverse event/unanticipated outcome require a change to the protocol?")
        p.setFont("Helvetica", 12)
        p.drawString(550, height - line_height, protocol_change if protocol_change else "N/A")
        line_height += 20

        p.setFont("Helvetica-Bold", 12)
        p.drawString(100, height - line_height, f"Has an amendment to the protocol been submitted for IACUC review?")
        p.setFont("Helvetica", 12)
        p.drawString(450, height - line_height, amendment_submitted if amendment_submitted else "N/A")
        line_height += 20

        # Signature and Date
        p.setFont("Helvetica-Bold", 12)
        p.drawString(100, height - line_height, f"Date of Report:")
        p.setFont("Helvetica", 12)
        p.drawString(250, height - line_height, str(report_date))
        line_height += 20
        
        p.setFont("Helvetica-Bold", 12)
        p.drawString(100, height - line_height, f"Signed by:")
        p.setFont("Helvetica", 12)
        p.drawString(250, height - line_height, signature if signature else "N/A")

        # Close the PDF object
        p.showPage()
        p.save()

        # Get the value of the BytesIO buffer and write it to a file
        pdf_data = buffer.getvalue()
        buffer.close()

        # Ensure the directory exists
        signed_forms_dir = os.path.join(settings.MEDIA_ROOT, 'signed_forms')
        if not os.path.exists(signed_forms_dir):
            os.makedirs(signed_forms_dir)

        # File path for the PDF (relative to MEDIA_ROOT)
        pdf_file_name = f'adverse_event_{request.user.username}_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        pdf_file_path = os.path.join('signed_forms', pdf_file_name)  # Only store the relative path

        # Write the PDF to the file system
        full_pdf_file_path = os.path.join(settings.MEDIA_ROOT, pdf_file_path)
        with open(full_pdf_file_path, 'wb') as f:
            f.write(pdf_data)

        # Save the signed form record in the database with relative path
        SignedForm.objects.create(
            user=request.user,
            form_name="Adverse Event/Unanticipated Outcome Reporting Form",
            file_path=pdf_file_path  # Store the relative path
        )

        # Save the signed form record in the database with relative path
        signed_form = SignedForm.objects.create(
            user=request.user,
            form_name="Adverse Event/Unanticipated Outcome Reporting Form",
            file_path=pdf_file_path  # Store the relative path
        )

        # Log the action of signing the document in UserAction
        UserAction.objects.create(
            user=request.user,
            action=f"Signed {signed_form.form_name}",
            typed_signature=signature,
            unique_signature=request.user.signature.signature_text  # Assuming the unique signature is stored in UserSignature
        )

        # Redirect to a confirmation page or show a success message
        return render(request, 'submission_confirmation.html', {
            'signature': signature,
            'event_description': event_description,
            'pdf_file': f'/media/{pdf_file_path}'
        })
    
    return render(request, 'adverse_event_form.html')


@login_required
def animal_care_concern_form(request):
    """Renders the animal care concern form page."""
    return render(request, 'animal_care_concern_form.html')


@login_required
def submit_animal_care_concern(request):
    """Handles the submission of the Animal Care Concern Reporting Form and generates a PDF."""
    if request.method == 'POST':
        # Determine if the submission is anonymous
        anonymous = request.POST.get('anonymous') == 'yes'
        
        # If not anonymous, capture reporter's details
        reporter_name = None
        contact_info = None
        if not anonymous:
            reporter_name = request.POST.get('reporter_name', '')
            contact_info = request.POST.get('contact_info', '')

        # Capture the nature of the concern
        concern_description = request.POST.get('concern_description')

        # Generate a PDF report
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        p.setFont("Helvetica", 10)

        # Write the content of the form to the PDF
        p.drawString(100, 750, "Animal Care Concern Reporting Form")
        p.drawString(100, 730, "We will expeditiously review any allegations regarding the care and use of animals.")
        p.drawString(100, 710, "DO NOT provide identification if you wish to remain anonymous.")

        if not anonymous:
            p.drawString(100, 680, f"Reporter's Name: {reporter_name}")
            p.drawString(100, 660, f"Contact Information: {contact_info}")
        else:
            p.drawString(100, 680, "Anonymous Submission")

        p.drawString(100, 640, "Concern Description:")
        p.drawString(100, 620, concern_description)

        p.drawString(100, 580, f"Submitted on: {timezone.now().strftime('%Y-%m-%d')}")

        # Finalize the PDF
        p.showPage()
        p.save()

        # Get the value of the BytesIO buffer and write it to a file
        pdf_data = buffer.getvalue()
        buffer.close()

        # Ensure the directory exists
        signed_forms_dir = os.path.join(settings.MEDIA_ROOT, 'signed_forms')
        if not os.path.exists(signed_forms_dir):
            os.makedirs(signed_forms_dir)

        # Generate a file name and save the PDF to the file system
        pdf_file_name = f'animal_care_concern_{reporter_name if reporter_name else "anonymous"}_{timezone.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        pdf_file_path = os.path.join('signed_forms', pdf_file_name)
        full_pdf_file_path = os.path.join(settings.MEDIA_ROOT, pdf_file_path)

        # Write the PDF file
        with open(full_pdf_file_path, 'wb') as f:
            f.write(pdf_data)

        # Save the form submission to the database (but don't link to the user if anonymous)
        SignedForm.objects.create(
            user=None if anonymous else request.user,
            form_name="Animal Care Concern Reporting Form",
            file_path=pdf_file_path,  # Store the relative path
            reviewed=False  # Automatically mark as unreviewed
        )

        # Log the user action if not anonymous
        if not anonymous:
            UserAction.objects.create(
                user=request.user,
                action='Submitted Animal Care Concern Form',
                additional_info=f"Concern submitted: {concern_description}",
                typed_signature=request.POST.get('signature', ''),
                unique_signature=request.user.signature.signature_text
            )

        # Redirect to a confirmation page or success message
        return render(request, 'submission_confirmation.html', {
            'pdf_file': f'/media/{pdf_file_path}'
        })

    return render(request, 'animal_care_concern_form.html')
@login_required
def user_forms(request):
    admin_forms = AdminForm.objects.filter(created_by__organization=request.user.organization)
    signed_forms = SignedAdminForm.objects.filter(user=request.user)

    available_forms = admin_forms.exclude(id__in=signed_forms.values_list('admin_form_id', flat=True))

    return render(request, 'forms.html', {
        'available_forms': available_forms,
        'signed_forms': signed_forms,
    })

@login_required
def forms_view(request):
    admin_forms = AdminForm.objects.all()  # Assuming you have an AdminForm model
    signed_forms = SignedForm.objects.filter(user=request.user)  # Signed forms for the user

    return render(request, 'forms.html', {
        'admin_forms': admin_forms,
        'signed_forms': signed_forms,
        'MEDIA_URL': settings.MEDIA_URL  # Ensure MEDIA_URL is passed to the template
    })

@login_required
def submit_filled_form(request, org_id, form_id):
    form_instance = get_object_or_404(AdminCreatedForm, id=form_id)

    if request.method == 'POST':
        filled_data = {}
        for field in form_instance.fields.all():
            user_input = request.POST.get(f'field_{field.id}', '')
            filled_data[field.field_label] = user_input

        # Generate the PDF from the filled data
        pdf_file_path = generate_pdf_from_filled_form(filled_data, form_instance, request.user)

        # Save the filled form as a SignedForm instance
        signed_form = SignedForm.objects.create(
            user=request.user,
            form=form_instance,
            file_path=pdf_file_path,
            digital_signature=request.POST.get('signature', ''),
        )

        # Redirect to a confirmation page
        return redirect('submission_confirmation', org_id=org_id, form_id=signed_form.id)

    return redirect('forms', org_id=org_id)

def generate_pdf_from_filled_form(filled_data, form_instance, user):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.setFont("Helvetica", 12)

    # Title and Description
    p.drawString(100, 800, f"Form: {form_instance.name}")
    p.drawString(100, 780, f"Description: {form_instance.description}")
    p.drawString(100, 760, f"Submitted by: {user.username}")
    line_height = 740

    # Render fields and user input
    for label, user_input in filled_data.items():
        p.drawString(100, line_height, f"{label}: {user_input}")
        line_height -= 20

    # Submission Date
    p.drawString(100, line_height, f"Submission Date: {timezone.now().strftime('%Y-%m-%d')}")
    p.showPage()
    p.save()

    pdf_data = buffer.getvalue()
    buffer.close()

    # Save the PDF file to the media directory
    pdf_file_name = f'{form_instance.name}_filled_by_{user.username}_{timezone.now().strftime("%Y%m%d_%H%M%S")}.pdf'
    pdf_file_path = os.path.join(settings.MEDIA_ROOT, 'signed_forms', pdf_file_name)
    
    with open(pdf_file_path, 'wb') as f:
        f.write(pdf_data)

    return pdf_file_path
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
