from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test, login_required
from .forms import ProjectForm, OpportunityForm, TrainingFolderForm, SF424FormForm, OtherPersonnelForm, BudgetPeriodForm, PerformanceSiteLocationForm, SubMiniStepForm, MiniStepForm, MiniStepFieldForm, CertificationForm, CustomUserCreationForm, AdminCreatedFormForm, FormField, FormFieldForm, UploadPDFTemplateForm, ProtocolCreationForm, ProtocolApprovalForm
from .models import ProtocolDesign, Opportunity, Project, SubmittedPackage, SF424Form, SF424Submission, OtherPersonnel, BudgetPeriod, PerformanceSiteLocation, FormPackage, PackageForm, SF424Field, Organization, PDFField, SubMiniStepField, MiniStep, SubMiniStep, MiniStepField, User, UserCertification, RFIDAssignment, Building, Room, TrainingFolder, Certification, Rack, ProtocolTemplate, ApprovalComment, SpeciesEntry, Attachment, Notification, Protocol, UserFilledForm, Animal, Cage, Experiment, UserAction, UserSignature, InboxNotification, SignedForm, AdminCreatedForm, Organization, PDFFieldMapping, Conversation, Message
from django.db.models import Q, F, Avg, Max, Min, Count, Prefetch
from django.db.models.signals import post_save
from myapp.utils.pdf_field_mapping import field_positions  # Import the field mapping
import boto3
from django.template.loader import render_to_string
from weasyprint import HTML, CSS
import tempfile
from botocore.exceptions import NoCredentialsError, PartialCredentialsError
from django.dispatch import receiver
import io
from reportlab.pdfgen import canvas
from myapp.utils.pdf_processing import generate_filled_pdf
import pdfkit
from django.core.files.storage import default_storage
import pymupdf as fitz
from django.forms import inlineformset_factory
from django.forms import formset_factory
from django.utils import timezone
from django.utils.html import escape
from django.db import IntegrityError, transaction, models
from django.views.decorators.http import require_POST
from django.http import JsonResponse, FileResponse, Http404, HttpResponseNotFound, HttpRequest, HttpResponseRedirect
import xml.etree.ElementTree as ET
from django.http import HttpResponseForbidden
from django.conf import settings
import requests
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import datetime
from django.urls import reverse
from django.contrib import messages 
from .pdf_utils import extract_pdf_fields, convert_pdf_to_images
import logging

from adobe.pdfservices.operation.execution_context import ExecutionContext
from adobe.pdfservices.operation.auth.credentials import Credentials
from adobe.pdfservices.operation.io.file_ref import FileRef
import pymupdf
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
from PyPDF2 import PdfReader, PdfWriter, PdfMerger
from reportlab.lib.pagesizes import letter  # To set PDF page size
from reportlab.lib.styles import getSampleStyleSheet  # For setting up basic text styles in PDF
from reportlab.lib.units import inch  # To handle unit conversion (e.g., inches for image scaling)
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image  # For PDF generation (mainly layout and content elements)
import json


logger = logging.getLogger(__name__)  # Set up a logger for error tracking
def is_admin_or_principal(user):
    return user.role in ['admin', 'principal_admin']

def is_principal_admin(user):
    return user.role == 'principal_admin'

def is_admins(user):
    return user.role in ['admin', 'principal_admin', 'approval_member']
def admin_login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)

            # Redirect based on role
            if user.role in ['admin', 'principal_admin']:
                return redirect('admin_dashboard', org_id=user.organization.id)
            else:
                # Redirect regular users
                return redirect('dashboard', org_id=user.organization.id)
        else:
            return render(request, 'admin/admin_login.html', {'error': 'Invalid username or password.'})

    return render(request, 'admin/admin_login.html')

@login_required
@user_passes_test(is_admin_or_principal)
def admin_actions_view(request, org_id):
    if request.user.role == 'principal_admin':
        actions = UserAction.objects.filter(
            user__organization_id=org_id,
            user__role='admin'
        ).order_by('-timestamp')
    elif request.user.role == 'admin':
        actions = UserAction.objects.filter(
            user__organization_id=org_id,
            user__role='user'
        ).order_by('-timestamp')
    else:
        return HttpResponseForbidden("You do not have permission to view these actions.")

    # Add the is_clickable flag for actions with additional details
    for action in actions:
        action.is_clickable = action.action_type in ['Measurement', 'DetailedActionType']

    context = {
        'admin_actions': actions,
        'org_id': org_id,
    }
    return render(request, 'admin/admin_actions.html', context)


@login_required
@user_passes_test(is_admin_or_principal)
def admin_vivarium_view(request, org_id):
    """
    Admin Vivarium View:
    - Display Buildings, Rooms, Racks, and Cages in a structured format.
    - Ensure hierarchy is passed correctly to the frontend.
    """
    organization = get_object_or_404(Organization, id=org_id)
    buildings_queryset = Building.objects.filter(organization=organization).prefetch_related('rooms__racks__cages__animals')

    # Construct the hierarchical structure
    buildings = {}
    for building in buildings_queryset:
        rooms_dict = {}
        for room in building.rooms.all():
            racks_dict = {}
            for rack in room.racks.all():
                cages = list(rack.cages.all())  # Get all cages in this rack
                racks_dict[rack.name] = cages  # Add cages under this rack
            
            rooms_dict[room.name] = {
                "racks": racks_dict
            }

        buildings[building.name] = {
            "rooms": rooms_dict
        }

    return render(request, 'admin/admin_vivarium.html', {
        'org_id': org_id,
        'sidebar_color': organization.sidebar_color,  # Send sidebar color to template
        'buildings': buildings
    })



