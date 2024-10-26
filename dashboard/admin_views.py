from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test, login_required, role_required
from .forms import CustomUserCreationForm, AdminCreatedFormForm, FormField, FormFieldForm, UploadPDFTemplateForm
from .models import User, UserFilledForm, Experiment, UserAction, UserSignature, InboxNotification, SignedForm, AdminCreatedForm, Organization, PDFFieldMapping
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.views.decorators.http import require_POST
from django.http import JsonResponse, FileResponse, Http404
from django.http import HttpResponseForbidden
from django.conf import settings
from django.urls import reverse
from django.contrib import messages as django_messages
from .pdf_utils import extract_pdf_fields
import logging
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login
from django.http import FileResponse
import os  # To handle file operations (e.g., saving and deleting temporary logo files)
from io import BytesIO  # For in-memory file handling (PDF generation)
from .models import PDFTemplate
from django.conf import settings  # To access project settings like MEDIA_ROOT
from django.shortcuts import render, get_object_or_404, redirect  # Standard shortcuts for rendering templates and managing views
from django.http import HttpResponse, HttpResponseForbidden  # To return HTTP responses, including PDF files or errors
from django.contrib.auth.decorators import login_required, user_passes_test  # To restrict views to logged-in users and superusers
from django.core.files.storage import FileSystemStorage  # For file handling and storage if needed
from PyPDF2 import PdfReader
from reportlab.lib.pagesizes import letter  # To set PDF page size
from reportlab.lib.styles import getSampleStyleSheet  # For setting up basic text styles in PDF
from reportlab.lib.units import inch  # To handle unit conversion (e.g., inches for image scaling)
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image  # For PDF generation (mainly layout and content elements)
import json

def admin_login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)

            # Check if the user has an associated organization
            if user.organization:
                org_id = user.organization.id
                return redirect('admin_dashboard', org_id=org_id)
            else:
                # If no organization is associated, redirect to some default page or show an error
                return render(request, 'admin/admin_login.html', {'error': 'This user is not associated with any organization.'})
        else:
            return render(request, 'admin/admin_login.html', {'error': 'Invalid username or password.'})
    else:
        return render(request, 'admin/admin_login.html')
    
@login_required
@role_required('principal_admin')  # Make sure this is the correct decorator for Principal Admin
def admin_actions_view(request, org_id):
    """
    Allows Principal Admin to view actions performed by Admin users.
    """
    admin_users = User.objects.filter(organization_id=org_id, role='admin')
    admin_actions = UserAction.objects.filter(user__in=admin_users).order_by('-timestamp')
    
    context = {
        'admin_actions': admin_actions,
        'org_id': org_id,
    }
    return render(request, 'principal_admin/admin_actions.html', context)

@login_required
@role_required('principal_admin')
def create_admin_view(request, org_id):
    """
    Allows Principal Admin to create new Admin users.
    """
    organization = get_object_or_404(Organization, id=org_id)

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.organization = organization
            user.role = 'admin'
            user.save()
            return redirect('admin_list_view', org_id=org_id)
    else:
        form = CustomUserCreationForm()

    return render(request, 'principal_admin/create_admin.html', {'form': form, 'organization': organization})


@login_required
@role_required('principal_admin')
def admin_list_view(request, org_id):
    """
    Allows Principal Admin to view all Admin users in the organization.
    """
    admins = User.objects.filter(organization_id=org_id, role='admin')

    context = {
        'admins': admins,
        'org_id': org_id,
    }
    return render(request, 'principal_admin/admin_list.html', context)

@user_passes_test(lambda u: u.is_superuser)
def admin_dashboard(request, org_id):
    user = request.user
    context = {
        'org_id': org_id,
        'user': user,
    }
    return render(request, 'admin/admin_dashboard.html', {'org_id': org_id})