@csrf_exempt
@login_required
@user_passes_test(is_admin_or_principal)
def vivarium_cage_creation_view(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            cages_data = data.get('cages', [])

            with transaction.atomic():
                for cage_info in cages_data:
                    assigned_user_ids = cage_info.get('assigned_user_ids', [])
                    assigned_users = User.objects.filter(id__in=assigned_user_ids, organization=organization)

                    # ✅ Fetch or Create Building
                    building_name = cage_info['housing_location'].strip()
                    building, _ = Building.objects.get_or_create(name=building_name, organization=organization)

                    # ✅ Fetch or Create Room within the Building
                    room_number = cage_info['room_number'].strip()
                    room, _ = Room.objects.get_or_create(name=room_number, building=building)

                    # ✅ Fetch or Create Rack within the Room
                    rack_number = cage_info['rack_number'].strip()
                    rack, _ = Rack.objects.get_or_create(name=rack_number, room=room)

                    # ✅ Create Cage assigned to Rack
                    cage = Cage.objects.create(
                        name=cage_info['name'],
                        capacity=cage_info['population'],
                        rack=rack,  # Correctly linking the cage to a rack
                        organization=organization
                    )
                    cage.assigned_users.set(assigned_users)

                    # ✅ Fetch Last Animal Index
                    last_index = Animal.objects.filter(organization=organization).aggregate(
                        Max('animal_index')
                    )['animal_index__max'] or 0

                    # ✅ Create Animals for the Cage
                    for animal_info in cage_info['animals']:
                        last_index += 1
                        date_of_birth = datetime.strptime(animal_info['date_of_birth'], '%Y-%m-%d').date()

                        species_name = animal_info.get('species', "").strip()

                        animal = Animal.objects.create(
                            cage=cage,
                            organization=organization,
                            rfid_tag=animal_info['rfid_tag'],
                            sex=animal_info['sex'],
                            date_of_birth=date_of_birth,
                            species=species_name,
                            strain=animal_info.get('strain', ""),
                            animal_index=last_index,
                            tracking_date=timezone.now().date()
                        )

                        # ✅ Assign RFID to the Animal
                        RFIDAssignment.objects.create(
                            rfid=animal.rfid_tag,
                            animal=animal,
                            experiment=animal.experiment,
                            cage_number=cage.name,
                            removed=False
                        )

            return JsonResponse({'success': True, 'message': 'Cages and animals created successfully with housing details.'})

        except Exception as e:
            logger.error(f"An error occurred: {e}")
            return JsonResponse({'success': False, 'message': f'Failed to create cages and animals: {str(e)}'}, status=500)

    return render(request, 'admin/admin_cage_creation.html', {'org_id': org_id})
@login_required
@user_passes_test(is_admin_or_principal)
def admin_buildings_view(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    buildings = Building.objects.filter(organization=organization).prefetch_related('rooms__racks')

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            building_name = data.get('building_name')
            room_name = data.get('room_name')
            rack_name = data.get('rack_name')

            if building_name:
                building = Building.objects.create(name=building_name, organization=organization)
            else:
                building = get_object_or_404(Building, id=data.get('building_id'), organization=organization)

            if room_name:
                room = Room.objects.create(name=room_name, building=building)
            else:
                room = get_object_or_404(Room, id=data.get('room_id'), building=building)

            if rack_name:
                Rack.objects.create(name=rack_name, room=room)

            return JsonResponse({'success': True, 'message': 'Building, Room, or Rack added successfully'})
        except Exception as e:
            logger.error(f"An error occurred: {e}")
            return JsonResponse({'success': False, 'message': str(e)}, status=500)

    return render(request, 'admin_buildings.html', {'org_id': org_id, 'buildings': buildings})
@login_required
@user_passes_test(is_admin_or_principal)
def admin_building_management_view(request, org_id):
    """
    Admin view to manage Buildings, Rooms, and Racks.
    Ensures buildings, rooms, and racks are correctly passed to the template.
    """
    organization = get_object_or_404(Organization, id=org_id)
    
    # Fetch all buildings related to the organization
    buildings = Building.objects.filter(organization=organization).prefetch_related('rooms__racks')

    # Organize rooms and racks in a dictionary structure
    buildings_dict = {}
    for building in buildings:
        buildings_dict[building.name] = {
            room.name: [rack.name for rack in room.racks.all()] for room in building.rooms.all()
        }

    return render(request, 'admin/admin_building_management.html', {
        'organization': organization,
        'org_id': org_id,
        'buildings': buildings_dict,  # Send the properly structured buildings data
    })

@csrf_exempt
@login_required
@user_passes_test(is_admin_or_principal)
def create_building(request, org_id):
    if request.method == 'POST':
        try:
            logger.info(f"Received request to create building for org_id: {org_id}")  # ✅ Debugging

            data = json.loads(request.body)
            building_name = data.get("name")
            rooms_data = data.get("rooms", [])

            logger.info(f"Building Name: {building_name}, Rooms: {rooms_data}")  # ✅ Debugging

            # Retrieve organization
            organization = get_object_or_404(Organization, id=org_id)

            # ✅ Create the Building
            building = Building.objects.create(name=building_name, organization=organization)

            # ✅ Create the Rooms and Racks
            for room_info in rooms_data:
                room_name = room_info.get("name")
                racks = room_info.get("racks", [])

                room = Room.objects.create(name=room_name, building=building)

                # Create Racks under the Room
                for rack_name in racks:
                    Rack.objects.create(name=rack_name, room=room)

            logger.info(f"Successfully created building: {building_name} for org_id: {org_id}")

            return JsonResponse({"success": True, "message": "Building created successfully!"})

        except Exception as e:
            logger.error(f"Error creating building for org_id {org_id}: {str(e)}")
            return JsonResponse({"success": False, "message": str(e)}, status=500)

    return JsonResponse({"success": False, "message": "Invalid request method."}, status=400)

@csrf_exempt
@login_required
@user_passes_test(is_admin_or_principal)
def create_room_view(request, org_id):
    """
    Adds a new room under a building in the organization's JSON field.
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        building_name = data.get('building_name')
        room_name = data.get('name')

        if not building_name or not room_name:
            return JsonResponse({'success': False, 'message': 'Both building and room name are required.'})

        organization = get_object_or_404(Organization, id=org_id)

        if building_name not in organization.buildings:
            return JsonResponse({'success': False, 'message': 'Building does not exist.'})

        # Add room if it doesn't exist
        if room_name not in organization.rooms:
            organization.rooms[room_name] = []
            organization.buildings[building_name].append(room_name)
            organization.save()

        return JsonResponse({'success': True, 'message': 'Room added successfully.', 'rooms': organization.rooms})

    return JsonResponse({'success': False, 'message': 'Invalid request method.'})

@csrf_exempt
@login_required
@user_passes_test(is_admin_or_principal)
def create_rack_view(request, org_id):
    """
    Adds a new rack under a room in the organization's JSON field.
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        room_name = data.get('room_name')
        rack_name = data.get('name')

        if not room_name or not rack_name:
            return JsonResponse({'success': False, 'message': 'Both room and rack name are required.'})

        organization = get_object_or_404(Organization, id=org_id)

        if room_name not in organization.rooms:
            return JsonResponse({'success': False, 'message': 'Room does not exist.'})

        # Add rack if it doesn't exist
        if rack_name not in organization.racks:
            organization.racks[rack_name] = []
            organization.rooms[room_name].append(rack_name)
            organization.save()

        return JsonResponse({'success': True, 'message': 'Rack added successfully.', 'racks': organization.racks})

    return JsonResponse({'success': False, 'message': 'Invalid request method.'})

@login_required
@user_passes_test(is_admin_or_principal)
def manage_vivarium_permissions(request, org_id):
    cages = Cage.objects.filter(organization_id=org_id)

    if request.method == 'POST':
        cage_id = request.POST.get('cage_id')
        user_ids = request.POST.getlist('allowed_users')

        cage = get_object_or_404(Cage, id=cage_id, organization_id=org_id)
        allowed_users = User.objects.filter(id__in=user_ids, organization_id=org_id)
        cage.allowed_users.set(allowed_users)

        return JsonResponse({'success': True, 'message': 'Permissions updated successfully.'})

    users = User.objects.filter(organization_id=org_id).exclude(role__in=['admin', 'principal_admin'])
    return render(request, 'admin/manage_permissions.html', {
        'cages': cages,
        'users': users,
        'org_id': org_id
    })

@login_required
def manage_mini_step_fields(request, step_id):
    mini_step = get_object_or_404(MiniStep, id=step_id)
    dropdown_fields = MiniStepField.objects.filter(mini_step=mini_step, field_type="dropdown")
    fields = MiniStepField.objects.filter(mini_step=mini_step)

    if request.method == "POST":
        form_data = request.POST
        field_label = form_data.get("field_label", "").strip()
        field_type = form_data.get("field_type", "").strip()
        is_required = form_data.get("is_required", "off") == "on"
        options = form_data.get("options", "").strip() if field_type == "dropdown" else ""
        column_names = form_data.get("column_names", "").strip() if field_type == "table" else ""
        fixed_rows = form_data.get("fixed_rows") if field_type == "table" and form_data.get("fixed_rows") else None
        allow_dynamic_rows = form_data.get("allow_dynamic_rows", "off") == "on" if field_type == "table" else False
        parent_field_id = form_data.get("parent_field", None)
        trigger_option = form_data.get("trigger_option", "").strip()

        # Validate required fields
        if not field_label or not field_type:
            return JsonResponse({"status": "error", "errors": {"label": ["This field is required."]}}, status=400)

        # Create new field
        new_field = MiniStepField(
            mini_step=mini_step,
            label=field_label,
            field_type=field_type,
            is_required=is_required,
            options=options,
            column_names=column_names,
            fixed_rows=fixed_rows if fixed_rows else None,
            allow_dynamic_rows=allow_dynamic_rows,
        )

        # Set parent dropdown field if applicable
        if parent_field_id:
            try:
                new_field.parent_field = MiniStepField.objects.get(id=parent_field_id, mini_step=mini_step, field_type="dropdown")
                new_field.trigger_option = trigger_option
            except MiniStepField.DoesNotExist:
                return JsonResponse({"status": "error", "message": "Invalid parent field selected"}, status=400)

        new_field.save()
        return JsonResponse({"status": "success", "message": "Field added successfully."})

    return render(request, "admin/manage_mini_step_fields.html", {
        "fields": fields,
        "mini_step": mini_step,
        "dropdown_fields": dropdown_fields,
    })
@login_required
def manage_mini_sub_steps(request, mini_step_id):
    mini_step = get_object_or_404(MiniStep, id=mini_step_id)
    sub_mini_steps = SubMiniStep.objects.filter(parent_mini_step=mini_step).order_by("order")

    if request.method == "POST":
        try:
            data = json.loads(request.body)
            form = SubMiniStepForm(data)

            if form.is_valid():
                sub_mini_step = form.save(commit=False)
                sub_mini_step.parent_mini_step = mini_step
                sub_mini_step.save()  # ✅ Ensure it's saved before sending response

                return JsonResponse({
                    "status": "success",
                    "message": "Sub Mini Step added successfully!",
                    "sub_step_id": sub_mini_step.id  # ✅ Now has a valid ID
                })

            return JsonResponse({"status": "error", "errors": form.errors}, status=400)

        except json.JSONDecodeError:
            return JsonResponse({"status": "error", "message": "Invalid JSON format."}, status=400)

    return render(request, "admin/manage_mini_sub_steps.html", {"sub_mini_steps": sub_mini_steps, "mini_step": mini_step})

@login_required
def manage_mini_sub_step_fields(request, sub_step_id):
    """
    Manage Fields for a Sub-Mini Step.
    """
    sub_mini_step = get_object_or_404(SubMiniStep, id=sub_step_id)
    dropdown_fields = SubMiniStepField.objects.filter(sub_mini_step=sub_mini_step, field_type="dropdown")
    fields = SubMiniStepField.objects.filter(sub_mini_step=sub_mini_step)

    if request.method == "POST":
        form_data = request.POST
        field_label = form_data.get("field_label", "").strip()
        field_type = form_data.get("field_type", "").strip()
        is_required = form_data.get("is_required", "off") == "on"
        options = form_data.get("options", "").strip() if field_type == "dropdown" else ""
        column_names = form_data.get("column_names", "").strip() if field_type == "table" else ""
        fixed_rows = form_data.get("fixed_rows") if field_type == "table" and form_data.get("fixed_rows") else None
        allow_dynamic_rows = form_data.get("allow_dynamic_rows", "off") == "on" if field_type == "table" else False
        parent_field_id = form_data.get("parent_field", None)
        trigger_option = form_data.get("trigger_option", "").strip()

        # Validate required fields
        if not field_label or not field_type:
            return JsonResponse({"status": "error", "errors": {"label": ["This field is required."]}}, status=400)

        # Create new field
        new_field = SubMiniStepField(
            sub_mini_step=sub_mini_step,
            label=field_label,
            field_type=field_type,
            is_required=is_required,
            options=options,
            column_names=column_names,
            fixed_rows=fixed_rows if fixed_rows else None,
            allow_dynamic_rows=allow_dynamic_rows,
        )

        # Set parent dropdown field if applicable
        if parent_field_id:
            try:
                new_field.parent_field = SubMiniStepField.objects.get(id=parent_field_id, sub_mini_step=sub_mini_step, field_type="dropdown")
                new_field.trigger_option = trigger_option
            except SubMiniStepField.DoesNotExist:
                return JsonResponse({"status": "error", "message": "Invalid parent field selected"}, status=400)

        new_field.save()
        return JsonResponse({"status": "success", "message": "Field added successfully."})

    return render(request, "admin/manage_mini_sub_step_fields.html", {
        "fields": fields,
        "sub_mini_step": sub_mini_step,
        "dropdown_fields": dropdown_fields,
    })

@login_required
def delete_mini_step_field(request, field_id):
    field = get_object_or_404(MiniStepField, id=field_id)
    step_id = field.mini_step.id
    field.delete()
    
    return JsonResponse({"status": "success", "message": "Field deleted successfully."})

@login_required
def add_mini_step(request):
    """Allows admins to add a new Mini Step"""
    organization = request.user.organization

    if request.method == "POST":
        form = MiniStepForm(request.POST)
        if form.is_valid():
            mini_step = form.save(commit=False)
            mini_step.organization = organization
            mini_step.save()
            return redirect('manage_mini_steps')

    else:
        form = MiniStepForm()

    return render(request, "admin/add_mini_step.html", {"form": form})

@login_required
def delete_mini_step_field(request, field_id):
    field = get_object_or_404(MiniStepField, id=field_id)
    step_id = field.mini_step.id
    field.delete()
    return redirect('manage_mini_step_fields', step_id=step_id)

@login_required
def manage_mini_steps(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    mini_steps = MiniStep.objects.filter(organization=organization).order_by("order")

    if request.method == "POST":
        data = json.loads(request.body)
        form = MiniStepForm(data)
        if form.is_valid():
            mini_step = form.save(commit=False)
            mini_step.organization = organization
            mini_step.save()
            return JsonResponse({"status": "success", "step_id": mini_step.id})
        return JsonResponse({"status": "error", "errors": form.errors}, status=400)

    return render(request, "admin/manage_mini_steps.html", {"mini_steps": mini_steps})
@login_required
@csrf_exempt
def manage_sub_mini_steps(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)

    if request.method == "POST":
        try:
            data = json.loads(request.body)
            parent_step = get_object_or_404(MiniStep, id=data["parent_mini_step"], organization=organization)
            trigger_field = get_object_or_404(MiniStepField, id=data["trigger_field"])

            sub_step = SubMiniStep(
                parent_mini_step=parent_step,
                name=data["name"],
                trigger_field=trigger_field,
                trigger_value=data["trigger_value"]
            )
            sub_step.save()

            return JsonResponse({"status": "success", "message": "Sub-mini step added successfully!", "step_id": sub_step.id})

        except json.JSONDecodeError:
            return JsonResponse({"status": "error", "message": "Invalid JSON format."}, status=400)
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)

    return JsonResponse({"status": "error", "message": "Invalid request method."}, status=405)

@login_required
def delete_mini_step(request, org_id, step_id):
    mini_step = get_object_or_404(MiniStep, id=step_id, organization_id=org_id)
    mini_step.delete()
    return JsonResponse({"status": "success", "message": "Mini step deleted successfully."})

@login_required
def edit_mini_step(request, step_id):
    mini_step = get_object_or_404(MiniStep, id=step_id)

    if request.method == "POST":
        form = MiniStepForm(request.POST, instance=mini_step)
        if form.is_valid():
            form.save()
            return redirect('manage_mini_steps')

    else:
        form = MiniStepForm(instance=mini_step)

    return render(request, "admin/edit_mini_step.html", {"form": form, "mini_step": mini_step})

@login_required
@user_passes_test(is_principal_admin)
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



@login_required
@user_passes_test(is_admins)
def admin_dashboard(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    user = request.user
    default_form = PDFTemplate.objects.filter(organization=organization).first()
    default_form_id = default_form.id if default_form else None

    context = {
        'org_id': org_id,
        'user': user,
    }
    return render(request, 'admin/admin_dashboard.html', {'org_id': org_id})
@user_passes_test(lambda u: u.role == 'admin' or u.role == 'principal_admin')
def create_user(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.organization = organization
            user.save()
            return redirect('admin_user_list', org_id=org_id)
    else:
        form = CustomUserCreationForm()

    return render(request, 'admin/create_user.html', {'form': form, 'organization': organization})

# Check if user is Admin, Researcher, or Officer (for protocol creation)
def can_create_protocol(user):
    return user.role in ['admin', 'principal_admin']

# Check if user is Approval Member or Principal Admin (for approval)
def can_approve_protocol(user):
    return user.role in ['approval_member', 'principal_admin']
@login_required
@user_passes_test(is_principal_admin)
def protocol_design_view(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    
    protocol_design = ProtocolDesign.objects.filter(organization=organization).first()
    
    # Ensure fields are properly serialized as JSON
    if protocol_design and protocol_design.fields:
        if isinstance(protocol_design.fields, str):  
            saved_fields = protocol_design.fields  # Already JSON string
        elif isinstance(protocol_design.fields, list):  
            saved_fields = json.dumps(protocol_design.fields)  # Convert list to JSON string
        else:
            saved_fields = "[]"  # Default to empty list
    else:
        saved_fields = "[]"

    return render(request, "admin/protocol_design.html", {
        "saved_fields": saved_fields,
        "org_id": org_id
    })
@login_required
@csrf_exempt
def save_protocol_info(request, org_id, protocol_id):
    """
    Saves mini step data and updates triggered sub-steps.
    """
    protocol = get_object_or_404(Protocol, id=protocol_id, organization_id=org_id)

    if request.method == "POST":
        try:
            data = json.loads(request.body)
            completed_step = data.get("completed_step", "").strip()

            if completed_step.startswith("mini_step_"):
                step_id = int(completed_step.split("_")[-1])
                step_key = f"mini_step_{step_id}"

                # ✅ Ensure step key exists in 'answers'
                if step_key not in protocol.answers:
                    protocol.answers[step_key] = {}

                for field_id, value in data.items():
                    if field_id.startswith("field_"):
                        protocol.answers[step_key][field_id] = value

                        # ✅ Check if this triggers a sub-step
                        triggered_sub_steps = SubMiniStep.objects.filter(
                            trigger_field__id=field_id.replace("field_", ""), 
                            trigger_value=value
                        ).values_list('id', flat=True)

                        for sub_step_id in triggered_sub_steps:
                            if f"sub_mini_step_{sub_step_id}" not in protocol.triggered_sub_steps:
                                protocol.triggered_sub_steps.append(f"sub_mini_step_{sub_step_id}")

                protocol.mini_steps_completed[step_key] = True  # ✅ Mark step as completed
                protocol.save()
                return JsonResponse({"status": "success", "message": "Mini-step saved successfully."})

            return JsonResponse({"status": "error", "message": "Invalid mini-step"}, status=400)

        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)

@login_required
@csrf_exempt
def save_protocol_design(request, org_id):
    """
    Saves the dynamically created Protocol Uses questions to the database.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            fields = data.get("fields", [])

            organization = get_object_or_404(Organization, id=org_id)

            # Save the Protocol Uses fields
            protocol_design, created = ProtocolDesign.objects.update_or_create(
                organization=organization,
                defaults={"fields": json.dumps(fields)}
            )

            logger.info(f"Saved Protocol Design Fields: {fields}")  # Debugging

            return JsonResponse({"success": True, "message": "Protocol Design Saved Successfully!"})

        except Exception as e:
            logger.error(f"Error saving Protocol Design: {e}")
            return JsonResponse({"success": False, "message": str(e)}, status=500)

    return JsonResponse({"success": False, "message": "Invalid request method"}, status=400)

@login_required
def get_mini_step_fields(request, mini_step_id):
    mini_step = get_object_or_404(MiniStep, id=mini_step_id)
    fields = MiniStepField.objects.filter(mini_step=mini_step).values("id", "label", "field_type")

    return JsonResponse({"fields": list(fields)})

@login_required
def get_protocol_design(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)

    protocol_design = ProtocolDesign.objects.filter(organization=organization).first()
    
    if protocol_design:
        try:
            fields_data = json.loads(protocol_design.fields)  # Convert from JSON
        except json.JSONDecodeError:
            fields_data = []

        return JsonResponse({"success": True, "fields": fields_data})
    
    return JsonResponse({"success": False, "message": "No protocol design found."})

@login_required
@user_passes_test(can_create_protocol)
def protocol_creation_view(request, org_id):
    if request.method == 'POST':
        form = ProtocolCreationForm(request.POST, request.FILES)
        if form.is_valid():
            protocol = form.save(commit=False)
            protocol.submitted_by = request.user
            protocol.save()
            messages.success(request, "Protocol submitted for approval.")
            return redirect('create_protocol', org_id=org_id)
    else:
        form = ProtocolCreationForm()
    
    return render(request, 'admin/create_protocol.html', {'form': form, 'org_id': org_id})

def start_protocol_process(request, org_id):
    """
    Ensures that the user is redirected to a protocol.
    If a draft protocol exists, use it. Otherwise, create a new one.
    """
    # Check if the user has an existing draft protocol
    existing_protocol = Protocol.objects.filter(
        organization_id=org_id, submitted_by=request.user, status="Draft"
    ).order_by('-created_at').first()  # FIXED: Replaced created_by with submitted_by

    if existing_protocol:
        protocol_id = existing_protocol.id
    else:
        # Create a new protocol draft if none exists
        new_protocol = Protocol.objects.create(
            organization_id=org_id,
            submitted_by=request.user,  # FIXED: Changed to submitted_by
            status="Draft",
            steps_completed={}
        )
        protocol_id = new_protocol.id
        messages.success(request, "New protocol created. Proceed with personnel step.")

    # Redirect to personnel step
    return redirect('protocol_personnel', org_id=org_id, protocol_id=protocol_id)

# Protocol Approval View
@login_required
@user_passes_test(can_approve_protocol)
def protocol_approval_view(request, org_id):
    pending_protocols = Protocol.objects.filter(approval_status='pending')

    if request.method == 'POST':
        protocol_id = request.POST.get('protocol_id')
        action = request.POST.get('approval_status')

        protocol = get_object_or_404(Protocol, id=protocol_id)

        protocol.approval_status = action
        protocol.reviewed_by = request.user
        protocol.reviewed_at = timezone.now() 
        protocol.save()

        messages.success(request, f"Protocol {protocol.title} marked as {action}.")
        return redirect('approve_protocols', org_id=org_id)

    return render(request, 'admin/approve_protocols.html', {'pending_protocols': pending_protocols, 'org_id': org_id})


@login_required
@user_passes_test(can_approve_protocol)
def approve_protocols(request, org_id):
    """ View to list all pending protocols for approval members. """
    pending_protocols = Protocol.objects.filter(status="Pending Approval", organization_id=org_id)

    if request.method == "POST":
        protocol_id = request.POST.get("protocol_id")
        approval_status = request.POST.get("approval_status")
        comment = request.POST.get("approval_comment", "").strip()

        protocol = get_object_or_404(Protocol, id=protocol_id, organization_id=org_id)

        # ✅ Save Approval Decision
        if approval_status in ["approved", "rejected"]:
            protocol.status = "Approved" if approval_status == "approved" else "Rejected"
            protocol.reviewed_by = request.user
            protocol.reviewed_at = now()
            protocol.save()

            # ✅ Store Approval Comment
            ApprovalComment.objects.create(
                protocol=protocol,
                reviewer=request.user,
                comment=comment,
                status=protocol.status
            )

        return redirect("approve_protocols", org_id=org_id)

    return render(request, "admin/approve_protocols.html", {
        "pending_protocols": pending_protocols,
        "org_id": org_id
    })

@login_required
@user_passes_test(can_approve_protocol)
def viewing_approve_protocols(request, org_id, protocol_id, section="personnel"):
    protocol = get_object_or_404(Protocol, id=protocol_id, organization_id=org_id)

    # Define section navigation and icons
    section_links = {
        "personnel": reverse("viewing_approve_protocols", args=[org_id, protocol_id, "personnel"]),
        "species": reverse("viewing_approve_protocols", args=[org_id, protocol_id, "species"]),
        "protocol_uses": reverse("viewing_approve_protocols", args=[org_id, protocol_id, "protocol_uses"]),
        "protocol_info": reverse("viewing_approve_protocols", args=[org_id, protocol_id, "protocol_info"]),
        "protocol_funding": reverse("viewing_approve_protocols", args=[org_id, protocol_id, "protocol_funding"]),
        "protocol_guidelines": reverse("viewing_approve_protocols", args=[org_id, protocol_id, "protocol_guidelines"]),
        "protocol_certifications": reverse("viewing_approve_protocols", args=[org_id, protocol_id, "protocol_certifications"]),
        "protocol_submission": reverse("viewing_approve_protocols", args=[org_id, protocol_id, "protocol_submission"]),
    }

    section_icons = {
        "personnel": "fas fa-user",
        "species": "fas fa-paw",
        "protocol_uses": "fas fa-vial",
        "protocol_info": "fas fa-info-circle",
        "protocol_funding": "fas fa-dollar-sign",
        "protocol_guidelines": "fas fa-book",
        "protocol_certifications": "fas fa-certificate",
        "protocol_submission": "fas fa-paper-plane",
    }


    section_titles = {
        "personnel": "Protocol Personnel Details",
        "species": "Species Details",
        "protocol_uses": "Protocol Uses",
        "protocol_info": "Protocol Information",
        "protocol_funding": "Funding Information",
        "protocol_guidelines": "Guidelines & Safety Measures",
        "protocol_certifications": "Certifications & Approvals",
        "protocol_submission": "Final Submission Review",
    }

    personnel_details = {
        "principal_investigator": protocol.principal_investigator,
        "co_principal_investigator": protocol.co_principal_investigator,
        "administrative_contact": protocol.administrative_contact,
        "submitters": protocol.additional_submitters.all(),
        "emergency_contacts": protocol.emergency_contacts.all(),
    }

    context = {
        "protocol": protocol,
        "org_id": org_id,
        "active_section": section,
        "section_links": section_links,
        "section_icons": section_icons,
        "section_titles": section_titles,
        "personnel_details": personnel_details,
    }

    return render(request, "admin/viewing_approve_protocols.html", context)

@login_required
def viewing_approve_protocol_species(request, org_id, protocol_id):
    protocol = get_object_or_404(Protocol, id=protocol_id, organization_id=org_id)

    # Fetch Species Details
    species_list = protocol.species_notes if protocol.species_notes else []  # Ensure data is in list format

    context = {
        "protocol": protocol,
        "org_id": org_id,
        "species_list": species_list,
    }
    
    return render(request, "admin/viewing_approve_protocol_species.html", context)

@login_required
def viewing_approve_protocol_uses(request, org_id, protocol_id):
    protocol = get_object_or_404(Protocol, id=protocol_id, organization_id=org_id)

    # Fetch all protocol uses-related data
    protocol_uses = {
        "collaboration": protocol.collaboration,
        "institution_name": protocol.institution_name,
        "biological_material": protocol.biological_material,
        "biological_material_data": protocol.biological_material_data if protocol.biological_material == "Yes" else [],
        "recombinant_dna": protocol.recombinant_dna,
        "ibc_rdna_protocol_number": protocol.ibc_rdna_protocol_number,
        "infectious_agents": protocol.infectious_agents,
        "ibc_biosafety_protocol_number": protocol.ibc_biosafety_protocol_number,
        "protocol_needed": protocol.protocol_needed,
        "protocol_verification_id": protocol.protocol_verification_id,
        "protocol_user_id": protocol.protocol_user_id,
        "toxic_agents": protocol.toxic_agents,
        "toxic_agents_data": protocol.toxic_agents_data if protocol.toxic_agents == "Yes" else [],
        "radiological_agents": protocol.radiological_agents,
        "isotope": protocol.isotope,
        "radiation_device": protocol.radiation_device,
        "field_study": protocol.field_study,
        "field_study_description": protocol.field_study_description if protocol.field_study == "Yes" else "",
    }

    # Fetch approval comments specific to this section
    comments = ApprovalComment.objects.filter(protocol=protocol, section="protocol_uses")

    context = {
        "protocol": protocol,
        "org_id": org_id,
        "protocol_uses": protocol_uses,
        "comments": comments,
    }

    return render(request, "admin/viewing_approve_protocol_uses.html", context)

@login_required
def viewing_approve_protocol_info(request, org_id, protocol_id):
    """View a submitted protocol's full info for approval."""
    protocol = get_object_or_404(Protocol, id=protocol_id, organization_id=org_id, is_draft=False)

    # Ensure only approval members can access
    if not request.user.groups.filter(name="Approval Members").exists():
        messages.error(request, "You do not have permission to review protocols.")
        return redirect("all_protocols", org_id=org_id)

    if request.method == "POST":
        action = request.POST.get("approval_status")
        comment_text = request.POST.get("approval_comment", "").strip()

        # Save approval/rejection decision
        if action in ["approved", "rejected"]:
            protocol.status = "Approved" if action == "approved" else "Rejected"
            protocol.reviewed_by = request.user
            protocol.reviewed_at = timezone.now()
            protocol.save()

            messages.success(request, f"Protocol {protocol.title} has been {protocol.status.lower()}.")

        # Save comment if provided
        if comment_text:
            section = request.POST.get("section", "general")
            ApprovalComment.objects.create(
                protocol=protocol,
                reviewer=request.user,
                section=section,
                comment=comment_text
            )

            messages.success(request, "Your comment has been added.")

        return redirect("viewing_approve_protocol_info", org_id=org_id, protocol_id=protocol.id)

    # Fetch existing comments
    comments = ApprovalComment.objects.filter(protocol=protocol)

    return render(request, "admin/viewing_approve_protocol_info.html", {
        "protocol": protocol,
        "comments": comments,
        "org_id": org_id,
    })


@login_required
def viewing_approve_protocol_funding(request, org_id, protocol_id):
    """View a submitted protocol's funding details for approval."""
    protocol = get_object_or_404(Protocol, id=protocol_id, organization_id=org_id, is_draft=False)

    # Ensure only approval members can access
    if not request.user.groups.filter(name="Approval Members").exists():
        messages.error(request, "You do not have permission to review protocols.")
        return redirect("all_protocols", org_id=org_id)

    if request.method == "POST":
        action = request.POST.get("approval_status")
        comment_text = request.POST.get("approval_comment", "").strip()

        # Save approval/rejection decision
        if action in ["approved", "rejected"]:
            protocol.status = "Approved" if action == "approved" else "Rejected"
            protocol.reviewed_by = request.user
            protocol.reviewed_at = timezone.now()
            protocol.save()

            messages.success(request, f"Protocol {protocol.title} has been {protocol.status.lower()}.")

        # Save comment if provided
        if comment_text:
            ApprovalComment.objects.create(
                protocol=protocol,
                reviewer=request.user,
                section="funding",
                comment=comment_text
            )

            messages.success(request, "Your comment has been added.")

        return redirect("viewing_approve_protocol_funding", org_id=org_id, protocol_id=protocol.id)

    # Fetch existing comments for funding
    comments = ApprovalComment.objects.filter(protocol=protocol, section="funding")

    return render(request, "admin/viewing_approve_protocol_funding.html", {
        "protocol": protocol,
        "comments": comments,
        "org_id": org_id,
    })

@login_required
def viewing_approve_protocol_guidelines(request, org_id, protocol_id):
    """View a submitted protocol's guidelines section for approval."""
    protocol = get_object_or_404(Protocol, id=protocol_id, organization_id=org_id, is_draft=False)

    # Ensure only approval members can access
    if not request.user.groups.filter(name="Approval Members").exists():
        messages.error(request, "You do not have permission to review protocols.")
        return redirect("all_protocols", org_id=org_id)

    if request.method == "POST":
        action = request.POST.get("approval_status")
        comment_text = request.POST.get("approval_comment", "").strip()

        # Save approval/rejection decision
        if action in ["approved", "rejected"]:
            protocol.status = "Approved" if action == "approved" else "Rejected"
            protocol.reviewed_by = request.user
            protocol.reviewed_at = timezone.now()
            protocol.save()

            messages.success(request, f"Protocol {protocol.title} has been {protocol.status.lower()}.")

        # Save comment if provided
        if comment_text:
            ApprovalComment.objects.create(
                protocol=protocol,
                reviewer=request.user,
                section="guidelines",
                comment=comment_text
            )

            messages.success(request, "Your comment has been added.")

        return redirect("viewing_approve_protocol_guidelines", org_id=org_id, protocol_id=protocol.id)

    # Fetch existing comments for guidelines
    comments = ApprovalComment.objects.filter(protocol=protocol, section="guidelines")

    return render(request, "admin/viewing_approve_protocol_guidelines.html", {
        "protocol": protocol,
        "comments": comments,
        "org_id": org_id,
    })

@login_required
def viewing_approve_protocol_certifications(request, org_id, protocol_id):
    """View a submitted protocol's certifications section for approval."""
    protocol = get_object_or_404(Protocol, id=protocol_id, organization_id=org_id, is_draft=False)

    # Ensure only approval members can access
    if not request.user.groups.filter(name="Approval Members").exists():
        messages.error(request, "You do not have permission to review protocols.")
        return redirect("all_protocols", org_id=org_id)

    if request.method == "POST":
        action = request.POST.get("approval_status")
        comment_text = request.POST.get("approval_comment", "").strip()

        # Save approval/rejection decision
        if action in ["approved", "rejected"]:
            protocol.status = "Approved" if action == "approved" else "Rejected"
            protocol.reviewed_by = request.user
            protocol.reviewed_at = timezone.now()
            protocol.save()

            messages.success(request, f"Protocol {protocol.title} has been {protocol.status.lower()}.")

        # Save comment if provided
        if comment_text:
            ApprovalComment.objects.create(
                protocol=protocol,
                reviewer=request.user,
                section="certifications",
                comment=comment_text
            )

            messages.success(request, "Your comment has been added.")

        return redirect("viewing_approve_protocol_certifications", org_id=org_id, protocol_id=protocol.id)

    # Fetch existing comments for certifications
    comments = ApprovalComment.objects.filter(protocol=protocol, section="certifications")

    return render(request, "admin/viewing_approve_protocol_certifications.html", {
        "protocol": protocol,
        "comments": comments,
        "org_id": org_id,
    })

@login_required
@user_passes_test(is_admin_or_principal)
def protocol_personnel(request, org_id, protocol_id):
    protocol = get_object_or_404(Protocol, id=protocol_id, organization_id=org_id)

    if request.method == "POST":
        try:
            data = json.loads(request.body)  # Parse JSON data from request
            
            # Update protocol fields
            protocol.title = data.get("protocol_title", protocol.title)

            # Fetch selected users
            pi_id = data.get("principal_investigator")
            co_pi_id = data.get("co_principal_investigator")
            admin_id = data.get("administrative_contact")
            submitter_ids = data.get("submitters", [])

            # Assign users to protocol if they exist
            protocol.principal_investigator = User.objects.filter(id=pi_id).first()
            protocol.co_principal_investigator = User.objects.filter(id=co_pi_id).first()
            protocol.administrative_contact = User.objects.filter(id=admin_id).first()

            # Assign additional submitters
            protocol.additional_submitters.set(User.objects.filter(id__in=submitter_ids))

            # Mark step as completed
            protocol.steps_completed["personnel"] = True
            protocol.save()

            return JsonResponse({"status": "success", "message": "Personnel details saved successfully."})

        except json.JSONDecodeError:
            return JsonResponse({"status": "error", "message": "Invalid JSON data."}, status=400)

    # Load existing personnel data
    context = {
        "protocol": protocol,
        "org_id": org_id,
        "step_number": 1,
        "current_step_name": "Personnel",
        "principal_investigator": protocol.principal_investigator,
        "co_principal_investigator": protocol.co_principal_investigator,
        "administrative_contact": protocol.administrative_contact,
        "additional_submitters": protocol.additional_submitters.all(),
    }
    return render(request, "admin/personnel.html", context)


@login_required
@csrf_exempt  # Remove this if CSRF is handled correctly
def protocol_species(request, org_id, protocol_id):
    protocol = get_object_or_404(Protocol, id=protocol_id, organization_id=org_id)

    # ✅ Fetch species list
    species_list = Animal.objects.filter(organization_id=org_id).values('species').annotate(count=Count('species')).order_by('species')

    # ✅ Fetch Buildings and associated Rooms
    buildings = Building.objects.filter(organization_id=org_id).prefetch_related('rooms')
    building_data = [
        {
            "name": building.name,
            "rooms": [room.name for room in building.rooms.all()]
        }
        for building in buildings
    ]

    # ✅ Load previously added species
    existing_species = json.loads(protocol.species_notes) if protocol.species_notes else []

    if request.method == 'POST':
        try:
            data = json.loads(request.body)  # ✅ Read JSON Data from Request

            new_species = {
                "species": data.get("species"),
                "scientific_name": data.get("scientific_name", ""),
                "sex_preference": data.get("sex_preference", "Either"),
                "weight_min": data.get("weight_min", None),
                "weight_max": data.get("weight_max", None),
                "weight_unit": data.get("weight_unit", "g"),
                "age_min": data.get("age_min", None),
                "age_max": data.get("age_max", None),
                "age_unit": data.get("age_unit", "days"),
                "strain": data.get("strain", ""),
                "housing_location": data.get("housing_location", ""),
                "room_number": data.get("room_number", ""),
                "number_needed": data.get("number_needed", 0),
            }

            existing_species.append(new_species)
            protocol.species_notes = json.dumps(existing_species)  # ✅ Save species list as JSON

            # ✅ Mark step as complete if at least one species exists
            protocol.steps_completed['species'] = bool(existing_species)
            protocol.save()

            return JsonResponse({'success': True, 'species': new_species, 'steps_completed': protocol.steps_completed})

        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)

    # ✅ Ensure species step is completed before redirecting
    if request.GET.get('next_step'):
        if existing_species:
            protocol.steps_completed['species'] = True
            protocol.save()
        return JsonResponse({'success': True, 'redirect_url': reverse('protocol_uses', args=[org_id, protocol_id])})

    return render(request, 'admin/protocol_species.html', {
        'protocol': protocol,
        'species_list': species_list,
        'existing_species': json.dumps(existing_species),
        'org_id': org_id,
        'step_number': 2,
        'current_step_name': "Protocol Species",
        'building_data': json.dumps(building_data),
    })




@login_required
def protocol_uses(request, org_id, protocol_id):
    organization = get_object_or_404(Organization, id=org_id)
    protocol = get_object_or_404(Protocol, id=protocol_id, organization=organization)

    protocol_design = ProtocolDesign.objects.filter(organization=organization).first()

    saved_fields = "[]"  
    saved_answers = protocol.uses_data if isinstance(protocol.uses_data, dict) else {}

    if protocol_design and protocol_design.fields:
        try:
            saved_fields = protocol_design.fields if isinstance(protocol_design.fields, str) else json.dumps(protocol_design.fields)
        except Exception as e:
            print(f"❌ Error parsing Protocol Design fields: {e}")
            saved_fields = "[]"

    # ✅ Handle form submission
    if request.method == "POST":
        try:
            raw_body = request.body.decode('utf-8').strip()
            if not raw_body:
                print("❌ Received Empty Request Body")
                return JsonResponse({"success": False, "message": "Empty request body"}, status=400)

            data = json.loads(raw_body)  # ✅ Properly load JSON
            answers = data.get("answers", {})

            protocol.uses_data = answers
            protocol.save()

            print("✅ Saved Protocol Answers:", answers)  # Debugging log
            return JsonResponse({"success": True})  # Success response

        except json.JSONDecodeError:
            print("❌ JSON Decode Error: Invalid JSON format received.")
            return JsonResponse({"success": False, "message": "Invalid JSON format"}, status=400)

        except Exception as e:
            print(f"❌ Error saving Protocol Answers: {e}")
            return JsonResponse({"success": False, "message": str(e)}, status=500)

    print("✅ Sending Protocol Uses Fields to Frontend:", saved_fields)
    print("✅ Sending Saved Answers to Frontend:", saved_answers)

    return render(request, "admin/protocol_uses.html", {
        "protocol": protocol,
        "saved_fields": saved_fields,  
        "saved_answers": json.dumps(saved_answers),  
        "org_id": org_id
    })
@csrf_exempt
def protocol_info(request, org_id, protocol_id):
    protocol = get_object_or_404(Protocol, id=protocol_id, organization_id=org_id)

    # ✅ Fetch Main Mini Steps and Sub Mini Steps
    mini_steps = MiniStep.objects.filter(organization_id=org_id).order_by("order")
    sub_mini_steps = SubMiniStep.objects.filter(parent_mini_step__organization_id=org_id).order_by("order")

    mini_steps_dict = {}

    # ✅ Include Main Mini Steps
    for step in mini_steps:
        mini_steps_dict[step.name] = f"mini_step_{step.id}"
        
        # ✅ Ensure triggered sub mini steps are included dynamically
        related_sub_steps = sub_mini_steps.filter(parent_mini_step=step)
        for sub_step in related_sub_steps:
            if str(sub_step.id) in protocol.triggered_sub_steps:
                mini_steps_dict[f"↳ {sub_step.name}"] = f"sub_mini_step_{sub_step.id}"

    active_mini_step = request.GET.get("mini_step", list(mini_steps_dict.values())[0]).strip()

    # ✅ Ensure 'answers' and 'triggered_sub_steps' exist in protocol
    if not isinstance(protocol.answers, dict):
        protocol.answers = {}

    if not isinstance(protocol.triggered_sub_steps, list):
        protocol.triggered_sub_steps = []

    if request.method == "POST":
        try:
            data = request.POST.dict()
            completed_step = data.get("completed_step", "").strip()

            if completed_step.startswith("mini_step_") or completed_step.startswith("sub_mini_step_"):
                step_id = int(completed_step.split("_")[-1])
                step_key = completed_step

                # ✅ Ensure step key exists in 'answers'
                if step_key not in protocol.answers:
                    protocol.answers[step_key] = {}

                # ✅ Determine if it's a Mini Step or Sub Mini Step
                if completed_step.startswith("sub_mini_step_"):
                    fields = SubMiniStepField.objects.filter(sub_mini_step_id=step_id)
                else:
                    fields = MiniStepField.objects.filter(mini_step_id=step_id)

                # ✅ Save all field responses
                for field in fields:
                    protocol.answers[step_key][f"field_{field.id}"] = data.get(f"field_{field.id}", "")

                protocol.mini_steps_completed[step_key] = True  # ✅ Mark step as completed

                # ✅ Check for dropdown selections that trigger sub mini steps
                for field_id, value in data.items():
                    if field_id.startswith("field_"):
                        triggered_sub_steps_qs = SubMiniStep.objects.filter(
                            trigger_field__id=field_id.replace("field_", ""),
                            trigger_value=value
                        ).values_list('id', flat=True)

                        for sub_step_id in triggered_sub_steps_qs:
                            if str(sub_step_id) not in protocol.triggered_sub_steps:
                                protocol.triggered_sub_steps.append(str(sub_step_id))

                protocol.save()

                return JsonResponse({"status": "success", "next_step": get_next_step(completed_step, protocol, mini_steps_dict)})

            return JsonResponse({"status": "error", "message": "Invalid step"}, status=400)

        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)

    # ✅ Determine the fields for the active step
    current_step_id = int(active_mini_step.split("_")[-1])
    if active_mini_step.startswith("sub_mini_step_"):
        fields = SubMiniStepField.objects.filter(sub_mini_step_id=current_step_id)
    else:
        fields = MiniStepField.objects.filter(mini_step_id=current_step_id)

    context = {
        "protocol": protocol,
        "org_id": org_id,
        "active_mini_step": active_mini_step,
        "mini_steps": mini_steps_dict,
        "mini_steps_json": json.dumps(list(mini_steps_dict.values())),
        "triggered_sub_steps": json.dumps(protocol.triggered_sub_steps),  # ✅ Pass to frontend
        "fields": fields,
        "field_dependencies": json.dumps({
            field.id: {"parent": field.parent_field.id, "trigger_option": field.trigger_option}
            for field in fields if field.parent_field
        }),
    }
    return render(request, "admin/protocol_info.html", context)

def get_next_step(current_step, protocol, mini_steps_dict):
    """
    Determines the next step based on triggered sub mini steps.
    """
    step_keys = list(mini_steps_dict.values())
    current_index = step_keys.index(current_step) if current_step in step_keys else -1

    if current_index != -1:
        # ✅ First, check for uncompleted sub mini steps
        for next_step in step_keys[current_index + 1:]:
            if next_step.startswith("sub_mini_step_") and next_step.split("_")[-1] in protocol.triggered_sub_steps:
                return next_step

        # ✅ If no sub mini steps left, move to next mini step
        for next_step in step_keys[current_index + 1:]:
            if next_step.startswith("mini_step_"):
                return next_step

    return None

@login_required
@csrf_exempt
def check_sub_mini_step(request, field_id, selected_value):
    """
    Fetch sub mini steps triggered by a dropdown value in a mini step.
    """
    try:
        selected_value = selected_value.strip()  # ✅ Remove extra spaces
        sub_steps = SubMiniStep.objects.filter(trigger_field__id=field_id, trigger_value=selected_value)

        if sub_steps.exists():
            return JsonResponse({"triggered": True, "sub_step_ids": [step.id for step in sub_steps]})

        return JsonResponse({"triggered": False})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)
    

def protocol_funding(request, org_id, protocol_id):
    protocol = get_object_or_404(Protocol, id=protocol_id, organization_id=org_id)

    if request.method == 'POST':
        protocol.funding_source = request.POST.get('funding_source', '')
        protocol.grant_number = request.POST.get('grant_number', '')
        protocol.funding_amount = request.POST.get('funding_amount', '')
        protocol.funding_duration = request.POST.get('funding_duration', '')
        protocol.ethical_restrictions = request.POST.get('ethical_restrictions', '')

        # Mark this step as completed if the required field is filled
        if protocol.funding_source:
            protocol.steps_completed['protocol_funding'] = True
        else:
            protocol.steps_completed['protocol_funding'] = False

        protocol.save()

        messages.success(request, "Protocol Funding details saved successfully.")
        return redirect('protocol_guidelines', org_id=org_id, protocol_id=protocol_id)  # Redirect to next step

    context = {
        'protocol': protocol,
        'org_id': org_id,
        'step_number': 5,
        'current_step_name': "Protocol Funding",
    }
    return render(request, 'admin/protocol_funding.html', context)


def protocol_guidelines(request, org_id, protocol_id):
    protocol = get_object_or_404(Protocol, id=protocol_id, organization_id=org_id)

    if request.method == 'POST':
        protocol.compliance_guidelines = request.POST.get('compliance_guidelines', '')
        protocol.safety_measures = request.POST.get('safety_measures', '')
        protocol.ethical_considerations = request.POST.get('ethical_considerations', '')
        protocol.special_approvals = request.POST.get('special_approvals', '')

        # Mark this step as completed if the required field is filled
        if protocol.compliance_guidelines:
            protocol.steps_completed['protocol_guidelines'] = True
        else:
            protocol.steps_completed['protocol_guidelines'] = False

        protocol.save()

        messages.success(request, "Protocol Guidelines saved successfully.")
        return redirect('protocol_certifications', org_id=org_id, protocol_id=protocol_id)  # Redirect to next step

    context = {
        'protocol': protocol,
        'org_id': org_id,
        'step_number': 6,
        'current_step_name': "Protocol Guidelines",
    }
    return render(request, 'admin/protocol_guidelines.html', context)

def protocol_certifications(request, org_id, protocol_id):
    protocol = get_object_or_404(Protocol, id=protocol_id, organization_id=org_id)

    if request.method == 'POST':
        protocol.required_certifications = request.POST.get('required_certifications', '')
        protocol.certification_body = request.POST.get('certification_body', '')
        protocol.certification_expiry = request.POST.get('certification_expiry', None)

        # Handle file uploads
        if 'certification_documents' in request.FILES:
            uploaded_files = request.FILES.getlist('certification_documents')
            fs = FileSystemStorage()
            file_urls = []
            for file in uploaded_files:
                filename = fs.save(f'certifications/{protocol_id}/{file.name}', file)
                file_urls.append(fs.url(filename))
            protocol.certification_documents = ','.join(file_urls)  # Store multiple file URLs

        # Mark step as completed if required field is filled
        if protocol.required_certifications:
            protocol.steps_completed['protocol_certifications'] = True
        else:
            protocol.steps_completed['protocol_certifications'] = False

        protocol.save()

        messages.success(request, "Protocol Certifications saved successfully.")
        return redirect('protocol_submission', org_id=org_id, protocol_id=protocol_id)  # Redirect to next step

    context = {
        'protocol': protocol,
        'org_id': org_id,
        'step_number': 7,
        'current_step_name': "Protocol Certifications",
    }
    return render(request, 'admin/protocol_certifications.html', context)


def protocol_submission(request, org_id, protocol_id):
    protocol = get_object_or_404(Protocol, id=protocol_id, organization_id=org_id)

    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
            print("Received Submission Data:", data)  # ✅ Debugging log

            action = data.get("action")
            protocol.additional_notes = data.get("additional_notes", "").strip()

            if action == "save_draft":
                protocol.is_draft = True
                protocol.status = "Draft"
                protocol.save()
                protocol.refresh_from_db()  # ✅ Ensure data is available immediately
                print("Saved as Draft:", protocol)  # ✅ Debugging log
                return JsonResponse({"status": "success", "message": "Draft saved successfully!", "redirect_url": f"/{org_id}/protocols/all/"})

            elif action == "submit":
                missing_steps = [step for step, completed in protocol.steps_completed.items() if not completed]
                if missing_steps:
                    return JsonResponse({"status": "error", "message": f"Complete all steps before submitting: {missing_steps}"})

                protocol.is_draft = False  
                protocol.status = "Pending Approval"
                protocol.submitted_at = timezone.now()
                protocol.save()
                protocol.refresh_from_db()  # ✅ Ensure data is immediately available

                print("Protocol after Submission:", protocol)

                return JsonResponse({"status": "success", "message": "Protocol submitted for approval!", "redirect_url": f"/{org_id}/protocols/all/"})

            return JsonResponse({"status": "error", "message": "Invalid action."})

        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)

    return render(request, 'admin/protocol_submission.html', {"protocol": protocol, "org_id": org_id})

def all_protocols_view(request, org_id):
    """
    View all protocols categorized as drafts and submitted
    """
    draft_protocols = Protocol.objects.filter(is_draft=True, submitted_by=request.user, organization_id=org_id)
    submitted_protocols = Protocol.objects.filter(is_draft=False, submitted_by=request.user, organization_id=org_id)

    return render(request, "admin/all_protocols.html", {
        "draft_protocols": draft_protocols,
        "submitted_protocols": submitted_protocols,
        "org_id": org_id
    })

@login_required
@user_passes_test(can_approve_protocol)
def viewing_approve_protocols(request, org_id, protocol_id):
    """
    View submitted protocols for approval, allow reviewers to approve, reject, or request adjustments.
    """
    protocol = get_object_or_404(Protocol, id=protocol_id, organization_id=org_id)

    # Fetch Personnel Details
    personnel_details = {
        "principal_investigator": protocol.principal_investigator,
        "co_principal_investigator": protocol.co_principal_investigator,
        "administrative_contact": protocol.administrative_contact,
        "submitters": protocol.additional_submitters.all()
    }

    if request.method == "POST":
        status = request.POST.get("status")
        comment_text = request.POST.get("comment", "").strip()

        if status not in ["approved", "rejected", "needs_adjustments"]:
            return JsonResponse({"status": "error", "message": "Invalid status update."})

        # Save comment if provided
        if comment_text:
            ApprovalComment.objects.create(
                protocol=protocol,
                reviewer=request.user,
                text=comment_text,
                section="general"
            )

        # Update protocol status
        protocol.status = status
        protocol.reviewed_by = request.user
        protocol.reviewed_at = timezone.now()
        protocol.save()

        return JsonResponse({"status": "success", "message": f"Protocol {status} successfully."})

    context = {
        "protocol": protocol,
        "org_id": org_id,
        "personnel_details": personnel_details,
    }
    
    return render(request, "admin/viewing_approve_protocols.html", context)