@user_passes_test(lambda u: u.role == 'admin' or u.role == 'principal_admin')  # Only Admin or Principal Admin can create users
def create_user(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.organization = organization  # Assign the organization
            user.save()
            return redirect('admin_user_list', org_id=org_id)
    else:
        form = CustomUserCreationForm()

    return render(request, 'admin/create_user.html', {'form': form, 'organization': organization})


@user_passes_test(lambda u: u.is_superuser)
def user_list(request, org_id):
    organization = Organization.objects.get(id=org_id)
    users = User.objects.filter(organization=organization)

    context = {
        'users': users,
        'org_id': org_id,  # Pass the org_id to the template
    }
    return render(request, 'admin/user_list.html', context)

@user_passes_test(lambda u: u.is_superuser)
def user_experiments(request, org_id, user_id):
    user = get_object_or_404(User, id=user_id, organization_id=org_id)  # Ensure user is in the same organization
    experiments = Experiment.objects.filter(
        Q(owner=user) | Q(collaborators__user=user),
        organization_id=org_id  # Filter experiments by the organization
    ).distinct()

    context = {
        'user': user,
        'experiments': experiments,
        'org_id': org_id,
    }
    return render(request, 'admin/user_experiments.html', context)


@user_passes_test(lambda u: u.is_superuser)
def view_user(request, user_id, org_id):
    user = get_object_or_404(User, id=user_id, organization_id=org_id)  # Fetch user in the same organization
    return render(request, 'admin/view_user.html', {'user': user, 'org_id': org_id})


@login_required
@user_passes_test(lambda u: u.is_superuser)
def user_actions(request, user_id, org_id):
    user = get_object_or_404(User, id=user_id, organization_id=org_id)# Ensure user is in the same organization
    if request.user.organization != user.organization:
        return HttpResponseForbidden("You are not allowed to view actions for users outside your organization.")
    actions = UserAction.objects.filter(user=user).order_by('-timestamp')

    return render(request, 'admin/user_actions.html', {
        'user': user,
        'actions': actions,
        'org_id': org_id,
    })


# Signal to create UserSignature when a new user is created
@receiver(post_save, sender=User)
def create_user_signature(sender, instance, created, **kwargs):
    if created:
        # Automatically create a UserSignature instance for the new user
        UserSignature.objects.create(user=instance)

@user_passes_test(lambda u: u.is_superuser)
@user_passes_test(lambda u: u.is_superuser)
@login_required
def send_admin_notification(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)

    if request.method == 'POST':
        recipient_ids = request.POST.getlist('recipients')
        message_content = request.POST.get('message')

        if not recipient_ids or not message_content:
            django_messages.error(request, "Recipients and message content are required.")
            return redirect('send_admin_notification', org_id=org_id)

        # Filter recipients by organization
        recipients = User.objects.filter(id__in=recipient_ids, organization=organization)

        # Create notifications for each recipient
        for recipient in recipients:
            notification = InboxNotification.objects.create(
                user=recipient,
                message=message_content,
                from_admin=True  # Mark as admin notification
            )
            print(f"Notification created for user: {recipient.username} with message: {message_content}")

        django_messages.success(request, "Notification sent to selected users.")
        return redirect('admin_dashboard', org_id=org_id)

    users = User.objects.filter(organization=organization)  # Get users in the same organization
    return render(request, 'admin/send_admin_notification.html', {'users': users, 'org_id': org_id})

@login_required
def admin_notify(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)

    if request.method == 'POST':
        recipient_ids = request.POST.getlist('recipients')
        message_content = request.POST.get('message')

        if not recipient_ids or not message_content:
            django_messages.error(request, "Recipients and message content are required.")
            return redirect('admin_notify', org_id=org_id)

        # Filter recipients by organization
        recipients = User.objects.filter(id__in=recipient_ids, organization=organization)

        # Send notifications to each selected recipient
        for recipient in recipients:
            InboxNotification.objects.create(
                user=recipient,
                message=message_content,
                from_admin=True  # Mark as admin notification
            )

        django_messages.success(request, "Notification sent to selected users.")
        return redirect('admin_notify', org_id=org_id)

    users = User.objects.filter(organization=organization)  # Get users in the same organization
    return render(request, 'admin/notify_users.html', {'users': users, 'org_id': org_id})


def extract_pdf_fields(file_path):
    """Extract form fields from a PDF file."""
    reader = PdfReader(file_path)
    fields = []
    
    if '/AcroForm' in reader.trailer['/Root']:
        form_fields = reader.trailer['/Root']['/AcroForm']['/Fields']
        for field in form_fields:
            field_obj = field.getObject()
            field_name = field_obj.get('/T')  # Get the field name (identifier)
            fields.append(field_name)
    
    return fields

@login_required
@user_passes_test(lambda u: u.is_superuser)
def create_form(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    users = User.objects.filter(organization=organization)
    message = None

    if request.method == 'POST':
        # Get form data
        form_name = request.POST.get('form_name')
        form_description = request.POST.get('form_description')
        user_selection = request.POST.get('user_selection')
        selected_users = request.POST.getlist('specific_users')
        form_file = request.FILES.get('form_file')

        # Save the form
        uploaded_form = AdminCreatedForm.objects.create(
            name=form_name,
            description=form_description,
            organization=organization,
            created_by=request.user
        )

        # Save the uploaded PDF/DOCX
        if form_file:
            fs = FileSystemStorage()
            filename = fs.save(form_file.name, form_file)
            pdf_template = PDFTemplate.objects.create(
                name=form_name,
                description=form_description,
                uploaded_pdf=filename,
                organization=organization,
                created_by=request.user
            )

            # Assign the form to users (either all users or specific users)
            if user_selection == 'all':
                assigned_users = users
            else:
                assigned_users = User.objects.filter(id__in=selected_users)

            for user in assigned_users:
                UserFilledForm.objects.create(
                    user=user,
                    form=uploaded_form,
                    file_path=pdf_template.uploaded_pdf.url
                )

            message = "Form successfully created and assigned to users."

    return render(request, 'admin/create_form.html', {
        'users': users,
        'org_id': org_id,
        'message': message  # Pass the success message to the template
    })

@login_required
@user_passes_test(lambda u: u.is_superuser)
def create_form_confirmation(request, org_id, form_id):
    form = AdminCreatedForm.objects.get(id=form_id, organization_id=org_id)
    form_fields = form.fields.all()

    # Prepare choices for multiple-choice fields
    for field in form_fields:
        if field.field_type == 'multiple_choice' and field.choices:
            # Split the choices into a list for multiple-choice fields
            field.split_choices = field.choices.split(',')
        else:
            field.split_choices = None  # No choices for non-multiple-choice fields

    return render(request, 'admin/create_form_confirmation.html', {
        'form': form,
        'form_fields': form_fields,
        'org_id': org_id
    })
@login_required
@user_passes_test(lambda u: u.is_superuser)
def map_pdf_fields(request, org_id, template_id):
    pdf_template = get_object_or_404(PDFTemplate, id=template_id, organization_id=org_id)

    # Get the URL of the uploaded PDF
    pdf_url = pdf_template.uploaded_pdf.url

    # Extract fields from the uploaded PDF (use extract_pdf_fields logic)
    extracted_fields = extract_pdf_fields(pdf_template.uploaded_pdf.path)

    if request.method == 'POST':
        editable_fields = request.POST.getlist('editable_fields[]')
        # Save the editable fields to the database or process them as needed

        return redirect('admin_dashboard')  # or wherever you want to redirect after saving

    return render(request, 'admin/map_pdf_fields.html', {
        'pdf_template': pdf_template,
        'pdf_url': pdf_url,
        'pdf_fields': extracted_fields,
        'org_id': org_id,
        'template_id': template_id,
    })

def display_pdf(request, pdf_template_id):
    pdf_template = get_object_or_404(PDFTemplate, id=pdf_template_id)
    file_path = pdf_template.uploaded_pdf.path

    try:
        response = FileResponse(open(file_path, 'rb'), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{pdf_template.name}.pdf"'
        return response
    except FileNotFoundError:
        raise Http404("PDF file not found")
    
@login_required
@user_passes_test(lambda u: u.is_superuser)
def save_pdf_field_mapping(request, org_id, template_id):
    pdf_template = get_object_or_404(PDFTemplate, id=template_id, organization_id=org_id)

    if request.method == 'POST':
        highlighted_fields = request.POST.get('highlighted_fields')
        if highlighted_fields:
            highlighted_fields = json.loads(highlighted_fields)  # Convert JSON back to Python objects

            # Save each highlighted field in the database
            for field in highlighted_fields:
                PDFFieldMapping.objects.create(
                    pdf_template=pdf_template,
                    x=field['x'],
                    y=field['y'],
                    width=field['width'],
                    height=field['height'],
                    is_editable=True  # Marking all highlighted fields as editable
                )

        return redirect('admin_dashboard', org_id=org_id)

    return redirect('admin_dashboard', org_id=org_id)



@user_passes_test(lambda u: u.is_superuser)
@login_required
def create_admin_form(request):
    if request.method == 'POST':
        form = AdminCreatedFormForm(request.POST)
        if form.is_valid():
            form_instance = form.save(commit=False)
            form_instance.created_by = request.user
            form_instance.organization = request.user.organization  # Associate with organization
            form_instance.save()
            return redirect('add_fields_to_form', form_id=form_instance.id)
    else:
        form = AdminCreatedFormForm()

    return render(request, 'admin/create_form.html', {'form': form})


@login_required
@user_passes_test(lambda u: u.is_superuser)
def add_fields_to_form(request, org_id, form_id):
    form_instance = get_object_or_404(AdminCreatedForm, id=form_id, organization_id=org_id, created_by=request.user)

    if request.method == 'POST':
        field_form = FormFieldForm(request.POST)
        if field_form.is_valid():
            field_instance = field_form.save(commit=False)
            field_instance.form = form_instance
            field_instance.save()
            return redirect('add_fields_to_form', org_id=org_id, form_id=form_id)

    field_form = FormFieldForm()

    return render(request, 'admin/add_fields_to_form.html', {
        'form_instance': form_instance,
        'field_form': field_form,
        'fields': form_instance.fields.all(),
        'org_id': org_id
    })

@login_required
@user_passes_test(lambda u: u.is_superuser)
def admin_signed_forms(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    
    # Include signed forms with a user from the organization or anonymous forms (user=None)
    signed_forms = SignedForm.objects.filter(
        Q(user__organization=organization) | Q(user__isnull=True)
    ).order_by('-is_high_importance', '-signed_date')

    return render(request, 'admin/signed_forms.html', {
        'signed_forms': signed_forms,
        'org_id': org_id,
        'MEDIA_URL': settings.MEDIA_URL
    })



@login_required
@user_passes_test(lambda u: u.is_superuser)
def review_signed_form(request, org_id, form_id):
    signed_form = get_object_or_404(SignedForm, id=form_id, user__organization_id=org_id)
    signed_form.reviewed = not signed_form.reviewed
    signed_form.save()
    return redirect('admin_signed_forms', org_id=org_id)

@login_required
@user_passes_test(lambda u: u.is_superuser)
def preview_form_pdf(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)

    if request.method == 'POST':
        # Collect form data
        form_name = request.POST.get('form_name', 'Untitled Form')
        form_description = request.POST.get('form_description', '')
        form_header = request.POST.get('form_header', '')
        form_subtitle = request.POST.get('form_subtitle', '')
        form_logo = request.FILES.get('form_logo', None)

        # Generate PDF
        buffer = BytesIO()
        pdf = SimpleDocTemplate(buffer, pagesize=letter)

        elements = []
        styles = getSampleStyleSheet()

        # Add logo if provided
        if form_logo:
            from reportlab.platypus import Image
            from django.core.files.storage import default_storage
            from django.conf import settings

            # Temporarily save the uploaded logo for embedding
            logo_path = default_storage.save(f"temp/{form_logo.name}", form_logo)
            logo_full_path = f"{settings.MEDIA_ROOT}/{logo_path}"
            img = Image(logo_full_path, 2 * inch, 1 * inch)  # Adjust size accordingly
            elements.append(img)

        # Add title
        if form_header:
            title_style = styles['Title']
            elements.append(Paragraph(form_header, title_style))
            elements.append(Spacer(1, 12))

        # Add subtitle
        if form_subtitle:
            subtitle_style = styles['Normal']
            elements.append(Paragraph(form_subtitle, subtitle_style))
            elements.append(Spacer(1, 12))

        # Add description
        if form_description:
            description_style = styles['BodyText']
            elements.append(Paragraph(form_description, description_style))
            elements.append(Spacer(1, 12))

        # Build the PDF
        pdf.build(elements)

        # Return the PDF as a response
        buffer.seek(0)
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="form_preview.pdf"'

        # Clean up temporary logo file if it exists
        if form_logo:
            default_storage.delete(logo_path)

        return response

    return HttpResponse(status=400)
@login_required
@user_passes_test(lambda u: u.is_superuser)
def upload_pdf_template(request):
    if request.method == 'POST':
        form = UploadPDFTemplateForm(request.POST, request.FILES)
        if form.is_valid():
            form_instance = form.save()
            pdf_path = form_instance.pdf_file.path  # Get the path to the uploaded PDF file

            # Extract fields from the PDF using a helper function
            fields = extract_pdf_fields(pdf_path)
            print(fields)  # For debugging purposes

            # If needed, associate the fields with a form (or save for later use)
            for field_name in fields:
                FormField.objects.create(
                    form=form_instance,  # Assuming this is an AdminCreatedForm instance
                    field_label=field_name,
                    field_type='text'  # You can change the field type based on the extracted data
                )

            return redirect('admin_dashboard')
    else:
        form = UploadPDFTemplateForm()

    return render(request, 'admin/upload_pdf_template.html', {'form': form})