def view_protocol(request, org_id, protocol_id):
    """
    View a submitted protocol
    """
    protocol = get_object_or_404(Protocol, id=protocol_id, organization_id=org_id)

    return render(request, "admin/view_protocol.html", {"protocol": protocol, "org_id": org_id})
@login_required
@user_passes_test(is_admin_or_principal)
def search_admin(request):
    query = request.GET.get('query', '').strip()
    organization = request.user.organization

    if query:
        # Role-based filtering
        if request.user.role == 'admin':
            # Admins can only see Users (not other Admins or Principal Admins)
            users = User.objects.filter(
                Q(username__icontains=query) | Q(email__icontains=query),
                organization=organization,
                role='user'  # Assuming 'user' is the role for regular users
            ).exclude(id=request.user.id)  # Exclude the current user
        elif request.user.role == 'principal_admin':
            # Principal Admins can see all users in the organization, including Admins
            users = User.objects.filter(
                Q(username__icontains=query) | Q(email__icontains=query),
                organization=organization
            ).exclude(id=request.user.id)  # Exclude the current user
        else:
            users = User.objects.none()
    else:
        users = User.objects.none()

    # Prepare the response data
    users_list = [{
        'username': user.username,
        'email': user.email,
        'profile_picture': user.profile_picture.url if user.profile_picture else None
    } for user in users]

    return JsonResponse({'users': users_list})
@login_required
@user_passes_test(is_admin_or_principal)
def search_users(request):
    org_id = request.GET.get("org_id")
    query = request.GET.get("query", "").strip()
    organization = get_object_or_404(Organization, id=org_id)

    # Filter users based on the role of the requesting user
    if request.user.role == "principal_admin":
        # Principal Admins see all users except other Principal Admins
        users = User.objects.filter(
            organization=organization,
            username__icontains=query
        ).exclude(role="principal_admin")
    elif request.user.role == "admin":
        # Admins see only non-admin users
        users = User.objects.filter(
            organization=organization,
            username__icontains=query
        ).exclude(role__in=["admin", "principal_admin"])
    else:
        # Unauthorized access fallback (if needed)
        return JsonResponse({"error": "Unauthorized access"}, status=403)

    # Format user data for JSON response
    users_data = [
        {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "email": user.email,
            "profile_picture": user.profile_picture.url if user.profile_picture else None
        }
        for user in users
    ]

    return JsonResponse({"users": users_data})

@login_required
@user_passes_test(is_admin_or_principal)
def user_list(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    
    if request.user.role == 'principal_admin':
        # Principal Admins can see all users, including Admins but excluding other Principal Admins
        users = User.objects.filter(organization=organization).exclude(role='principal_admin')
    elif request.user.role == 'admin':
        # Admins can see only regular users, excluding Admins and Principal Admins
        users = User.objects.filter(organization=organization).exclude(role__in=['admin', 'principal_admin'])
    else:
        # If the role does not match, deny access
        return HttpResponseForbidden("You do not have permission to view this user list.")

    return render(request, 'admin/user_list.html', {
        'users': users, 
        'org_id': org_id
    })

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
@login_required
@user_passes_test(lambda u: u.role in ['admin', 'principal_admin'])
def view_user(request, org_id, user_id):
    """View a specific user's profile and assigned certifications."""
    viewed_user = get_object_or_404(User, id=user_id, organization_id=org_id)

    # Fetch assigned certifications
    assigned_certs = Certification.objects.filter(
        id__in=UserCertification.objects.filter(user=viewed_user).values_list('certification_id', flat=True)
    )

    # Fetch the folders that contain assigned certifications
    folder_cert_mapping = {}
    for cert in assigned_certs:
        if cert.folder_id not in folder_cert_mapping:
            folder_cert_mapping[cert.folder_id] = {
                "folder_name": cert.folder.name,
                "certifications": []
            }
        folder_cert_mapping[cert.folder_id]["certifications"].append(cert)

    return render(
        request, 
        "admin/view_user.html", 
        {
            "viewed_user": viewed_user, 
            "folder_cert_mapping": folder_cert_mapping,  # ✅ Pass organized folder-certification data
            "org_id": org_id
        }
    )


@login_required
@user_passes_test(lambda u: u.role in ['admin', 'principal_admin'])
def user_animals_view(request, org_id, user_id):
    user = get_object_or_404(User, id=user_id, organization_id=org_id)
    animals = Animal.objects.filter(assigned_users=user)

    context = {
        'org_id': org_id,
        'user': user,
        'animals': animals,
    }
    return render(request, 'admin/user_animals.html', context)

@login_required
@user_passes_test(is_admin_or_principal)
def user_actions(request, user_id, org_id):
    user = get_object_or_404(User, id=user_id, organization_id=org_id)
    actions = UserAction.objects.filter(user=user, organization_id=org_id)

    # Filter by search query
    search_query = request.GET.get('search', '').strip()
    if search_query:
        actions = actions.filter(
            Q(action__icontains=search_query) | Q(additional_info__icontains=search_query)
        )

    # Filter by date range
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    if start_date:
        try:
            start_datetime = datetime.strptime(start_date, '%Y-%m-%d %H:%M')
            actions = actions.filter(timestamp__gte=start_datetime)
        except ValueError:
            # Handle invalid date format
            pass
    if end_date:
        try:
            end_datetime = datetime.strptime(end_date, '%Y-%m-%d %H:%M')
            actions = actions.filter(timestamp__lte=end_datetime)
        except ValueError:
            # Handle invalid date format
            pass

    # Paginate the actions
    paginator = Paginator(actions.order_by('-timestamp'), 10)  # Show 10 actions per page
    page_number = request.GET.get('page')
    actions = paginator.get_page(page_number)

    return render(request, 'admin/user_actions.html', {
        'user': user,
        'actions': actions,
        'org_id': org_id,
        'search_query': search_query,
        'start_date': start_date,
        'end_date': end_date,
    })

@login_required
def action_details(request, action_id):
    action = get_object_or_404(UserAction, id=action_id)

    session_details = []
    if "Data Import" in action.action:
        try:
            # Load preview data from additional_info
            import_data = json.loads(action.additional_info)
            for entry in import_data:
                session_details.append({
                    "experiment_name": entry.get("experiment_name"),
                    "data": entry.get("data", []),
                })
        except Exception as e:
            logger.error(f"Error parsing import details: {e}")

    return render(request, 'admin/action_details.html', {
        "action": action,
        "session_details": session_details,
    })

@receiver(post_save, sender=User)
def create_user_signature(sender, instance, created, **kwargs):
    if created:
        # Automatically create a UserSignature instance for the new user
        UserSignature.objects.create(user=instance)


@login_required
@user_passes_test(lambda u: u.role in ['admin', 'principal_admin'])
def send_admin_notification(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)

    if request.method == 'POST':
        recipient_ids = request.POST.getlist('recipients')
        title = request.POST.get('title', '').strip()
        sender_name = request.POST.get('sender_name', '').strip()
        message_content = request.POST.get('message', '').strip()

        # Validate required fields
        if not recipient_ids or not title or not sender_name or not message_content:
            messages.error(request, "All fields (recipients, title, sender name, and message) are required.")
            return redirect('send_admin_notification', org_id=org_id)

        recipients = User.objects.filter(id__in=recipient_ids, organization=organization)

        for recipient in recipients:
            # Create a notification for each recipient
            InboxNotification.objects.create(
                user=recipient,
                organization=organization,
                title=title,
                sender_name=sender_name,
                message=message_content,
                from_admin=True,
                is_read=False,  # Mark as unread
                timestamp=timezone.now() 
            )

        messages.success(request, "Notifications sent successfully.")
        return redirect('admin_dashboard', org_id=org_id)

    users = User.objects.filter(organization=organization)
    return render(request, 'admin/notify_users.html', {'users': users, 'org_id': org_id})


@login_required
def admin_notify(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)

    if request.method == 'POST':
        recipient_ids = request.POST.getlist('recipients')
        title = request.POST.get('title', '').strip()
        sender_name = request.POST.get('sender_name', '').strip()
        message_content = request.POST.get('message', '').strip()

        # Validate required fields
        if not recipient_ids or not title or not sender_name or not message_content:
            messages.error(request, "All fields (recipients, title, sender name, and message) are required.")
            return redirect('admin_notify', org_id=org_id)

        recipients = User.objects.filter(id__in=recipient_ids, organization=organization)

        for recipient in recipients:
            # Create a notification for each recipient
            InboxNotification.objects.create(
                user=recipient,
                organization=organization,
                title=title,
                sender_name=sender_name,
                message=message_content,
                from_admin=True,
                is_read=False,  # Mark as unread
                timestamp=timezone.now()
            )

        messages.success(request, "Notifications sent to selected users.")
        return redirect('admin_notify', org_id=org_id)

    users = User.objects.filter(organization=organization)
    return render(request, 'admin/notify_users.html', {'users': users, 'org_id': org_id})


@login_required
@user_passes_test(lambda u: u.role in ['admin', 'principal_admin'])
def create_form(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    users = User.objects.filter(organization=organization)  # All users in the organization
    message = None

    if request.method == 'POST':
        form_name = request.POST.get('form_name')
        form_description = request.POST.get('form_description')
        user_selection = request.POST.get('user_selection')
        selected_user_ids = request.POST.getlist('specific_users[]')  # List of selected user IDs
        form_file = request.FILES.get('form_file')

        logger.info(f"Form submission initiated. Form name: {form_name}, user_selection: {user_selection}")
        logger.info(f"Received selected_user_ids: {selected_user_ids}")

        # Validate specific user selection
        if user_selection == 'specific' and not selected_user_ids:
            logger.error("Specific user selection was chosen, but no users were selected.")
            messages.error(request, "You must select at least one user when choosing 'Specific Users'.")
            return redirect('create_form', org_id=org_id)

        # Save the form
        uploaded_form = AdminCreatedForm.objects.create(
            name=form_name,
            description=form_description,
            organization=organization,
            created_by=request.user
        )

        # Save the uploaded file as a PDFTemplate
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

            # Assign form to users
            if user_selection == 'specific':
                assigned_users = users.filter(id__in=selected_user_ids)
                logger.info(f"Filtered assigned users: {[user.username for user in assigned_users]}")

                if not assigned_users.exists():
                    logger.error("No valid users matched the provided IDs. Form assignment will fail.")
                    messages.error(request, "No valid users found for assignment.")
                    return redirect('create_form', org_id=org_id)

                # Create UserFilledForm instances for assigned users
                for user in assigned_users:
                    UserFilledForm.objects.create(
                        user=user,
                        form=uploaded_form,
                        file_path=pdf_template.uploaded_pdf.url
                    )
            else:
                # Assign to all users
                logger.info("Assigning form to all users in the organization.")
                for user in users:
                    UserFilledForm.objects.create(
                        user=user,
                        form=uploaded_form,
                        file_path=pdf_template.uploaded_pdf.url
                    )

            message = "Form successfully created and assigned to the selected users."
            logger.info(message)

    return render(request, 'admin/create_form.html', {
        'users': users,
        'org_id': org_id,
        'message': message
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

@login_required
def delete_protocol(request, org_id, protocol_id):
    """Deletes a draft protocol if it's not submitted."""
    protocol = get_object_or_404(Protocol, id=protocol_id, organization_id=org_id)

    if protocol.is_draft:
        protocol.delete()
        messages.success(request, "Protocol deleted successfully.")
        return JsonResponse({"status": "success", "message": "Protocol deleted successfully."})
    else:
        return JsonResponse({"status": "error", "message": "Cannot delete a submitted protocol."}, status=400)

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
@user_passes_test(lambda u: u.role == 'admin' or u.role == 'principal_admin')
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


@csrf_exempt
def fill_and_download_pdf(request, org_id, form_id):
    """Handles the SF-424 form submission and saves the filled PDF locally."""
    if request.method == "POST":
        uploaded_pdf = request.FILES.get("edited_pdf")

        if not uploaded_pdf:
            return JsonResponse({"error": "No PDF file received"}, status=400)

        try:
            # ✅ Ensure directory exists
            pdf_dir = os.path.join(settings.MEDIA_ROOT, "pdfs")
            os.makedirs(pdf_dir, exist_ok=True)

            # ✅ Save the uploaded file
            file_path = os.path.join(pdf_dir, f"filled_sf424_{form_id}.pdf")
            with open(file_path, "wb+") as destination:
                for chunk in uploaded_pdf.chunks():
                    destination.write(chunk)

            # ✅ Generate local URL for access
            
            filled_pdf_url = f"{settings.STATIC_URL}pdfs/filled_sf424_{form_id}.pdf"

            


            return JsonResponse({"success": True, "download_url": filled_pdf_url})

        except Exception as e:
            logging.error(f"Error saving filled PDF: {e}")
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request"}, status=400)


def extract_pdf_fields(pdf_filename):
    """Extracts form fields from a PDF stored in static files."""
    pdf_path = os.path.join(settings.STATICFILES_DIRS[0], "pdfs", pdf_filename)
    print(f"Checking PDF at: {pdf_path}")

    if not os.path.exists(pdf_path):
        print(f"❌ File not found at: {pdf_path}")
        return []

    reader = PdfReader(pdf_path)
    fields = []

    if "/AcroForm" in reader.trailer["/Root"]:
        form_fields = reader.trailer["/Root"]["/AcroForm"]["/Fields"]
        for field in form_fields:
            field_obj = field.get_object()
            field_name = field_obj.get("/T")  # Field name
            field_type = field_obj.get("/FT")  # Field type
            field_value = field_obj.get("/V", "")

            fields.append({
                "name": field_name,
                "type": field_type,
                "value": field_value
            })

    return fields

def upload_pdf_view(request, org_id):
    """
    Handles PDF file upload and extracts form fields.
    """
    logger.info("Upload request received")  # ✅ Debugging start point

    if request.method != 'POST':  # ✅ Ensure only POST requests are allowed
        logger.warning(f"Invalid request method: {request.method}")  # ✅ Log incorrect methods
        return JsonResponse({"success": False, "error": "Invalid request method"}, status=400)

    if 'pdf_file' not in request.FILES:
        logger.error("No file found in request.FILES")
        return JsonResponse({"success": False, "error": "No file uploaded"}, status=400)

    try:
        pdf_file = request.FILES['pdf_file']
        logger.info(f"Received file: {pdf_file.name}, Size: {pdf_file.size} bytes")

        fs = FileSystemStorage()
        filename = fs.save(pdf_file.name, pdf_file)
        file_path = fs.path(filename)

        # ✅ Extract fields from PDF
        extracted_fields = extract_pdf_fields(file_path)
        logger.info(f"Extracted fields: {json.dumps(extracted_fields, indent=2)}")

        # ✅ Save the uploaded PDF as a template
        pdf_template = PDFTemplate.objects.create(
            name=pdf_file.name,
            uploaded_pdf=filename,
            organization=get_object_or_404(Organization, id=org_id),
            uploaded_by=request.user,
            uploaded_at=timezone.now(),
        )

        return JsonResponse({"success": True, "message": "PDF uploaded successfully!", "template_id": pdf_template.id})

    except Exception as e:
        logger.error(f"Error during PDF upload: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@user_passes_test(lambda u: u.role in ['admin', 'principal_admin'])
def fill_out_forms(request, org_id):
    """Display available forms that users can fill out."""
    organization = get_object_or_404(Organization, id=org_id)
    available_forms = PDFTemplate.objects.filter(organization=organization)  # List of uploaded PDFs

    return render(request, 'admin/fill_out_forms.html', {
        'org_id': org_id,
        'available_forms': available_forms
    })
ADOBE_CREDENTIALS_PATH = os.path.join(settings.BASE_DIR, "pdfservices-api-credentials.json")

@login_required
@user_passes_test(lambda u: u.role in ['admin', 'principal_admin'])
def bulk_assign_animals(request, org_id):
    """
    Allows bulk assignment of animals to users.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            animal_ids = data.get('animal_ids', [])
            user_ids = data.get('user_ids', [])

            if not animal_ids or not user_ids:
                return JsonResponse({'success': False, 'message': 'Animals or users not specified'}, status=400)

            animals = Animal.objects.filter(id__in=animal_ids, organization_id=org_id)
            users = User.objects.filter(id__in=user_ids, organization_id=org_id)

            if not animals.exists() or not users.exists():
                return JsonResponse({'success': False, 'message': 'Invalid animals or users selected'}, status=400)

            for animal in animals:
                animal.assigned_users.add(*users)  # Add users to the animal
                animal.save()

            return JsonResponse({'success': True, 'message': 'Animals successfully assigned to selected users'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)
    else:
        return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=400)
@login_required
@user_passes_test(lambda u: u.role in ['admin', 'principal_admin'])
def assign_animals(request, org_id):
    if request.method == 'POST':
        data = json.loads(request.body)
        animal_ids = data.get('animal_ids', [])
        user_usernames = data.get('user_ids', [])

        try:
            # Convert usernames to user IDs
            users = User.objects.filter(username__in=user_usernames, organization_id=org_id)
            user_ids = list(users.values_list('id', flat=True))

            if not user_ids or not animal_ids:
                return JsonResponse({'success': False, 'message': 'Animals or users not specified'}, status=400)

            animals = Animal.objects.filter(id__in=animal_ids, cage__organization_id=org_id)

            if not animals.exists() or not users.exists():
                return JsonResponse({'success': False, 'message': 'Invalid animals or users selected'}, status=400)

            for animal in animals:
                animal.assigned_users.add(*users)  # Add users to the animal
                animal.save()

            return JsonResponse({'success': True, 'message': 'Animals successfully assigned to selected users'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)
    else:
        return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=400)
@login_required
@user_passes_test(lambda u: u.role == 'principal_admin')
def assign_certifications(request, org_id):
    """Assigns Certifications and Training Folders to Users"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            folder_ids = set(data.get("folder_ids", []))  # Convert to set for uniqueness
            certification_ids = set(data.get("certification_ids", []))  # Convert to set for uniqueness
            user_ids = data.get("user_ids", [])

            if not user_ids or (not folder_ids and not certification_ids):
                return JsonResponse({"success": False, "message": "Users or certifications not specified"}, status=400)

            users = User.objects.filter(id__in=user_ids, organization_id=org_id)
            if not users.exists():
                return JsonResponse({"success": False, "message": "Invalid users selected"}, status=400)

            # Fetch certifications from selected folders
            folder_certifications = set(Certification.objects.filter(folder_id__in=folder_ids).values_list("id", flat=True))

            # Exclude certifications already individually selected
            folder_certifications -= certification_ids

            # Merge the unique certifications
            all_certification_ids = certification_ids | folder_certifications  # Union of both sets

            # Assign certifications to users
            assigned_count = 0
            for user in users:
                for cert_id in all_certification_ids:
                    cert = Certification.objects.get(id=cert_id)
                    _, created = UserCertification.objects.get_or_create(user=user, certification=cert, assigned_by=request.user)
                    if created:
                        assigned_count += 1

            return JsonResponse({"success": True, "message": f"Successfully assigned {assigned_count} certifications."})

        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)}, status=500)

    return JsonResponse({"success": False, "message": "Invalid request method"}, status=400)
@login_required
@user_passes_test(is_principal_admin)
def create_training_folder(request, org_id):
    """Allows the Principal Admin to create Training Folders."""
    if request.method == 'POST':
        form = TrainingFolderForm(request.POST)
        if form.is_valid():
            folder = form.save(commit=False)
            folder.created_by = request.user
            folder.save()
            messages.success(request, "Training Folder created successfully.")
            return redirect('manage_training_folders', org_id=org_id)
    else:
        form = TrainingFolderForm()

    return render(request, 'admin/create_training_folder.html', {'form': form, 'org_id': org_id})
@login_required
@user_passes_test(lambda u: u.role == 'principal_admin')
def manage_training_folders(request, org_id):
    """Displays all training folders and users for assignment."""
    folders = TrainingFolder.objects.prefetch_related("certifications").all()
    users = User.objects.filter(organization_id=org_id).exclude(role="principal_admin")  # Exclude self

    return render(request, 'admin/manage_training_folders.html', {
        'folders': folders,
        'users': users,
        'org_id': org_id
    })

@login_required
@user_passes_test(is_principal_admin)
def create_certification(request, org_id, folder_id):
    """Allows Principal Admin to create certifications under a training folder."""
    folder = get_object_or_404(TrainingFolder, id=folder_id)
    
    if request.method == 'POST':
        form = CertificationForm(request.POST)
        if form.is_valid():
            certification = form.save(commit=False)
            certification.folder = folder
            certification.save()
            messages.success(request, "Certification created successfully.")
            return redirect('manage_training_folders', org_id=org_id)
    else:
        form = CertificationForm()

    return render(request, 'admin/create_certification.html', {'form': form, 'folder': folder, 'org_id': org_id})


# Render PDF Preview Page
def fill_form_view(request, pdf_id):
    pdf_template = get_object_or_404(PDFTemplate, id=pdf_id)
    return render(request, "fill_form.html", {"pdf": pdf_template, "pdf_id": pdf_id})

# API to Save User Input


@login_required
@user_passes_test(lambda u: u.role in ['admin', 'principal_admin'])
def save_filled_form(request, org_id, form_id):
    """Handles form submission and saves the filled data."""
    if request.method == "POST":
        try:
            data = json.loads(request.body)  # Parse JSON form data
            
            # Get the PDF template
            pdf_template = get_object_or_404(PDFTemplate, id=form_id, organization_id=org_id)

            # Save filled data as JSON
            filled_data_path = os.path.join(settings.MEDIA_ROOT, f"filled_forms/form_{form_id}.json")
            os.makedirs(os.path.dirname(filled_data_path), exist_ok=True)

            with open(filled_data_path, "w") as json_file:
                json.dump(data, json_file, indent=4)

            return JsonResponse({"success": True, "message": "Form data saved successfully!"})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    return JsonResponse({"success": False, "message": "Invalid request"}, status=400)


def download_filled_performance_site(request, org_id, package_id):
    # ✅ Ensure the package exists
    form_package = get_object_or_404(FormPackage, id=package_id, organization_id=org_id)
   


    # ✅ Fetch performance site locations
    site_locations = PerformanceSiteLocation.objects.filter(form_package=form_package).order_by("identifier")

    if not site_locations.exists():
        return HttpResponse("No performance site locations found for this organization.", status=404)

    # ✅ Load the template PDF
    pdf_template_path = "/Users/ryancarmody/algoResearchs/static/templates/performance_site_template.pdf"
    try:
        doc = fitz.open(pdf_template_path)
    except Exception as e:
        return HttpResponse(f"Error opening PDF template: {str(e)}", status=500)

    # ✅ Fill in the form fields
    for page in doc:
        for site in site_locations:
            field_mapping = {
                "Organization Name": site.organization_name or "N/A",
                "UEI": site.uei or "N/A",
                "Street1": site.street1,
                "Street2": site.street2 or "",
                "City": site.city,
                "County": site.county or "",
                "State": site.state or "",
                "Province": site.province or "",
                "Country": site.country,
                "ZIP/Postal Code": site.zip_code or "",
                "Congressional District": site.congressional_district or "",
            }

            for key, value in field_mapping.items():
                text_instances = page.search_for(key)
                for inst in text_instances:
                    x, y, _, _ = inst
                    page.insert_text((x + 100, y), value, fontsize=10, color=(0, 0, 0))

    # ✅ Save to memory and return response
    output_buffer = io.BytesIO()
    doc.save(output_buffer)
    output_buffer.seek(0)
    
    return FileResponse(output_buffer, as_attachment=True, filename="Filled_Performance_Site_Locations.pdf")


def get_form_fields(request, form_id):
    """Retrieve extracted fields for a given form"""
    pdf_template = get_object_or_404(PDFTemplate, id=form_id)

    try:
        fields = json.loads(pdf_template.fields)  # Ensure fields are stored as JSON
    except json.JSONDecodeError:
        fields = []

    return JsonResponse({"fields": fields})


# Path to the SF-424 PDF (adjust as needed)
SF_424_PATH = os.path.join(os.path.dirname(__file__), "/static/pdfs/sf424_18.pdf")

def fill_out_form(request):
    return render(request, "fill_out_forms.html")

def view_pdf(request):
    """Serve the SF-424 PDF file"""
    pdf_path = os.path.join(settings.STATICFILES_DIRS[0], "pdfs", "sf424_18.pdf")

    if not os.path.exists(pdf_path):
        return HttpResponseNotFound("File not found. Ensure the file is inside static/pdfs/.")

    return FileResponse(open(pdf_path, "rb"), content_type="application/pdf")




def check_pdf_fields(pdf_filename):
    """Extracts form fields from a PDF stored in media/pdfs/."""
    pdf_path = os.path.join(settings.MEDIA_ROOT, "pdfs", pdf_filename)
    print(f"Checking PDF at: {pdf_path}")

    if not os.path.exists(pdf_path):
        print(f"❌ File not found at: {pdf_path}")
        return []

    reader = PdfReader(pdf_path)
    fields = []

    if "/AcroForm" in reader.trailer["/Root"]:
        form_fields = reader.trailer["/Root"]["/AcroForm"]["/Fields"]
        for field in form_fields:
            field_obj = field.get_object()
            field_name = field_obj.get("/T")  # Field name
            field_type = field_obj.get("/FT")  # Field type
            field_value = field_obj.get("/V", "")

            fields.append({
                "name": field_name,
                "type": field_type,
                "value": field_value
            })

    return fields


@login_required
def get_pdf_fields(request, pdf_id):
    """Retrieve form fields for a given PDF."""
    pdf_template = get_object_or_404(PDFTemplate, id=pdf_id)
    reader = PdfReader(pdf_template.uploaded_pdf.path)
    fields = []

    if "/AcroForm" in reader.trailer["/Root"]:
        for field in reader.get_fields():
            field_obj = reader.get_field(field)
            field_name = field
            field_type = "text"

            if "/FT" in field_obj:
                if field_obj["/FT"] == "/Btn":
                    field_type = "checkbox"
                elif field_obj["/FT"] == "/Tx":
                    field_type = "text"

            fields.append({
                "name": field_name,
                "type": field_type,
            })

    return JsonResponse({"fields": fields})


@login_required
def get_form_fields(request, form_id):
    """
    API to fetch form fields based on selected form.
    """
    form_instance = get_object_or_404(UserFilledForm, id=form_id, user=request.user)
    fields = form_instance.form.fields.all()

    field_data = [
        {"name": field.field_label.lower().replace(" ", "_"), "label": field.field_label}
        for field in fields
    ]
    
    return JsonResponse({"fields": field_data})


@login_required
@user_passes_test(lambda u: u.role in ['admin', 'principal_admin'])
def list_form_packages(request, org_id):
    """Displays available Form Packages."""
    form_packages = FormPackage.objects.filter(organization_id=org_id)

    return render(request, "admin/form_packages.html", {
        "form_packages": form_packages,
        "org_id": org_id
    })


@login_required
@user_passes_test(lambda u: u.role in ['admin', 'principal_admin'])
def load_package_forms(request, org_id, package_id):
    """Loads all forms belonging to a selected package."""
    package = get_object_or_404(FormPackage, id=package_id, organization_id=org_id)
    package_forms = PackageForm.objects.filter(package=package).select_related("pdf_template")

    return render(request, "admin/fill_package_forms.html", {
        "package": package,
        "package_forms": package_forms,
        "org_id": org_id
    })
@login_required
@user_passes_test(lambda u: u.role in ['admin', 'principal_admin'])
def package_display(request, org_id, package_id):
    try:
        # 🔍 Try to retrieve the opportunity and project to get the project_id
        opportunity = Opportunity.objects.filter(form_package_id=package_id).first()
        project = opportunity.project if opportunity else None
        project_id = project.id if project else None
        if project_id:
            request.session["project_id"] = project_id
        
        # 🔍 Try to retrieve an existing draft for this user, package, and organization
        draft = SubmittedPackage.objects.filter(
            user=request.user,
            org_id=org_id,
            package_id=package_id,
            project=project,  # Ensure draft is linked to the specific project
            is_draft=True
        ).last()
        # Initialize draft data variables
        sf424_data = {}
        rr_budget_data = {}
        budget_periods = []
        cumulative_totals = {}
        draft_exists = False
        if draft:
            sf424_data = draft.sf424_data if draft.sf424_data else {}
            rr_budget_data = draft.rr_budget_data if hasattr(draft, 'rr_budget_data') and draft.rr_budget_data else {}
            budget_periods = draft.budget_periods
            cumulative_totals = draft.cumulative_totals
            draft_exists = True
            print(f"✅ Draft found for user {request.user.username}, package ID {package_id}, project ID {project_id}")
        else:
            sf424_data = {}
            rr_budget_data = {}
            budget_periods = []
            cumulative_totals = {}
            draft_exists = False
            print(f"❌ No draft found for user {request.user.username}, package ID {package_id}, project ID {project_id}")
        # Get the package, allowing for null organization
        package = FormPackage.objects.filter(id=package_id).first()

        if not package:
            print(f"❌ No FormPackage matches the given query. Package ID: {package_id}")
            return HttpResponse("Form Package not found", status=404)

        print(f"✅ Package found: ID {package.id}, Name: {package.name}, Type: {package.package_type}")
    except FormPackage.DoesNotExist:
        print(f"❌ No FormPackage matches the given query. Package ID: {package_id}, Org ID: {org_id}")
        return HttpResponse("Form Package not found", status=404)

    package_forms = list(PackageForm.objects.filter(package=package))
    user = request.user
    print(f"Package Type: {package.package_type}")

    # User Data
    user_data = {
        "prefix": user.prefix,
        "first_name": user.first_name,
        "middle_name": user.middle_name,
        "last_name": user.last_name,
        "suffix": user.suffix,
        "position_title": user.position,
        "street1": user.street1,
        "street2": user.street2,
        "city": user.city,
        "county": user.county,
        "state": user.state,
        "province": user.province,
        "country": user.country,
        "zip_code": user.zip_code,
        "phone_number": user.phone_number,
        "fax": user.fax,
        "email": user.email,
    }

    # Manually Add Required Forms (SF-424, RR Budget)
    additional_forms = []

    if package.package_type == "combined":
        additional_forms.append({"id": "1", "name": "SF-424 Form", "template": "admin/fill_out_sf424.html"})
        additional_forms.append({"id": "2", "name": "RR Budget", "template": "admin/RR_Budget.html"})
    elif package.package_type in ["sf424_only", "sf424"]:
        additional_forms.append({"id": "1", "name": "SF-424 Form", "template": "admin/fill_out_sf424.html"})
    elif package.package_type in ["rr_budget_only", "rr_budget"]:
        additional_forms.append({"id": "2", "name": "RR Budget", "template": "admin/RR_Budget.html"})
    else:
        print(f"Unknown package type: {package.package_type}")

    # Merge All Forms
    all_forms = additional_forms + [
        {"id": str(form.id), "name": form.pdf_template.name if form.pdf_template else "Unnamed Form", "template": form.html_template_name}
        for form in package_forms
    ]

    # Track User Progress Using Sessions
    session_progress_key = f"{org_id}_{package_id}_progress"
    form_progress = request.session.get(session_progress_key, {})

    # Ensure `selected_form_id` Defaults to First Form
    selected_form_id = request.GET.get("form") or (all_forms[0]["id"] if all_forms else None)
    selected_form = next((form for form in all_forms if form["id"] == selected_form_id), None)

    # Handle the case when `selected_form` is None
    if selected_form is None:
        print(f"❗ Warning: Selected form ID '{selected_form_id}' not found.")
        selected_form = all_forms[0] if all_forms else None

    current_index = next((i for i, form in enumerate(all_forms) if form["id"] == selected_form_id), None)
    previous_form = all_forms[current_index - 1] if current_index is not None and current_index > 0 else None
    next_form = all_forms[current_index + 1] if current_index is not None and current_index < len(all_forms) - 1 else None

    # Log the additional forms and selected form for debugging
    print(f"Additional Forms: {additional_forms}")
    print(f"All Forms: {all_forms}")
    print(f"Selected Form ID: {selected_form_id}")
    print(f"Selected Form: {selected_form}")
    print(f"Previous Form: {previous_form}")
    print(f"Next Form: {next_form}")

    # Render Package Display Page
    return render(request, "admin/package_display.html", {
        "package": package,
        "project_id": project_id,
        "org_id": org_id,
        "package_id": package_id,
        "package_forms": package_forms,
        "additional_forms": additional_forms,
        "selected_form": selected_form,
        "form_id": selected_form["id"] if selected_form else None,
        "template_name": selected_form["template"] if selected_form else None,
        "user_data": user_data,
        "form_progress": form_progress,
        "previous_form": previous_form,
        "next_form": next_form,
        "draft_exists": draft_exists,
        "budget_periods": budget_periods,
        "cumulative_totals": cumulative_totals,
        "sf424_data": sf424_data,
        "rr_budget_data": rr_budget_data,
    })


def parse_sf424_schema(xml_file):
    """Extracts form fields from the SF-424 XML schema"""
    tree = ET.parse(xml_file)
    root = tree.getroot()

    ns = {"xs": "http://www.w3.org/2001/XMLSchema"}

    fields = []

    for element in root.findall(".//xs:element", ns):
        field_name = element.get("name")
        field_type = element.get("type")

        # Extract dropdown values if available
        restriction = element.find(".//xs:restriction", ns)
        if restriction is not None:
            options = [enum.get("value") for enum in restriction.findall("xs:enumeration", ns)]
        else:
            options = None
        
        fields.append({
            "name": field_name,
            "type": field_type if field_type else "string",
            "options": options
        })

    return fields


@login_required
@user_passes_test(lambda u: u.role in ['admin', 'principal_admin'])
def save_rr_other_information(request, org_id):
    """Handles RR Other Information form submission."""
    if request.method == "POST":
        try:
            proprietary_info = request.POST.get("proprietary_info", False)
            environmental_impact = request.POST.get("environmental_impact", False)
            historic_properties = request.POST.get("historic_properties", False)
            human_subjects = request.POST.get("human_subjects", "")
            vertebrate_animals = request.POST.get("vertebrate_animals", "")
            international_collab = request.POST.get("international_collaboration", "")
            uploaded_file = request.FILES.get("attachments", None)

            # Save to database (example model)
            rr_info = RROtherInformation.objects.create(
                organization_id=org_id,
                proprietary_info=proprietary_info,
                environmental_impact=environmental_impact,
                historic_properties=historic_properties,
                human_subjects=human_subjects,
                vertebrate_animals=vertebrate_animals,
                international_collaboration=international_collab,
                uploaded_file=uploaded_file
            )

            messages.success(request, "RR Other Information form submitted successfully!")
            return redirect('package_display', org_id=org_id, package_id=request.POST.get("package_id"))

        except Exception as e:
            messages.error(request, f"Error: {e}")

    return redirect('package_display', org_id=org_id, package_id=request.POST.get("package_id"))



def budget_period_view(request, org_id, period_number):
    organization = get_object_or_404(Organization, id=org_id)
    budget_period, created = BudgetPeriod.objects.get_or_create(
        organization=organization,
        period_number=period_number
    )

    if request.method == "POST":
        form = BudgetPeriodForm(request.POST, instance=budget_period)
        if form.is_valid():
            form.save()
            return redirect('next_budget_section', org_id=org_id, period_number=period_number)  # Move to Part A
    else:
        form = BudgetPeriodForm(instance=budget_period)

    return render(request, "admin/RR_Budget.html", {
        "form": form,
        "period_number": period_number,
        "organization": organization
    })

def generate_filled_pdf(pdf_path, output_pdf, form_data):
    doc = fitz.open(pdf_path)

    for page_num, page in enumerate(doc):
        for field, data in form_data.items():
            if field in field_positions:
                x, y = field_positions[field]
                page.insert_text((x, y), str(data), fontsize=10, color=(0, 0, 0))  # Insert text
    
    doc.save(output_pdf)
    print(f"PDF saved at {output_pdf}")


def generate_sf424_xml(form_instance):
    root = ET.Element("SF424")

    ET.SubElement(root, "SubmissionType").text = form_instance.submission_type
    ET.SubElement(root, "DateSubmitted").text = str(form_instance.date_submitted)
    ET.SubElement(root, "ApplicantIdentifier").text = form_instance.applicant_identifier or ""
    ET.SubElement(root, "StateApplicationIdentifier").text = form_instance.state_application_identifier or ""
    ET.SubElement(root, "FederalIdentifier").text = form_instance.federal_identifier or ""

    # Contact Person Information
    contact = ET.SubElement(root, "ContactPerson")
    ET.SubElement(contact, "FirstName").text = form_instance.contact_first_name
    ET.SubElement(contact, "LastName").text = form_instance.contact_last_name
    ET.SubElement(contact, "Email").text = form_instance.contact_email

    # Estimated Funding
    funding = ET.SubElement(root, "EstimatedFunding")
    ET.SubElement(funding, "TotalFederalFundsRequested").text = str(form_instance.total_federal_funds_requested)
    ET.SubElement(funding, "TotalNonFederalFunds").text = str(form_instance.total_non_federal_funds)

    return ET.tostring(root, encoding="utf-8").decode("utf-8")


def fill_out_sf424(request):
    if request.method == 'POST':
        form = SF424Form(request.POST)
        if form.is_valid():
            # Retrieve user input
            position_title = form.cleaned_data['position_title'].replace(' ', '&#160;')
            authorized_rep_title = form.cleaned_data['authorized_representative_title'].replace(' ', '&#160;')
            
            # Load the XML template
            xml_file = '/Users/ryancarmody/algoResearchs/dashboard/templates/admin/SF4X.xml'
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            # Find and replace placeholders in XML
            for elem in root.iter():
                if elem.tag == 'ix:nonNumeric' and elem.attrib.get('name') == 'sap:GranteeContactTitle':
                    elem.text = position_title
                elif elem.tag == 'ix:nonNumeric' and elem.attrib.get('name') == 'sap:AuthorizedRepresentativeTitle':
                    elem.text = authorized_rep_title
            
            # Convert XML tree to string
            updated_xml = ET.tostring(root, encoding='utf-8').decode()
            
            # Serve XML as downloadable file
            response = HttpResponse(updated_xml, content_type='application/xml')
            response['Content-Disposition'] = 'attachment; filename=updated_sf424.xml'
            return response
    else:
        form = SF424Form()
    
    return render(request, 'admin/fill_out_sf424.html', {'form': form})

@login_required
def download_sf424_xml(request, form_id):
    sf424_instance = SF424Form.objects.get(id=form_id, user=request.user)
    xml_data = generate_sf424_xml(sf424_instance)

    response = HttpResponse(xml_data, content_type="application/xml")
    response["Content-Disposition"] = f'attachment; filename="SF424_{form_id}.xml"'
    return response

def submit_sf424_form(request):
    if request.method == "POST":
        form_data = request.POST  # Capture form data
        submission = SF424Submission.objects.create(
            submission_type=form_data.get("submission_type"),
            federal_entity_identifier=form_data.get("federal_entity_identifier"),
            agency_routing_number=form_data.get("agency_routing_number"),
            previous_tracking_id=form_data.get("previous_tracking_id"),
            consolidated_app=form_data.get("consolidated_app"),
            explanation=form_data.get("explanation"),
            date_submitted=form_data.get("date_submitted"),
            applicant_identifier=form_data.get("applicant_identifier"),
            state_use_only=form_data.get("state_use_only"),
            legal_name=form_data.get("legal_name"),
            ein_tin=form_data.get("ein_tin"),
            duns_number=form_data.get("duns_number"),
            address_street1=form_data.get("address_street1"),
            address_street2=form_data.get("address_street2"),
            city=form_data.get("city"),
            state=form_data.get("state"),
            country=form_data.get("country"),
            zip_code=form_data.get("zip_code"),
            contact_name=form_data.get("contact_name"),
            contact_email=form_data.get("contact_email"),
            contact_phone=form_data.get("contact_phone"),
        )
        return JsonResponse({"message": "Submission Saved!", "submission_id": submission.id})
    
    return render(request, "admin/fill_out_sf424.html")

def sf424_answers(request, org_id, form_id):
    """ Retrieves SF-424 data stored in the session and displays it in a template """
    org_id = int(org_id)
    form_id = int(form_id)

    # Load applicant types
    with open("static/applicant_types.json") as f:
        applicant_types = json.load(f)

    # Retrieve **all session data** for this specific form
    context = {
        key.replace(f"_{org_id}_{form_id}", ""): value
        for key, value in request.session.items()
        if key.endswith(f"_{org_id}_{form_id}")
    }
    for key in ["submission_type", "application_type", "revision_type"]:
        if key in context and isinstance(context[key], list):
            context[key] = ", ".join(context[key])

    # Convert stored lists (checkbox selections) to readable strings
    if "submission_type" in context and isinstance(context["submission_type"], list):
        context["submission_type"] = ", ".join(context["submission_type"])

    if "application_type" in context and isinstance(context["application_type"], list):
        context["application_type"] = ", ".join(context["application_type"])

    if "revision_type" in context and isinstance(context["revision_type"], list):
        context["revision_type"] = ", ".join(context["revision_type"])

    # Ensure applicant type is resolved correctly
    type_of_applicant_code = context.get("type_of_applicant", "Not Provided")
    context["type_of_applicant"] = next(
        (app["name"] for app in applicant_types if app["code"] == type_of_applicant_code),
        "Not Provided"
    )
    context["eo_review_check"] = "✔" if context.get("eo_review_check") == "Yes" else "☐"
    context["eo_review_date"] = context.get("eo_review_date", "Not Provided") if context.get("eo_review_check") == "✔" else "Not Applicable"
    context["eo_not_selected"] = "✔" if context.get("eo_not_selected") == "Yes" else "☐"
    context["eo_not_covered"] = "✔" if context.get("eo_not_covered") == "Yes" else "☐"
    context["certification_agree"] = "✔" if context.get("certification_agree") == "Yes" else "☐"
    context["attachment_agree"] = "✔" if context.get("attachment_agree") == "Yes" else "☐"
    context["sflll_attachment"] = context.get("sflll_attachment", "No file uploaded")
    context["pre_application_attachment"] = context.get("pre_application_attachment", "No file uploaded")
    context["cover_letter_attachment"] = context.get("cover_letter_attachment", "No file uploaded")
    # Include org_id and form_id in the context
    context["org_id"] = org_id
    context["form_id"] = form_id
    return render(request, "admin/sf424_answers.html", context)

def sf424_submit(request, org_id, form_id):
    if request.method == "POST":
        package_id = request.POST.get("package_id", "").strip()

        if not package_id or not package_id.isdigit():
            messages.error(request, "Error: Missing or invalid package ID.")
            return redirect("organization_dashboard", org_id=org_id)

        package_id = int(package_id)
        
        # Try to get project ID from POST data, GET data, or session
        project_id = request.POST.get("project_id") or request.GET.get("project_id") or request.session.get("project_id")
        
        if not project_id:
            opportunity = Opportunity.objects.filter(form_package_id=package_id).first()
            project = opportunity.project if opportunity else None
            project_id = project.id if project else None
            if project_id:
                request.session["project_id"] = project_id  # Save to session for consistency
        
        try:
            project = Project.objects.get(id=project_id)
            print(f"✅ Project found: ID {project.id}, Name: {project.name}")
        except Project.DoesNotExist:
            print(f"❌ Project not found: ID {project_id}")
            messages.error(request, "Error: Project not found.")
            return HttpResponse("Project not found", status=404)

        print(f"✅ Processing SF-424 Submission: org_id={org_id}, form_id={form_id}, package_id={package_id}, project_id={project_id}")

        # Handle file uploads
        def get_uploaded_file(file_field):
            if file_field in request.FILES:
                uploaded_file = request.FILES[file_field]
                file_name = uploaded_file.name
                file_path = os.path.join(settings.MEDIA_ROOT, 'uploads', file_name)

                os.makedirs(os.path.dirname(file_path), exist_ok=True)

                with open(file_path, 'wb+') as destination:
                    for chunk in uploaded_file.chunks():
                        destination.write(chunk)

                print(f"📂 Saved {file_field}: {file_path}")
                return f"/media/uploads/{file_name}"
            return "No file uploaded"
        sf424_data = {
            "submission_types": request.POST.getlist("submission_type"),
            "application_types": request.POST.getlist("application_type"),
            "agency_routing_identifier": request.POST.get("agencyRoutingIdentifier", "Not Provided"),
            "previous_grants_gov_tracking_id": request.POST.get("previousGrantsGovTrackingID", "Not Provided"),
            "revision_type": request.POST.getlist("revision_type"),
            "date_submitted": request.POST.get("dateSubmitted", "Not Provided"),
            "applicant_identifier": request.POST.get("applicantIdentifier", "Not Provided"),
            "date_received_by_state": request.POST.get("dateReceivedState", "Not Provided"),
            "state_application_identifier": request.POST.get("stateApplicationIdentifier", "Not Provided"),
            "federal_identifier": request.POST.get("federalIdentifier", "Not Provided"),
            "agency_routing_number": request.POST.get("agencyRoutingIdentifier", "Not Provided"),
            "previous_tracking_id": request.POST.get("previousGrantsGovTrackingID", "Not Provided"),
            "uei": request.POST.get("uei", "Not Provided"),
            "legal_name": request.POST.get("legalName", "Not Provided"),
            "department": request.POST.get("department", "Not Provided"),
            "division": request.POST.get("division", "Not Provided"),
            "address_street1": request.POST.get("street1", "Not Provided"),
            "address_street2": request.POST.get("street2", "Not Provided"),
            "city": request.POST.get("city", "Not Provided"),
            "county": request.POST.get("county", "Not Provided"),
            "province": request.POST.get("province", "Not Provided"),
            "zip_code": request.POST.get("zipPostal", "Not Provided"),
            "country": request.POST.get("country", "Not Provided"),
            "state": request.POST.get("state", "Not Provided"),
            "prefix": request.POST.get("prefix", "Not Provided"),
            "first_name": request.POST.get("firstName", "Not Provided"),
            "middle_name": request.POST.get("middleName", "Not Provided"),
            "last_name": request.POST.get("lastName", "Not Provided"),
            "contact_street1": request.POST.get("contactStreet1", "Not Provided"),
            "contact_street2": request.POST.get("contactStreet2", "Not Provided"),
            "contact_zip": request.POST.get("contactZipPostal", "Not Provided"),
            "contact_state": request.POST.get("contactState", "Not Provided"),
            "contact_province": request.POST.get("contactProvince", "Not Provided"),
            "contact_country": request.POST.get("contactCountry", "Not Provided"),
            "contact_city": request.POST.get("contactCity", "Not Provided"),
            "contact_county": request.POST.get("contactCounty", "Not Provided"),
            "contact_fax": request.POST.get("contactFax", "Not Provided"),
            "contact_phone": request.POST.get("contactPhone", "Not Provided"),
            "contact_email": request.POST.get("contactEmail", "Not Provided"),
            "ein_tin": request.POST.get("einTin", "Not Provided"),
            "federal_agency": request.POST.get("federalAgency", "Not Provided"),
            "assistance_listing_number": request.POST.get("assistanceListingNumber", "Not Provided"),
            "assistance_listing_title": request.POST.get("assistanceListingTitle", "Not Provided"),
            "project_title": request.POST.get("projectTitle", "Not Provided"),
            "congressional_district": request.POST.get("congressionalDistrict", "Not Provided"),
            "start_date": request.POST.get("startDate", "Not Provided"),
            "end_date": request.POST.get("endDate", "Not Provided"),
            "total_federal_funds": request.POST.get("totalFederalFunds", "0.00"),
            "total_non_federal_funds": request.POST.get("totalNonFederalFunds", "0.00"),
            "total_combined_funds": request.POST.get("totalCombinedFunds", "0,00"),
            "estimated_income": request.POST.get("estimatedIncome", "0.00"),
            "eo_review_check": request.POST.get("eo_review_check", "No"),
            "eo_review_date": request.POST.get("eo_review_date", "Not Provided") if request.POST.get("eo_review_check") else "Not Applicable",
            "eo_not_covered": request.POST.get("eo_not_covered", "No"),
            "eo_not_selected": request.POST.get("eo_not_selected", "No"),
            "pi_prefix": request.POST.get("piPrefix", "Not Provided"),
            "pi_first_name": request.POST.get("piFirstName", "Not Provided"),
            "pi_middle_name": request.POST.get("piMiddleName", "Not Provided"),
            "pi_last_name": request.POST.get("piLastName", "Not Provided"),
            "pi_suffix": request.POST.get("piSuffix", "Not Provided"),
            "pi_position": request.POST.get("piPosition", "Not Provided"),
            "pi_organization": request.POST.get("piOrganization", "Not Provided"),
            "pi_department": request.POST.get("piDepartment", "Not Provided"),
            "pi_division": request.POST.get("piDivision", "Not Provided"),
            "pi_street1": request.POST.get("piStreet1", "Not Provided"),
            "pi_street2": request.POST.get("piStreet2", "Not Provided"),
            "pi_city": request.POST.get("piCity", "Not Provided"),
            "pi_county": request.POST.get("piCounty", "Not Provided"),
            "pi_state": request.POST.get("piState", "Not Provided"),
            "pi_province": request.POST.get("piProvince", "Not Provided"),
            "pi_country": request.POST.get("piCountry", "Not Provided"),
            "pi_zip_postal": request.POST.get("piZipPostal", "Not Provided"),
            "pi_phone": request.POST.get("piPhone", "Not Provided"),
            "pi_fax": request.POST.get("piFax", "Not Provided"),
            "pi_email": request.POST.get("piEmail", "Not Provided"),
            "certification_agree": request.POST.get("certification_agree", "No"),
            "attachment_agree": request.POST.get("attachment_agree", "No"),
            # ✅ New: Store Uploaded File Name
            "sflll_attachment": get_uploaded_file("sflllAttachment"),
            "pre_application_attachment": get_uploaded_file("preApplicationAttachment"),
            "cover_letter_attachment": get_uploaded_file("coverLetterAttachment"),
            "auth_rep_prefix": request.POST.get("authRepPrefix", "Not Provided"),
            "auth_rep_first_name": request.POST.get("authRepFirstName", "Not Provided"),
            "auth_rep_middle_name": request.POST.get("authRepMiddleName", "Not Provided"),
            "auth_rep_last_name": request.POST.get("authRepLastName", "Not Provided"),
            "auth_rep_suffix": request.POST.get("authRepSuffix", "Not Provided"),
            "authorizedRepTitle": request.POST.get("authRepPosition", "Not Provided"),
            "auth_rep_organization": request.POST.get("authRepOrganization", "Not Provided"),
            "auth_rep_department": request.POST.get("authRepDepartment", "Not Provided"),
            "auth_rep_division": request.POST.get("authRepDivision", "Not Provided"),
            "auth_rep_street1": request.POST.get("authRepStreet1", "Not Provided"),
            "auth_rep_street2": request.POST.get("authRepStreet2", "Not Provided"),
            "auth_rep_city": request.POST.get("authRepCity", "Not Provided"),
            "auth_rep_county": request.POST.get("authRepCounty", "Not Provided"),
            "auth_rep_state": request.POST.get("authRepState", "Not Provided"),
            "auth_rep_province": request.POST.get("authRepProvince", "Not Provided"),
            "auth_rep_country": request.POST.get("authRepCountry", "Not Provided"),
            "auth_rep_zip_postal": request.POST.get("authRepZipPostal", "Not Provided"),
            "auth_rep_phone": request.POST.get("authRepPhone", "Not Provided"),
            "auth_rep_fax": request.POST.get("authRepFax", "Not Provided"),
            "auth_rep_email": request.POST.get("authRepEmail", "Not Provided"),
            "auth_rep_signature": request.POST.get("authRepSignature", "Not Provided"),
            "date_signed": request.POST.get("authRepDateSigned", "Not Provided"),
        }
        if "save_draft" in request.POST:
            try:
                draft, created = SubmittedPackage.objects.get_or_create(
                    user=request.user,
                    org_id=org_id,
                    package_id=package_id,
                    project=project,  # Link to the correct project
                    is_draft=True,
                    defaults={
                        "submission_name": f"Draft - {project.name if project else 'Unknown'}",
                        "submission_date": timezone.now(),
                        "sf424_data": sf424_data,
                    }
                )

                # Update if draft already exists
                if not created:
                    draft.submission_name = f"Draft - {project.name if project else 'Unknown'}"
                    draft.submission_date = timezone.now()
                    draft.sf424_data = sf424_data
                    draft.save()

                print(f"✅ Draft saved successfully for user {request.user.username}, package ID {package_id}, project ID {project_id}")
                messages.success(request, "SF-424 draft saved successfully.")
                return redirect("specific_project_home", org_id=org_id, project_id=project_id)

            except Exception as e:
                print(f"❌ Error saving SF-424 draft: {str(e)}")
                messages.error(request, f"Error saving SF-424 draft: {str(e)}")
                return redirect("package_display", org_id=org_id, package_id=package_id)

        # Store data in session
        session_key = f"sf424_data_{org_id}_{package_id}"
        request.session[session_key] = sf424_data
        request.session.modified = True

        print(f"✅ Redirecting to summary for project ID {project_id}")
        return redirect("package_summary", org_id=org_id, package_id=package_id)

    print("❗ Invalid request method")
    return redirect("package_display", org_id=org_id, package_id=package_id)

def generate_pdf(request):
    # Render the HTML with Django template context
    html_string = render_to_string("SF424_Answers.html", {})  # Pass context if needed

    # Create a PDF file
    pdf_file = tempfile.NamedTemporaryFile(delete=True)
    HTML(string=html_string).write_pdf(pdf_file.name)

    # Return as a downloadable response
    with open(pdf_file.name, "rb") as pdf:
        response = HttpResponse(pdf.read(), content_type="application/pdf")
        response["Content-Disposition"] = "attachment; filename=SF424_Answers.pdf"
        return response
    


def download_sf424_pdf(request):
    """ Generate and serve the SF424 Answers form as a downloadable PDF """

    # Render the HTML template with context
    html_string = render_to_string("admin/Sf424_Answers.html", {})

    # Create a temporary file for the PDF
    with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as pdf_file:
        HTML(string=html_string).write_pdf(pdf_file.name)

        # Serve the file as a response
        with open(pdf_file.name, "rb") as pdf:
            response = HttpResponse(pdf.read(), content_type="application/pdf")
            response["Content-Disposition"] = 'attachment; filename="Sf424_Answers.pdf"'
            return response
@login_required
def download_filled_sf424_pdf(request, org_id, form_id):
    """Generate and serve the filled SF-424 form as a downloadable PDF"""
    import json

    # ✅ Fetch the most recent submission for this package
    submission = SubmittedPackage.objects.filter(
        org_id=org_id, package_id=form_id, user=request.user
    ).order_by('-submission_date').first()
    

    if not submission:
        messages.error(request, "No SF-424 data available for this submission.")
        return redirect("view_submission", org_id=org_id, submission_id=form_id)

    # ✅ Fetch SF-424 data from the stored submission
    sf424_data = submission.sf424_data if submission and submission.sf424_data else {}

    # ✅ Convert JSON string to dictionary if necessary
    if isinstance(sf424_data, str):
        sf424_data = json.loads(sf424_data)
    sf424_data["sflll_attachment"] = sf424_data.get("sflll_attachment", "No file uploaded")
    sf424_data["pre_application_attachment"] = sf424_data.get("pre_application_attachment", "No file uploaded")
    sf424_data["cover_letter_attachment"] = sf424_data.get("cover_letter_attachment", "No file uploaded")
    # ✅ Debugging: Print stored values
    print(f"📌 SF-424 Data Retrieved for PDF: {sf424_data}")

    # ✅ Render HTML with SF-424 data
    html_string = render_to_string(
        "admin/Sf424_Answers.html",
        {
            "sf424_data": sf424_data,
            "submission": submission,
            "org_id": org_id,
            "form_id": form_id,
        },
    )

    # ✅ Define PDF styles
    pdf_css = CSS(string="""
        @page { size: Letter; margin: 0.5in; }
        body { font-family: 'Times New Roman', serif; font-size: 10pt; margin: 0; }
        table { width: 100%; border-collapse: collapse; font-size: 9pt; }
        td, th { border: 1px solid black; padding: 4px; word-wrap: break-word; }
        input { border: none; background: transparent; width: 100%; font-size: 9pt; }
        .TableHeader { font-weight: bold; background-color: #f0f0f0; }
        .page-break { page-break-before: always; }
    """)

    # ✅ Generate and serve PDF
    with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as pdf_file:
        HTML(string=html_string).write_pdf(pdf_file.name, stylesheets=[pdf_css])

        with open(pdf_file.name, "rb") as pdf:
            response = HttpResponse(pdf.read(), content_type="application/pdf")
            response["Content-Disposition"] = 'attachment; filename="SF424_Filled.pdf"'
            return response

def rr_budget(request):
    with open(name_titles_path, "r", encoding="utf-8") as f:
        name_titles = json.load(f)
    
    if request.method == "POST":
        # Collect form data
        rr_budget_data = request.POST.dict()
        budget_periods = []
        period_count = int(request.POST.get("period_count", 1))  # Ensure we get the number of periods
        
        for i in range(1, period_count + 1):
            period_data = {
                "period_number": i,
                "uei": request.POST.get(f"uei_{i}", "Not Provided"),
                "organization_name": request.POST.get(f"organization_name_{i}", "Not Provided"),
                "start_date": request.POST.get(f"start_date_{i}", "").strip(),
                "end_date": request.POST.get(f"end_date_{i}", "").strip(),
                "budget_type": request.POST.get(f"budget_type_{i}", "project"),
                "other_personnel": {},  #
                "direct_costs": {
                    "materials_supplies": float(request.POST.get(f"materials_supplies_{i}", 0) or 0),
                    "publication_costs": float(request.POST.get(f"publication_costs_{i}", 0) or 0),
                    "consultant_services": float(request.POST.get(f"consultant_services_{i}", 0) or 0),
                    "adp_computer_services": float(request.POST.get(f"adp_computer_services_{i}", 0) or 0),
                    "subawards_contractual_costs": float(request.POST.get(f"subawards_contractual_costs_{i}", 0) or 0),
                    "equipment_rental_fees": float(request.POST.get(f"equipment_rental_fees_{i}", 0) or 0),
                    "alterations_renovations": float(request.POST.get(f"alterations_renovations_{i}", 0) or 0),
                    "other_1": float(request.POST.get(f"other1_{i}", 0) or 0),
                    "other_2": float(request.POST.get(f"other2_{i}", 0) or 0),
                    "other_3": float(request.POST.get(f"other3_{i}", 0) or 0),
                    "other_4": float(request.POST.get(f"other4_{i}", 0) or 0),
                    "other_5": float(request.POST.get(f"other5_{i}", 0) or 0),
                    "other_6": float(request.POST.get(f"other6_{i}", 0) or 0),
                    "other_7": float(request.POST.get(f"other7_{i}", 0) or 0),
                    "other_8": float(request.POST.get(f"other8_{i}", 0) or 0),
                    "other_9": float(request.POST.get(f"other9_{i}", 0) or 0),
                    "other_10": float(request.POST.get(f"other10_{i}", 0) or 0),
                    "custom_costs": [],
                },
            }
            for j in range(1, 11):  # 8-17
                cost_name = request.POST.get(f"custom_cost_name_{i}_{j}", "").strip()
                cost_funds = float(request.POST.get(f"custom_cost_funds_{i}_{j}", 0) or 0)

                period_data["direct_costs"]["custom_costs"].append({
                    "name": cost_name if cost_name else f"Custom Cost {j+7}",
                    "funds_requested": cost_funds,
                })

            # Calculate total other direct costs including custom costs
            period_data["direct_costs"]["total_other_direct_costs"] = (
                sum(period_data["direct_costs"][key] for key in period_data["direct_costs"] if key != "custom_costs")
                + sum(item["funds_requested"] for item in period_data["direct_costs"]["custom_costs"])
            )


            # Store predefined roles
            predefined_roles = ["postdoc", "grad", "undergrad", "secretarial"]
            for role in predefined_roles:
                period_data["other_personnel"][role] = {
                    "role": {"postdoc": "Post Doctoral Student", "grad": "Graduate Student",
                             "undergrad": "Undergraduate Student", "secretarial": "Clerical"}[role],
                    "num": request.POST.get(f"num_personnel_{role}_{i}", "0"),
                    "calendar_months": request.POST.get(f"calendar_months_{role}_{i}", "0"),
                    "academic_months": request.POST.get(f"academic_months_{role}_{i}", "0"),
                    "summer_months": request.POST.get(f"summer_months_{role}_{i}", "0"),
                    "requested_salary": request.POST.get(f"requested_salary_{role}_{i}", "0"),
                    "fringe_benefits": request.POST.get(f"fringe_benefits_{role}_{i}", "0"),
                    "funds_requested": float(request.POST.get(f"requested_salary_{role}_{i}", "0")) +
                                       float(request.POST.get(f"fringe_benefits_{role}_{i}", "0")),
                }
            custom_roles = request.POST.getlist(f"custom_role_{i}[]")
            num_personnel_list = request.POST.getlist(f"num_personnel_custom_{i}[]")
            calendar_months_list = request.POST.getlist(f"calendar_months_custom_{i}[]")
            academic_months_list = request.POST.getlist(f"academic_months_custom_{i}[]")
            summer_months_list = request.POST.getlist(f"summer_months_custom_{i}[]")
            requested_salary_list = request.POST.getlist(f"requested_salary_custom_{i}[]")
            fringe_benefits_list = request.POST.getlist(f"fringe_benefits_custom_{i}[]")
            for j in range(len(custom_roles)):
                if custom_roles[j].strip():
                    period_data["other_personnel"][f"custom_{j+1}"] = {
                        "role": custom_roles[j],
                        "num": int(num_personnel_list[j] or 0),
                        "calendar_months": calendar_months_list[j],
                        "academic_months": academic_months_list[j],
                        "summer_months": summer_months_list[j],
                        "requested_salary": requested_salary_list[j],
                        "fringe_benefits": fringe_benefits_list[j],
                        "funds_requested": float(requested_salary_list[j] or 0) + float(fringe_benefits_list[j] or 0),
                    }



            budget_periods.append(period_data)

        # Store data in session (temporary storage)
        
        request.session["rr_budget_data"] = budget_periods

        # Redirect to the RR Budget Answered page
        return redirect('RR_Budget_Answers')

    return render(request, "admin/RR_Budget.html", {
        "prefixes": name_titles["prefixes"],
        "suffixes": name_titles["suffixes"],
    })
def rr_budget_answers(request, org_id, package_id):
    """Processes and saves RR Budget answers for a package submission."""
    if request.method == "POST":
        period_count = int(request.POST.get("period_count", 1))
        budget_periods = []
        cumulative_totals = {
            "total_funds_senior_key_persons": 0,
            "total_other_personnel": 0,
            "total_equipment_cost": 0,
            "total_travel_cost": 0,
            "total_domestic_travel": 0,  
            "total_foreign_travel": 0,  
            "total_participant_support_costs": 0,  
            "total_other_direct_costs": 0,
            "total_direct_costs": 0,
            "total_indirect_costs": 0,
            "total_direct_indirect_costs": 0,
            "total_fees": 0,
            "total_cost_with_fee": 0
        }

        for i in range(1, period_count + 1):
            uei = request.POST.get(f"uei_{i}", "Not Provided")
            start_date = request.POST.get(f"start_date_{i}", "").strip()
            end_date = request.POST.get(f"end_date_{i}", "").strip()
            total_direct_costs = float(request.POST.get(f"total_direct_costs_{i}", 0) or 0)
            total_indirect_costs = float(request.POST.get(f"total_indirect_costs_{i}", 0) or 0)
            fee = float(request.POST.get(f"fee_{i}", "0") or 0)
            total_cost_with_fee = total_direct_costs + total_indirect_costs + fee

            # ✅ Print extracted values for debugging
            print(f"📌 Budget Period {i}")
            print(f"    UEI: {uei}")
            print(f"    Start Date: {start_date}")
            print(f"    End Date: {end_date}")
            print(f"    Total Direct Costs: {total_direct_costs}")
            print(f"    Total Indirect Costs: {total_indirect_costs}")
            print(f"    Fee: {fee}")
            print(f"    Total Cost with Fee: {total_cost_with_fee}")

            # ✅ Extract Senior/Key Personnel
            senior_key_persons = []
            total_funds_senior_key_persons = 0
            first_names = request.POST.getlist(f"first_name_{i}[]")
            last_names = request.POST.getlist(f"last_name_{i}[]")
            requested_salaries = request.POST.getlist(f"requested_salary_{i}[]")
            fringe_benefits = request.POST.getlist(f"fringe_benefits_{i}[]")
            project_roles = request.POST.getlist(f"project_role_{i}[]")

            for j in range(len(first_names)):
                if first_names[j].strip():
                    requested_salary = float(requested_salaries[j] or 0)
                    fringe_benefit = float(fringe_benefits[j] or 0)
                    funds_requested = requested_salary + fringe_benefit

                    senior_key_persons.append({
                        "first_name": first_names[j],
                        "last_name": last_names[j] if j < len(last_names) else "",
                        "requested_salary": requested_salary,
                        "fringe_benefits": fringe_benefit,
                        "funds_requested": funds_requested,
                        "project_role": project_roles[j] if j < len(project_roles) else "",
                    })
                    total_funds_senior_key_persons += funds_requested  

            # ✅ Print Senior/Key Personnel for debugging
            print(f"    Senior/Key Personnel: {senior_key_persons}")

            # ✅ Travel Costs
            domestic_travel = float(request.POST.get(f"domestic_travel_cost_{i}", "0") or 0)
            foreign_travel = float(request.POST.get(f"foreign_travel_cost_{i}", "0") or 0)
            total_travel = domestic_travel + foreign_travel

            travel_data = {
                "domestic_costs": domestic_travel,
                "foreign_costs": foreign_travel,
                "total_travel_cost": total_travel
            }

            # ✅ Store Period Data
            period_data = {
                "period_number": i,
                "uei": uei,
                "organization_name": request.POST.get(f"organization_name_{i}", "Not Provided"),
                "start_date": start_date,
                "end_date": end_date,
                "senior_key_persons": senior_key_persons,
                "total_funds_senior_key_persons": total_funds_senior_key_persons,  
                "total_travel_cost": total_travel,
                "travel": travel_data,
                "total_direct_costs": total_direct_costs,
                "total_indirect_costs": total_indirect_costs,
                "total_direct_indirect_costs": total_direct_costs + total_indirect_costs,
                "fee": fee,
                "total_cost_with_fee": total_cost_with_fee
            }
            budget_periods.append(period_data)

            # ✅ Accumulate Cumulative Totals
            cumulative_totals["total_funds_senior_key_persons"] += total_funds_senior_key_persons
            cumulative_totals["total_travel_cost"] += total_travel
            cumulative_totals["total_direct_costs"] += total_direct_costs
            cumulative_totals["total_indirect_costs"] += total_indirect_costs
            cumulative_totals["total_direct_indirect_costs"] += total_direct_costs + total_indirect_costs
            cumulative_totals["total_fees"] += fee
            cumulative_totals["total_cost_with_fee"] += total_cost_with_fee
        
        

        # ✅ Save Data in Session
        session_key_budget = f"budget_periods_{org_id}_{package_id}"
        session_key_cumulative = f"cumulative_totals_{org_id}_{package_id}"

        request.session[session_key_budget] = budget_periods
        request.session[session_key_cumulative] = cumulative_totals
        request.session.modified = True  
        package = get_object_or_404(FormPackage, id=package_id, organization_id=org_id)
        package_type = package.package_type

         # Determine the appropriate summary URL
        if package_type == "rr_budget_only":
            return redirect('rr_budget_summary', org_id=org_id, package_id=package_id)
        elif package_type == "combined":
            return redirect('package_summary', org_id=org_id, package_id=package_id)
        elif package_type == "sf424_only":
            return redirect('sf424_summary', org_id=org_id, package_id=package_id)
        else:
            # Fallback to combined summary if package type is unknown
            return redirect('package_summary', org_id=org_id, package_id=package_id)

@login_required
def rr_budget_submit(request, org_id, package_id):
    """Processes and saves RR Budget form submission."""
    if request.method == "POST":
       
        
        period_count = int(request.POST.get("period_count", 1))
        budget_periods = []
        cumulative_totals = {
            "total_funds_senior_key_persons": 0,
            "total_other_personnel": 0,
            "total_equipment_cost": 0,
            "total_travel_cost": 0,
            "total_domestic_travel": 0,
            "total_foreign_travel": 0,
            "total_participant_support_costs": 0,
            "total_other_direct_costs": 0,
            "total_direct_costs": 0,
            "total_indirect_costs": 0,
            "total_direct_indirect_costs": 0,
            "total_fees": 0,
            "total_cost_with_fee": 0
        }

        for i in range(1, period_count + 1):
            uei = request.POST.get(f"uei_{i}", "Not Provided")
            start_date = request.POST.get(f"start_date_{i}", "").strip()
            end_date = request.POST.get(f"end_date_{i}", "").strip()
            total_indirect_costs = float(request.POST.get(f"total_indirect_costs_{i}", 0) or 0)
            fee = float(request.POST.get(f"fee_{i}", "0") or 0)
            total_direct_costs = float(request.POST.get(f"total_direct_costs_{i}", 0) or 0)
            
            senior_key_persons = []
            total_funds_senior_key_persons = 0
            first_names = request.POST.getlist(f"first_name_{i}[]")
            last_names = request.POST.getlist(f"last_name_{i}[]")
            requested_salaries = request.POST.getlist(f"requested_salary_{i}[]")
            fringe_benefits = request.POST.getlist(f"fringe_benefits_{i}[]")
            project_roles = request.POST.getlist(f"project_role_{i}[]")
            domestic_travel = float(request.POST.get(f"domestic_travel_cost_{i}", "0") or 0)
            foreign_travel = float(request.POST.get(f"foreign_travel_cost_{i}", "0") or 0)
            total_travel = domestic_travel + foreign_travel  # ✅ Ensure total is calculated
            indirect_costs = []
            total_indirect_costs = 0
            indirect_cost_types = request.POST.getlist(f"indirect_cost_type_{i}[]")
            indirect_cost_rates = request.POST.getlist(f"indirect_cost_rate_{i}[]")
            indirect_cost_bases = request.POST.getlist(f"indirect_cost_base_{i}[]")
            indirect_funds_requested = request.POST.getlist(f"indirect_funds_requested_{i}[]")
            for j in range(len(indirect_cost_types)):
                if indirect_cost_types[j].strip():
                    rate = float(indirect_cost_rates[j] or 0)
                    base = float(indirect_cost_bases[j] or 0)
                    funds_requested = float(indirect_funds_requested[j] or 0)

                    indirect_costs.append({
                        "type": indirect_cost_types[j],
                        "rate": rate,
                        "base": base,
                        "funds_requested": funds_requested
                    })

                    total_indirect_costs += funds_requested

            for j in range(len(first_names)):
                if first_names[j].strip():
                    requested_salary = float(requested_salaries[j] or 0)
                    fringe_benefit = float(fringe_benefits[j] or 0)
                    funds_requested = requested_salary + fringe_benefit

                    senior_key_persons.append({
                        "first_name": first_names[j],
                        "last_name": last_names[j] if j < len(last_names) else "",
                        "requested_salary": requested_salary,
                        "fringe_benefits": fringe_benefit,
                        "funds_requested": funds_requested,
                        "project_role": project_roles[j] if j < len(project_roles) else "",
                    })
                    total_funds_senior_key_persons += funds_requested  

            # ✅ Other Personnel
            other_personnel = []
            total_other_personnel = 0
            personnel_roles = ["postdoc", "grad", "undergrad", "secretarial"]

            for role in personnel_roles:
                num_personnel = int(request.POST.get(f"num_personnel_{role}_{i}", 0) or 0)
                requested_salary = float(request.POST.get(f"requested_salary_{role}_{i}", 0) or 0)
                fringe_benefits = float(request.POST.get(f"fringe_benefits_{role}_{i}", 0) or 0)
                funds_requested = requested_salary + fringe_benefits

                if num_personnel > 0:
                    other_personnel.append({
                        "role": role.capitalize(),
                        "num": num_personnel,
                        "requested_salary": requested_salary,
                        "fringe_benefits": fringe_benefits,
                        "funds_requested": funds_requested
                    })
                    total_other_personnel += funds_requested

            # ✅ Equipment
            equipment = []
            total_equipment_cost = 0
            equipment_items = request.POST.getlist(f"equipment_item_{i}[]")
            equipment_funds = request.POST.getlist(f"equipment_funds_requested_{i}[]")

            for j in range(len(equipment_items)):
                if equipment_items[j].strip():
                    funds_requested = float(equipment_funds[j] or 0)
                    equipment.append({"item": equipment_items[j], "funds_requested": funds_requested})
                    total_equipment_cost += funds_requested

            # ✅ Travel Costs
            domestic_travel = float(request.POST.get(f"domestic_travel_cost_{i}", "0") or 0)
            foreign_travel = float(request.POST.get(f"foreign_travel_cost_{i}", "0") or 0)
            total_travel = domestic_travel + foreign_travel

            # ✅ Participant/Trainee Support Costs
            trainee_costs = {
                "tuition_fees": float(request.POST.get(f"tuition_fees_health_insurance_{i}", "0") or 0),
                "stipends": float(request.POST.get(f"stipends_{i}", "0") or 0),
                "trainee_travel": float(request.POST.get(f"trainee_travel_{i}", "0") or 0),
                "subsistence": float(request.POST.get(f"subsistence_{i}", "0") or 0),
                "other_costs": float(request.POST.get(f"other_cost_funds_{i}", "0") or 0),
                "num_participants": int(request.POST.get(f"num_participants_trainees_{i}", "0") or 0),
            }
            trainee_costs["total_support_costs"] = sum(trainee_costs.values())
            direct_costs = {
                "materials_supplies": float(request.POST.get(f"materials_supplies_{i}", "0") or 0),
                "publication_costs": float(request.POST.get(f"publication_costs_{i}", "0") or 0),
                "consultant_services": float(request.POST.get(f"consultant_services_{i}", "0") or 0),
                "adp_computer_services": float(request.POST.get(f"adp_computer_services_{i}", "0") or 0),
                "subawards_contractual_costs": float(request.POST.get(f"subawards_contractual_costs_{i}", "0") or 0),
                "equipment_rental_fees": float(request.POST.get(f"equipment_rental_fees_{i}", "0") or 0),
                "alterations_renovations": float(request.POST.get(f"alterations_renovations_{i}", "0") or 0),
                "other_1": float(request.POST.get(f"other_1_{i}", "0") or 0),
                "other_2": float(request.POST.get(f"other_2_{i}", "0") or 0),
                "other_3": float(request.POST.get(f"other_3_{i}", "0") or 0),
                "other_4": float(request.POST.get(f"other_4_{i}", "0") or 0),
                "other_5": float(request.POST.get(f"other_5_{i}", "0") or 0),
                "other_6": float(request.POST.get(f"other_6_{i}", "0") or 0),
                "other_7": float(request.POST.get(f"other_7_{i}", "0") or 0),
                "other_8": float(request.POST.get(f"other_8_{i}", "0") or 0),
                "other_9": float(request.POST.get(f"other_9_{i}", "0") or 0),
                "other_10": float(request.POST.get(f"other_10_{i}", "0") or 0),
            }
            total_other_direct_costs = sum(direct_costs.values())
            total_direct_costs = (
                total_funds_senior_key_persons +  # Part A: Senior Key Personnel
                total_other_personnel +           # Part B: Other Personnel
                total_equipment_cost +            # Part C: Equipment
                total_travel +                     # Part D: Travel
                trainee_costs["total_support_costs"] +  # Part E: Participant Support
                total_other_direct_costs           # Part F: Other Direct Costs
            )
            total_cost_with_fee = total_direct_costs + total_indirect_costs + fee
            # ✅ Budget Period Data
            period_data = {
                "period_number": i,
                "uei": uei,
                "organization_name": request.POST.get(f"organization_name_{i}", "Not Provided"),
                "start_date": start_date,
                "end_date": end_date,
                "senior_key_persons": senior_key_persons,
                "total_funds_senior_key_persons": total_funds_senior_key_persons,  
                "other_personnel": other_personnel,
                "total_other_personnel": total_other_personnel,
                "equipment": equipment,
                "direct_costs": direct_costs,  
                "total_other_direct_costs": total_other_direct_costs,
                "total_equipment_cost": total_equipment_cost,
                "total_travel_cost": total_travel,
                "total_domestic_travel": domestic_travel,  # ✅ Store explicitly
                "total_foreign_travel": foreign_travel,

                "trainee_costs": trainee_costs,
                "total_participant_support_costs": trainee_costs["total_support_costs"],
                "indirect_costs": indirect_costs,  # ✅ Now properly stored
                "total_indirect_costs": total_indirect_costs,
                "total_direct_costs": total_direct_costs,
                "total_indirect_costs": total_indirect_costs,
                "total_direct_indirect_costs": total_direct_costs + total_indirect_costs,
                "fee": fee,
                "total_cost_with_fee": total_cost_with_fee
            }
            budget_periods.append(period_data)

            # ✅ Update Cumulative Totals
            
            cumulative_totals["total_funds_senior_key_persons"] += total_funds_senior_key_persons
            cumulative_totals["total_other_personnel"] += total_other_personnel
            cumulative_totals["total_equipment_cost"] += total_equipment_cost
            cumulative_totals["total_travel_cost"] += total_travel
            cumulative_totals["total_participant_support_costs"] += trainee_costs["total_support_costs"]
            cumulative_totals["total_other_direct_costs"] += total_other_direct_costs  # ✅ Store cumulative total
            cumulative_totals["total_direct_costs"] += total_direct_costs
            cumulative_totals["total_indirect_costs"] += total_indirect_costs
            cumulative_totals["total_direct_indirect_costs"] += total_direct_costs + total_indirect_costs
            cumulative_totals["total_fees"] += fee
            cumulative_totals["total_cost_with_fee"] += total_cost_with_fee
        if "save_draft" in request.POST:
            try:
                # Get the project and opportunity linked to the package
                opportunity = Opportunity.objects.filter(form_package_id=package_id).first()
                project = opportunity.project if opportunity else None

                # Try to get an existing draft for this user, project, and package
                draft, created = SubmittedPackage.objects.get_or_create(
                    user=request.user,
                    org_id=org_id,
                    package_id=package_id,
                    project=project,  # Include project to make it unique
                    is_draft=True,  # Ensure it matches existing draft entries
                    defaults={
                        "submission_name": f"Draft - {project.name if project else 'Unknown'}",
                        "submission_date": timezone.now(),
                        "budget_periods": budget_periods,
                        "cumulative_totals": cumulative_totals,
                    }
                )

                # If draft already exists, update it
                if not created:
                    draft.submission_name = f"Draft - {project.name if project else 'Unknown'}"
                    draft.submission_date = timezone.now()
                    draft.budget_periods = budget_periods
                    draft.cumulative_totals = cumulative_totals
                    draft.save()

                messages.success(request, "Draft saved successfully.")
                return redirect("specific_project_home", org_id=org_id, project_id=project.id)

            except Exception as e:
                messages.error(request, f"Error saving draft: {str(e)}")
                return redirect("specific_project_home", org_id=org_id, project_id=package_id)

        request.session[f"budget_periods_{org_id}_{package_id}"] = budget_periods
        request.session[f"cumulative_totals_{org_id}_{package_id}"] = cumulative_totals
        request.session.modified = True

        package = get_object_or_404(FormPackage, id=package_id, organization_id=org_id)
        try:
            # Handle both rr_budget and rr_budget_only types
            if package.package_type in ["rr_budget", "rr_budget_only"]:
                # Redirect to the RR Budget Summary page
                summary_url = reverse("package_summary", kwargs={"org_id": org_id, "package_id": package_id})
                print(f"✅ Redirecting to RR Budget Summary: {summary_url}")
                return HttpResponseRedirect(summary_url)
            elif package.package_type == "combined":
                # Redirect to the Combined Summary page
                summary_url = reverse("package_summary", kwargs={"org_id": org_id, "package_id": package_id})
                print(f"✅ Redirecting to Combined Summary: {summary_url}")
                return HttpResponseRedirect(summary_url)
            else:
                print(f"❗ Unknown package type: {package.package_type}")
                return redirect("package_display", org_id=org_id, package_id=package_id)

        except Exception as e:
            print(f"❌ Error in redirecting: {e}")
            messages.error(request, "Error: Could not redirect to the summary page.")
            return redirect("package_display", org_id=org_id, package_id=package_id)



@login_required
def download_rr_budget_pdf(request, org_id, form_id):
    """ Generate and serve the filled RR Budget form as a downloadable PDF """
    # Retrieve the latest submission instead of using `.get()`
    submission = get_object_or_404(SubmittedPackage, id=form_id, user=request.user)
    # Fetch budget data from the latest submission
    budget_periods = submission.budget_periods
    cumulative_totals = submission.cumulative_totals

    # Render the HTML template
    html_string = render_to_string(
        "admin/RR_Budget_Answers.html",
        {
            "budget_periods": budget_periods,
            "cumulative_totals": cumulative_totals,
            "submission": submission,
            "org_id": org_id,  # ✅ Ensure org_id is passed
            "form_id": form_id,  # ✅ Ensure form_id is passed
            "is_cumulative_summary": True
        },
    )

    # Define PDF formatting
    pdf_css = CSS(string="""
        @page { size: Letter; margin: 0.5in; }
        body { font-family: 'Times New Roman', serif; font-size: 10pt; margin: 0; }
        table { width: 100%; border-collapse: collapse; font-size: 9pt; }
        td, th { border: 1px solid black; padding: 4px; word-wrap: break-word; }
        input { border: none; background: transparent; width: 100%; font-size: 9pt; }
        .TableHeader { font-weight: bold; background-color: #f0f0f0; }
        .page-break { page-break-before: always; }
    """)

    # Create a temporary PDF file
    with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as pdf_file:
        HTML(string=html_string).write_pdf(pdf_file.name, stylesheets=[pdf_css])

        # Serve the PDF as a response
        with open(pdf_file.name, "rb") as pdf:
            response = HttpResponse(pdf.read(), content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="RR_Budget_{submission.submission_name}.pdf"'
            return response

@login_required
@user_passes_test(lambda u: u.role in ['admin', 'principal_admin'])
def save_rr_budget(request, org_id, package_id):
    if request.method == "POST":
        print("✅ RR Budget Form Submission Received")

        # 🚀 Ensure RR Budget Form Data is Saved in Session
        session_key_budget = f"budget_periods_{org_id}_{package_id}"
        session_key_cumulative = f"cumulative_totals_{org_id}_{package_id}"

        # Extract and structure budget data from POST request
        budget_periods = []
        cumulative_totals = {
            "total_direct_costs": 0,
            "total_indirect_costs": 0,
            "total_fees": 0,
            "total_cost_with_fee": 0
        }

        period_count = int(request.POST.get("period_count", 0))

        for i in range(1, period_count + 1):
            period_data = {
                "period_number": i,
                "uei": request.POST.get(f"uei_{i}", ""),
                "organization_name": request.POST.get(f"organization_name_{i}", ""),
                "start_date": request.POST.get(f"start_date_{i}", ""),
                "end_date": request.POST.get(f"end_date_{i}", ""),
                "total_direct_costs": float(request.POST.get(f"funds_requested_{i}[]", 0) or 0),
                "total_indirect_costs": float(request.POST.get(f"indirect_funds_requested_{i}[]", 0) or 0),
                "total_cost_with_fee": float(request.POST.get(f"total_cost_with_fee_{i}", 0) or 0),
            }
            budget_periods.append(period_data)

            # Update cumulative totals
            cumulative_totals["total_direct_costs"] += period_data["total_direct_costs"]
            cumulative_totals["total_indirect_costs"] += period_data["total_indirect_costs"]
            cumulative_totals["total_fees"] += float(request.POST.get(f"fee_{i}", 0) or 0)
            cumulative_totals["total_cost_with_fee"] += period_data["total_cost_with_fee"]

        # ✅ Save to session
        request.session[session_key_budget] = budget_periods
        request.session[session_key_cumulative] = cumulative_totals
        request.session.modified = True  # 🔥 Ensure session data is saved

        # 🚀 Debugging Output
        print(f"✅ Saving to session: {session_key_budget} ->", budget_periods)
        print(f"✅ Saving to session: {session_key_cumulative} ->", cumulative_totals)

        return JsonResponse({"message": "RR Budget saved successfully"})
    
@login_required
def package_summary(request, org_id, package_id):
    """Displays all saved forms for review before submission"""

    budget_periods_key = f"budget_periods_{org_id}_{package_id}"
    cumulative_totals_key = f"cumulative_totals_{org_id}_{package_id}"
    sf424_key = f"sf424_data_{org_id}_{package_id}"

    sf424_data = request.session.get(sf424_key, {})
    budget_periods = request.session.get(budget_periods_key, [])
    cumulative_totals = request.session.get(cumulative_totals_key, {})

    # Get the package to determine its type
    package = FormPackage.objects.get(id=package_id)

    # Select the summary template based on package type
    if package.package_type == "sf424_only":
        summary_template = "admin/sf424_summary.html"
    elif package.package_type == "rr_budget_only":
        summary_template = "admin/rr_budget_summary.html"
    else:
        summary_template = "admin/combined_summary.html"

    return render(request, summary_template, {
        "budget_periods": budget_periods,
        "cumulative_totals": cumulative_totals,
        "sf424_data": sf424_data,
        "org_id": org_id,
        "package_id": package_id,
    })

@login_required
def save_draft(request, org_id, package_id, form_id):
    """Save form progress as a draft."""
    if request.method == "POST":
        submission_name = request.POST.get("submission_name", "Draft")

        # Fetch form data from POST request
        sf424_data = request.POST.dict()
        budget_periods = request.session.get(f"budget_periods_{org_id}_{package_id}", [])
        cumulative_totals = request.session.get(f"cumulative_totals_{org_id}_{package_id}", {})

        # Mark as a draft (is_draft=True)
        SubmittedPackage.objects.create(
            user=request.user,
            org_id=org_id,
            package_id=package_id,
            project=None,
            submission_name=submission_name,
            sf424_data=sf424_data,
            budget_periods=budget_periods,
            cumulative_totals=cumulative_totals,
            is_draft=True  # Mark as a draft
        )

        messages.success(request, f"Draft '{submission_name}' saved successfully.")
        return redirect("specific_project_home", org_id=org_id, project_id=package_id)

    return HttpResponse("Invalid request", status=400)

@login_required
def delete_draft(request, org_id, package_id):
    """Delete a saved draft."""
    if request.method == "POST":
        try:
            draft = SubmittedPackage.objects.get(org_id=org_id, package_id=package_id, is_draft=True)
            draft.delete()
            messages.success(request, "Draft deleted successfully.")
        except SubmittedPackage.DoesNotExist:
            messages.error(request, "Draft not found.")

        return redirect("specific_project_home", org_id=org_id, project_id=package_id)

    return HttpResponse("Invalid request", status=400)

@login_required
def submit_package(request, org_id, package_id):
    """Handles submission of a completed package summary."""
    print("Submitting package...")  # Debug Statement

    if request.method == "POST":
        submission_name = request.POST.get("submission_name", "").strip()
        print(f"Submission Name: {submission_name}")  # Debug Statement

        if not submission_name:
            messages.error(request, "Submission name is required.")
            return redirect("package_summary", org_id=org_id, package_id=package_id)

        # Retrieve data from session
        sf424_key = f"sf424_data_{org_id}_{package_id}"
        budget_periods_key = f"budget_periods_{org_id}_{package_id}"
        cumulative_totals_key = f"cumulative_totals_{org_id}_{package_id}"

        sf424_data = request.session.get(sf424_key, {})
        budget_periods = request.session.get(budget_periods_key, [])
        cumulative_totals = request.session.get(cumulative_totals_key, {})
        
        print(f"SF-424 Data: {sf424_data}")  # Debug Statement
        print(f"Budget Periods: {budget_periods}")  # Debug Statement
        print(f"Cumulative Totals: {cumulative_totals}")  # Debug Statement

        # Retrieve the project related to the package
        opportunity = Opportunity.objects.filter(form_package_id=package_id).first()
        print(f"Opportunity: {opportunity}")  # Debug Statement

        if not opportunity:
            messages.error(request, "No opportunity associated with this package.")
            return redirect("package_summary", org_id=org_id, package_id=package_id)

        project = opportunity.project
        print(f"Project: {project}")  # Debug Statement
        
        if not project:
            messages.error(request, "No project associated with this opportunity.")
            return redirect("package_summary", org_id=org_id, package_id=package_id)

        # Save submission to the database
        submitted_package = SubmittedPackage.objects.create(
            user=request.user,
            org_id=org_id,
            package_id=package_id,
            project=project,  # Associate with the project
            submission_name=submission_name,
            sf424_data=sf424_data,
            budget_periods=budget_periods,
            cumulative_totals=cumulative_totals,
        )

        messages.success(request, f"Package '{submission_name}' submitted successfully.")
        print(f"Submission successful, redirecting to project home...")  # Debug Statement

        # Redirect to the specific project home page
        return redirect("specific_project_home", org_id=org_id, project_id=project.id)

    print("Submission method not POST, redirecting to package summary...")  # Debug Statement
    return redirect("package_summary", org_id=org_id, package_id=package_id)
@login_required
def submitted_forms(request, org_id):
    """Displays a list of submitted package summaries."""
    submissions = SubmittedPackage.objects.filter(user=request.user).order_by("-submission_date")
    context = {
        "org_id": org_id,  # Ensure org_id is passed
        "submissions": submissions,
    }
    return render(request, "admin/submitted_forms.html", context)

@login_required
def view_submission(request, org_id, submission_id):
    """Displays details of a submitted package summary."""
    submission = get_object_or_404(SubmittedPackage, id=submission_id, user=request.user)

    # Get the package to determine its type
    package = get_object_or_404(FormPackage, id=submission.package_id, organization_id=org_id)

    context = {
        "submission": submission,
        "sf424_data": submission.sf424_data,
        "budget_periods": submission.budget_periods,
        "cumulative_totals": submission.cumulative_totals,
        "org_id": org_id,
        "form_id": submission.package_id,
        "package_type": package.package_type,  # Pass package type to the template
    }
    return render(request, "admin/view_submission.html", context)

@login_required
def download_combined_pdf(request, org_id, form_id):
    """Generate and serve a combined PDF of SF-424, RR Budget forms, and attachments"""

    try:
        # Fetch the most recent submission
        submission = get_object_or_404(SubmittedPackage, id=form_id, user=request.user)

        # Define PDF CSS styles
        pdf_css = CSS(string="""
            @page { size: Letter; margin: 0.5in; }
            body { font-family: 'Times New Roman', serif; font-size: 10pt; margin: 0; }
            table { width: 100%; border-collapse: collapse; font-size: 9pt; }
            td, th { border: 1px solid black; padding: 4px; word-wrap: break-word; }
            input { border: none; background: transparent; width: 100%; font-size: 9pt; }
            .TableHeader { font-weight: bold; background-color: #f0f0f0; }
            .page-break { page-break-before: always; }
        """)

        # Generate SF-424 PDF in memory
        sf424_html = render_to_string(
            "admin/Sf424_Answers.html",
            {"sf424_data": submission.sf424_data, "submission": submission, "org_id": org_id, "form_id": form_id},
        )
        sf424_pdf = BytesIO()
        HTML(string=sf424_html).write_pdf(sf424_pdf, stylesheets=[pdf_css])
        sf424_pdf.seek(0)

        # Generate RR Budget PDF in memory
        rr_budget_html = render_to_string(
            "admin/RR_Budget_Answers.html",
            {
                "budget_periods": submission.budget_periods,
                "cumulative_totals": submission.cumulative_totals,
                "submission": submission,
                "org_id": org_id,
                "form_id": form_id,
                "is_cumulative_summary": True,
            },
        )
        rr_budget_pdf = BytesIO()
        HTML(string=rr_budget_html).write_pdf(rr_budget_pdf, stylesheets=[pdf_css])
        rr_budget_pdf.seek(0)

        # Initialize PDF merger
        merger = PdfMerger()
        merger.append(sf424_pdf)
        merger.append(rr_budget_pdf)

        # Append uploaded files if present
        # Append uploaded files if present
        file_attachments = [
            ("SFLLL Attachment", submission.sflll_attachment),
            ("Pre-Application Attachment", submission.pre_application_attachment),
            ("Cover Letter Attachment", submission.cover_letter_attachment)
        ] 
        for attachment_name, attachment_file in file_attachments:
            if attachment_file and attachment_file.name:
                try:
                    file_path = attachment_file.path
                    print(f"🔍 Trying to add attachment: {attachment_name}, Path: {file_path}")
            
                    # Check if the file is a PDF
                    if file_path.lower().endswith(".pdf"):
                        with open(file_path, "rb") as file:
                            attachment_pdf = BytesIO(file.read())
                            attachment_pdf.seek(0)
                            merger.append(attachment_pdf)
                            print(f"✅ Successfully added PDF attachment: {attachment_name}")
                    else:
                        print(f"⚠️ Skipping non-PDF file: {attachment_name} ({file_path})")
                except Exception as e:
                    print(f"❌ Error adding {attachment_name}: {e}")
                # Create a combined PDF in memory
        combined_pdf = BytesIO()
        merger.write(combined_pdf)
        merger.close()
        combined_pdf.seek(0)

        # Serve the combined PDF as a response
        response = HttpResponse(combined_pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="combined_submission_{form_id}.pdf"'
        return response

    except Exception as e:
        return HttpResponse(f"Error creating combined PDF: {str(e)}", status=500)
    
def project_dashboard(request, org_id):
    projects = Project.objects.all()

    if request.method == "POST":
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.org_id = org_id  # Set the org_id attribute before saving
            project.project_identifier = project.generate_unique_identifier(org_id)  # Generate identifier
            project.save()
            return redirect('specific_project_home', org_id=org_id, project_id=project.id)
    else:
        form = ProjectForm()

    context = {
        'projects': projects,
        'form': form,
        'org_id': org_id
    }
    return render(request, 'admin/project_dashboard.html', context)
def specific_project_home(request, org_id, project_id):
    project = get_object_or_404(Project, id=project_id)
    submissions = SubmittedPackage.objects.filter(project=project, is_draft=False)
    drafts = SubmittedPackage.objects.filter(project=project, is_draft=True)

    # Fetch unique, valid opportunities not linked to any project or linked to this project
    opportunities = Opportunity.objects.filter(
        form_package__isnull=False,
        number__in=['12345', '67890', '11111']
    ).distinct()

    context = {
        'project': project,
        'org_id': org_id,
        'opportunities': opportunities,
        'submissions': submissions,
        'drafts': drafts,
    }
    return render(request, 'admin/specific_project_home.html', context)

@login_required
def update_project_details(request, org_id, project_id):
    project = get_object_or_404(Project, id=project_id)

    if request.method == "POST":
        # Update project fields from form data
        project.admin_unit = request.POST.get("admin_unit")
        project.sponsor = request.POST.get("sponsor")
        project.instrument_type = request.POST.get("instrument_type")
        project.sponsor_deadline = request.POST.get("sponsor_deadline")
        project.prime_sponsor = request.POST.get("prime_sponsor")
        project.total_sponsor_costs = request.POST.get("total_sponsor_costs")
        project.project_start_date = request.POST.get("project_start_date")
        project.project_end_date = request.POST.get("project_end_date")
        
        # Save the updated project
        project.save()
        messages.success(request, "Project details updated successfully!")
        return redirect("specific_project_home", org_id=org_id, project_id=project_id)

    return redirect("specific_project_home", org_id=org_id, project_id=project_id)

def opportunity_information(request, org_id, project_id, opportunity_number):
    opportunity = get_object_or_404(Opportunity, number=opportunity_number)

    context = {
        'opportunity': opportunity,
        'org_id': org_id,
        'project_id': project_id,
    }
    return render(request, 'admin/opportunity_information.html', context)

def add_opportunity(request, org_id, project_id, opportunity_number):
    project = get_object_or_404(Project, id=project_id)

    # Retrieve the existing opportunity by its number
    opportunity = Opportunity.objects.filter(number=opportunity_number).first()

    if not opportunity:
        return HttpResponse("Opportunity not found", status=404)

    # Check if the opportunity is already linked to the project
    if opportunity.project != project:
        opportunity.project = project
        opportunity.is_added = True  # Mark as added
        opportunity.save()

    # Get the form package from the opportunity
    form_package = opportunity.form_package

    if request.method == 'POST':
        form = OpportunityForm(request.POST)
        if form.is_valid():
            opportunity = form.save(commit=False)
            opportunity.project = project
            opportunity.form_package = form_package

            if not form_package:
                return HttpResponse("No form package associated with this opportunity.", status=400)

            opportunity.is_added = True  # Mark as added
            opportunity.save()
            print(f"Opportunity saved: {opportunity}")  # Debug Statement

            # Redirect to the package display for the chosen package
            return redirect('package_display', org_id=org_id, package_id=form_package.id)
    else:
        form = OpportunityForm()

    return render(request, 'admin/add_opportunity.html', {
        'org_id': org_id,
        'project_id': project_id,
        'opportunity_number': opportunity_number,
        'form': form,
        'form_package': form_package,
    })