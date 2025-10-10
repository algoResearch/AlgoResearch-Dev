from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test, login_required
from dashboard.forms import *
from django.db.models import Q, F, Avg, Max, Min, Count, Prefetch, Sum
from dashboard.models import *
from django.db.models.signals import post_save
from django.views.decorators.http import require_http_methods
from django.contrib.staticfiles import finders
from decimal import Decimal, InvalidOperation
from myapp.utils.pdf_field_mapping import field_positions  # Import the field mapping
import boto3
from django.template.loader import render_to_string
from django.template.defaultfilters import slugify
from weasyprint import HTML, CSS
import tempfile
from collections import defaultdict
from decimal import Decimal
from botocore.exceptions import NoCredentialsError, PartialCredentialsError
from django.dispatch import receiver
import io
from urllib.parse import urlparse, unquote
from reportlab.pdfgen import canvas
import hashlib
from myapp.utils.pdf_processing import generate_filled_pdf
from myapp.utils.save_full_draft import save_full_draft
import decimal
from myapp.utils.get_base_template import get_base_template

from decimal import InvalidOperation
import pdfkit
from django.core.files.storage import default_storage
from django.core.serializers import serialize
from django.core.exceptions import PermissionDenied
from django.core.files import File

from django.forms import modelformset_factory
from django.forms.models import inlineformset_factory
from django.forms import formset_factory
from django.utils import timezone
from django.utils.timezone import make_aware
from django.utils.text import slugify
from django.utils.html import escape
from django.db import IntegrityError, transaction, models
from django.views.decorators.http import require_POST
from django.http import JsonResponse, FileResponse, Http404, HttpResponseNotFound, HttpRequest, HttpResponseRedirect, HttpResponseNotAllowed, HttpResponseBadRequest
import xml.etree.ElementTree as ET
from django.http import HttpResponseForbidden
from django.conf import settings
import requests
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import datetime, timedelta, time
from django.urls import reverse
from django.contrib import messages 
from dashboard.core.pdf_utils import extract_pdf_fields, convert_pdf_to_images
import logging

from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login
from django.http import FileResponse
import os  # To handle file operations (e.g., saving and deleting temporary logo files)
from io import BytesIO  # For in-memory file handling (PDF generation)
from dashboard.models import PDFTemplate, CalendarEvent
from django.conf import settings  # To access project settings like MEDIA_ROOT
from django.shortcuts import render, get_object_or_404, redirect  # Standard shortcuts for rendering templates and managing views
from django.http import HttpResponse, HttpResponseForbidden  # To return HTTP responses, including PDF files or errors
from django.contrib.auth.decorators import login_required, user_passes_test  # To restrict views to logged-in users and superusers
from django.core.files.storage import FileSystemStorage  # For file handling and storage if needed
from PyPDF2 import PdfReader, PdfWriter, PdfMerger
from reportlab.lib.pagesizes import letter  # To set PDF page size
from reportlab.lib.styles import getSampleStyleSheet  # For setting up basic text styles in PDF
from reportlab.lib.units import inch  # To handle unit conversion (e.g., inches for image scaling)
from itertools import islice
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image  # For PDF generation (mainly layout and content elements)
import json


logger = logging.getLogger(__name__)  # Set up a logger for error tracking
def is_admin_or_principal(user):
    return user.role in ['admin', 'principal_admin']

def is_principal_admin(user):
    return user.role == 'principal_admin'
def get_included_form_templates(package):
    return [pf.html_template_name for pf in package.package_forms.all()]
def get_included_form_types(package):
    return list(package.package_forms.values_list('form_type', flat=True))
    
def is_admins(user):
    return user.role in ['admin', 'principal_admin', 'approval_member']
def admin_login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)

            # New: Redirect logic based on NIH roles
            if user.agency and user.position_type in ['agency_user', 'nih_sro', 'nih_chair', 'nih_board_member']:
                return redirect('agency_dashboard')

            # Original admin/org admin
            if user.role in ['admin', 'principal_admin']:
                return redirect('admin_dashboard', org_id=user.organization.id)

            # Fallback for regular org users
            return redirect('dashboard', org_id=user.organization.id)

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
    return render(request, 'principal_admin/admin_actions.html', context)


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

    return render(request, 'admin/admin_buildings.html', {'org_id': org_id, 'buildings': buildings})
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
def entry_detail(request, fund_id, entry_id):
    fund = get_object_or_404(Fund, fund_id=fund_id)
    entry = get_object_or_404(CostEntry, id=entry_id)

    context = {
        "fund": fund,
        "entry": entry,
    }

    return render(request, "admin/entry_detail.html", context)


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
def calendar_event_data(request, org_id):
    events = CalendarEvent.objects.filter(organization_id=org_id)
    data = [
        {
            "id": e.id,  # ✅ REQUIRED for deletion / interaction
            "title": e.title,
            "start": e.start_date.isoformat(),
            "end": e.end_date.isoformat(),
            "color": e.color,
            "allDay": e.all_day,
            "description": e.description,
            "project_task": {
                "project_id": e.project_task.project.id,
                "task_id": e.project_task.task_id,
            } if e.project_task else None
        }
        for e in events
    ]
    return JsonResponse(data, safe=False)

@login_required
@user_passes_test(is_admins)
def admin_dashboard(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    user = request.user

    total_users = User.objects.filter(organization=organization).count()
    upcoming_events = CalendarEvent.objects.filter(
        organization=organization, start_date__gte=timezone.now()
    ).count()
    pending_tasks = ProjectTask.objects.filter(
        project__org_id=org_id, status="Pending"
    ).count()

    VALID_STATUSES = [
        "Development", "Under Review", "Approved",
        "Submitted to Sponsor", "Funded", "Closed"
    ]
    status_filter = request.GET.get("status")

    # 👇 Base query to exclude incomplete/opportunity-based projects
    base_queryset = Project.objects.filter(org_id=org_id).filter(
        Q(admin_unit__isnull=False) | Q(users__isnull=False)
    ).exclude(name__icontains='Opportunity')

    # 🔐 Access filtering (non-superusers)
    if not user.is_superuser:
        if user.position_type in ['app_editor', 'app_viewer']:
            pass  # Can see all
        elif user.position_type in ['dept_app_editor', 'dept_app_viewer'] and user.department:
            base_queryset = base_queryset.filter(admin_unit=user.department.name)
        else:
            base_queryset = base_queryset.filter(
                Q(users=user) | Q(routing_users=user)
            )

    # ✅ Always call .distinct() to prevent duplication
    base_queryset = base_queryset.distinct()
    
    # 📌 Apply status filter if valid
    if status_filter in VALID_STATUSES:
        base_queryset = base_queryset.filter(status=status_filter)

    # 📦 Pagination
    paginator = Paginator(base_queryset.order_by("-created_at"), 15)
    page_number = request.GET.get("page")
    projects_page = paginator.get_page(page_number)

    # 📊 Status counts for buttons
    dev_count = base_queryset.filter(status="Development").count()
    review_count = base_queryset.filter(status="Under Review").count()
    approved_count = base_queryset.filter(status="Approved").count()
    submitted_count = base_queryset.filter(status="Submitted to Sponsor").count()
    funded_count = base_queryset.filter(status="Funded").count()
    closed_count = base_queryset.filter(status="Closed").count()

    context = {
        'org_id': org_id,
        'user': user,
        'total_users': total_users,
        'upcoming_events': upcoming_events,
        'pending_tasks': pending_tasks,
        'projects': projects_page,
        'status_filter': status_filter,
        'dev_count': dev_count,
        'review_count': review_count,
        'approved_count': approved_count,
        'submitted_count': submitted_count,
        'funded_count': funded_count,
        'closed_count': closed_count,
    }
    return render(request, 'admin/admin_dashboard.html', context)

def agency_or_nih_required(user):
    if user.is_authenticated and user.agency and user.position_type in ['agency_user', 'nih_sro', 'nih_chair', 'nih_board_member']:
        return True
    raise PermissionDenied  # Instead of redirecting to /accounts/login/
@login_required
@user_passes_test(agency_or_nih_required)
def agency_dashboard(request):
    user = request.user
    agency = user.agency

    related_submissions = SubmittedPackage.objects.filter(
        opportunity__agency_ref=agency,
        is_draft=False,
        approval_status__in=["approved", "routed"]
    ).select_related("project", "opportunity", "user")

    status_filter = request.GET.get("status")
    if status_filter:
        related_submissions = related_submissions.filter(project__status=status_filter)

    # Mapping latest submission to project
    project_map = {}
    for submission in related_submissions.order_by('-submission_date'):
        project = submission.project
        if project and project.id not in project_map:
            project.latest_submitter = submission.user
            project.submitting_org = submission.user.organization if submission.user else None
            project_map[project.id] = project
    unique_projects = list(project_map.values())

    # Paginate the unique projects
    paginator = Paginator(unique_projects, 15)
    page_number = request.GET.get("page")
    projects_page = paginator.get_page(page_number)

    context = {
        'user': user,
        'agency': agency,
        'org_id': None,
        'projects': projects_page,
        'status_filter': status_filter,
        'dev_count': related_submissions.filter(project__status="Development").count(),
        'review_count': related_submissions.filter(project__status="Under Review").count(),
        'approved_count': related_submissions.filter(project__status="Approved").count(),
    }

    return render(request, "admin/admin_dashboard.html", context)
from datetime import date

@login_required
@user_passes_test(lambda u: u.position_type in ['agency_user', 'nih_sro', 'nih_chair', 'nih_board_member'] and u.agency is not None)
def agency_opportunity_list(request):
    agency = request.user.agency
    query = request.GET.get("search", "")
    
    opportunities = Opportunity.objects.filter(agency_ref=agency)

    if query:
        opportunities = opportunities.filter(
            Q(title__icontains=query) |
            Q(number__icontains=query) |
            Q(comp_id__icontains=query)
        )

    opportunities = opportunities.order_by('-created_at')

    # 🔄 Pagination
    paginator = Paginator(opportunities, 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        'opportunities': page_obj,
        'page_obj': page_obj,
        'user': request.user,
        'agency': agency,
        'search_query': query,
    }
    return render(request, 'admin/agency_opportunity_list.html', context)

@login_required
@user_passes_test(lambda u: u.position_type in ['agency_user', 'nih_sro', 'nih_chair', 'nih_board_member'] and u.agency is not None)
def opportunity_submissions_view(request, opportunity_id):
    opportunity = get_object_or_404(Opportunity, id=opportunity_id, agency_ref=request.user.agency)

    query = request.GET.get("search", "")
    submissions = SubmittedPackage.objects.filter(
        opportunity=opportunity,
        is_draft=False,
        approval_status__in=["submitted", "approved", "routed"]
    ).select_related('project', 'user')

    projects = []
    for sub in submissions:
        proj = sub.project
        if proj:
            proj.submitting_org = sub.user.organization
            proj.latest_submitter = sub.user

            if query.lower() in proj.name.lower() or \
               query.lower() in proj.project_identifier.lower() or \
               query.lower() in (proj.principal_investigator or "").lower() or \
               query.lower() in sub.user.get_full_name().lower():
                projects.append(proj)
            elif not query:
                projects.append(proj)

    # ✅ Add financial sections to use in template
    financial_sections = [
        "Project Budget",
        "Expenses to Date",
        "Balance Remaining",
        "Encumbrance",
        "Projected",
        "Projected Balance (incl. Enc)"
    ]

    context = {
        'opportunity': opportunity,
        'projects': projects,
        'search_query': query,
        'user': request.user,
        'committees': request.user.agency.committees.all(),
        'financial_sections': financial_sections,  # 🆕 add this line
    }

    return render(request, 'admin/opportunity_submissions.html', context)
@login_required
@user_passes_test(lambda u: u.position_type in ['agency_user', 'nih_sro', 'nih_chair', 'nih_board_member'] and u.agency is not None)
def assign_committee_to_opportunity(request, opportunity_id):
    opportunity = get_object_or_404(Opportunity, id=opportunity_id, agency_ref=request.user.agency)

    if request.method == "POST":
        committee_id = request.POST.get("committee_id")
        committee = get_object_or_404(Committee, id=committee_id)
        opportunity.committee = committee
        opportunity.save()

        try:
            assign_sros_to_projects(opportunity)
            messages.success(request, "Committee and reviewers assigned successfully.")
        except Exception as e:
            messages.error(request, f"Error assigning reviewers: {str(e)}")

        return redirect('opportunity_submissions_view', opportunity_id=opportunity.id)


@user_passes_test(lambda u: u.role == 'admin' or u.role == 'principal_admin')
def create_user(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST or None, organization=organization)
        if form.is_valid():
            user = form.save(commit=False)
            user.organization = organization
            user.save()
            return redirect('admin_user_list', org_id=org_id)
    else:
        # ✅ Fix: pass organization here too
        form = CustomUserCreationForm(organization=organization)

    return render(request, 'admin/create_user.html', {'form': form, 'organization': organization})
@user_passes_test(lambda u: u.is_authenticated and u.role in ['admin', 'principal_admin'])
def department_list(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    departments = Department.objects.filter(organization=organization).prefetch_related('users')
    return render(request, 'admin/department_list.html', {
        'departments': departments,
        'organization': organization
    })

@user_passes_test(lambda u: u.is_authenticated and u.role in ['admin', 'principal_admin'])
def create_department(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)

    if request.method == 'POST':
        form = DepartmentForm(request.POST)
        if form.is_valid():
            department = form.save(commit=False)
            department.organization = organization
            department.save()
            return redirect('department_list', org_id=org_id)
    else:
        form = DepartmentForm()

    return render(request, 'admin/create_department.html', {
        'form': form,
        'organization': organization
    })

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
        users = User.objects.filter(
            organization=organization,
            username__icontains=query
        ).exclude(role="principal_admin") | User.objects.filter(id=request.user.id)
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


@login_required
@user_passes_test(lambda u: u.role == 'principal_admin')
def toggle_verification(request, org_id, user_id):
    if request.method == 'POST':
        user = get_object_or_404(User, id=user_id, organization_id=org_id)
        user.is_verified = not user.is_verified
        user.save()
        return JsonResponse({'status': 'success', 'verified': user.is_verified})
    return JsonResponse({'status': 'error'}, status=400)

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
    return render(request, "import_export/fill_form.html", {"pdf": pdf_template, "pdf_id": pdf_id})

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
    pdf_template_path = "/Users/ryancarmody/algoresearch/static/templates/performance_site_template.pdf"
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


# Path to the SF-424 PDF (adjust as needed)

@login_required
def project_performance_submit(request, org_id, form_id):
    if request.method == "POST":
        package_id = request.POST.get("package_id", "").strip()
        project_id = request.POST.get("project_id") or request.session.get("project_id")

        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return HttpResponse("Project not found", status=404)

        draft, created = SubmittedPackage.objects.get_or_create(
            org_id=org_id,
            package_id=package_id,
            project=project,
            is_draft=True,
            defaults={"submission_name": f"Draft - {project.name}", "submission_date": timezone.now()}
        )

        # Parse data from request.POST
        num_sites = len(request.POST.getlist("uei[]"))
        sites = []
        for i in range(num_sites):
            site = {
                "is_individual_applicant": "is_individual_applicant" in request.POST,  # Checkbox applies to whole form
                "uei": request.POST.getlist("uei[]")[i],
                "organization_name": request.POST.getlist("organization_name[]")[i],
                "street1": request.POST.getlist("street1[]")[i],
                "street2": request.POST.getlist("street2[]")[i],
                "city": request.POST.getlist("city[]")[i],
                "county": request.POST.getlist("county[]")[i],
                "province": request.POST.getlist("province[]")[i],
                "state": request.POST.getlist("state[]")[i],
                "zip": request.POST.getlist("zip[]")[i],
                "country": request.POST.getlist("country[]")[i],
                "congressional_district": request.POST.getlist("congressional_district[]")[i],
            }
            sites.append(site)

        # Save to draft
        draft.project_performance_data = json.dumps({"sites": sites})
        draft.last_edited_by = request.user
        draft.save()

        messages.success(request, "Project Performance Sites draft saved successfully.")
        return redirect("specific_project_home", org_id=org_id, project_id=project_id)

    return redirect("package_display", org_id=org_id, package_id=package_id, project_id=project_id)

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
    


def save_full_draft(project, org_id, package_id, user, sf424_data=None, rr_budget_data=None, budget_periods=None, cumulative_totals=None):
    draft, created = SubmittedPackage.objects.get_or_create(
        org_id=org_id,
        package_id=package_id,
        project=project,
        is_draft=True,
        defaults={
            "submission_name": f"Draft - {project.name}",
            "submission_date": timezone.now(),
            "last_edited_by": user
        }
    )

    if sf424_data is not None:
        draft.sf424_data = sf424_data
    if rr_budget_data is not None:
        draft.rr_budget_data = rr_budget_data
    if budget_periods is not None:
        draft.budget_periods = budget_periods
    if cumulative_totals is not None:
        draft.cumulative_totals = cumulative_totals

    draft.last_edited_by = user
    draft.save()
    return draft
@login_required
def download_project_performance_pdf(request, org_id, form_id):
    """Generate and serve the Project Performance Sites form as a downloadable PDF."""
    submission = get_object_or_404(SubmittedPackage, id=form_id, user=request.user)

    # Parse the stored JSON data
    try:
        project_performance_data = json.loads(submission.project_performance_data or "{}")
    except json.JSONDecodeError:
        project_performance_data = {}

    html_string = render_to_string(
        "admin/Project_Performance_Sites_Answers.html",  # ✅ Match your template file name
        {
            "project_performance_data": project_performance_data,
            "submission": submission,
            "org_id": org_id,
            "form_id": form_id,
        },
    )

    pdf_css = CSS(string="""
        @page { size: Letter; margin: 0.5in; }
        body { font-family: 'Times New Roman', serif; font-size: 10pt; margin: 0; }
        table { width: 100%; border-collapse: collapse; font-size: 9pt; }
        td, th { border: 1px solid black; padding: 4px; word-wrap: break-word; }
        input { border: none; background: transparent; width: 100%; font-size: 9pt; }
        .TableHeader { font-weight: bold; background-color: #f0f0f0; }
        .page-break { page-break-before: always; }
    """)

    with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as pdf_file:
        HTML(string=html_string).write_pdf(pdf_file.name, stylesheets=[pdf_css])
        with open(pdf_file.name, "rb") as pdf:
            response = HttpResponse(pdf.read(), content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="Project_Performance_Sites_{submission.submission_name}.pdf"'
            return response

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from weasyprint import HTML, CSS
import tempfile
import json
import logging

logger = logging.getLogger(__name__)

@login_required
def download_phs_human_subject_pdf(request, org_id, form_id):
    """Generate and serve the PHS Human Subjects form as a downloadable PDF."""
    submission = get_object_or_404(
        SubmittedPackage, id=form_id, org_id=org_id, is_draft=False
    )

    try:
        raw_data = submission.phs_human_subject_data
        if isinstance(raw_data, str):
            data = json.loads(raw_data)
        elif isinstance(raw_data, dict):
            data = raw_data
        else:
            data = {}
    except json.JSONDecodeError:
        logger.warning("❗ JSON decode failed for phs_human_subject_data.")
        data = {}

    logger.info(f"📦 PHS Human Subjects raw type: {type(submission.phs_human_subject_data)}")
    logger.info(f"📦 Loaded fields: {list(data.keys())}")

    context = {
        "submission": submission,
        "org_id": org_id,
        "form_id": form_id,
        "phs_data": data,
        "data": data,
        "user": request.user,
    }

    html_string = render_to_string("admin/phs_human_subject_answers.html", context)

    pdf_css = CSS(string="""
        @page { size: Letter; margin: 0.5in; }
        body { font-family: 'Times New Roman', serif; font-size: 10pt; margin: 0; }
        table { width: 100%; border-collapse: collapse; font-size: 9pt; }
        td, th { border: 1px solid black; padding: 4px; word-wrap: break-word; }
        .TableHeader { font-weight: bold; background-color: #f0f0f0; }
        .page-break { page-break-before: always; }
    """)

    try:
        with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as pdf_file:
            HTML(string=html_string).write_pdf(pdf_file.name, stylesheets=[pdf_css])
            with open(pdf_file.name, "rb") as pdf:
                response = HttpResponse(pdf.read(), content_type="application/pdf")
                response["Content-Disposition"] = (
                    f'attachment; filename="PHS_Human_Subjects_{submission.submission_name}.pdf"'
                )
                return response
    except Exception as e:
        logger.exception("❌ PDF generation failed for PHS Human Subjects")
        return HttpResponse(f"Error generating PDF: {e}", status=500)

@login_required
def create_project_task(request, project_id):
    if request.method == 'POST':
        data = json.loads(request.body)
        project = get_object_or_404(Project, id=project_id)

        task_type = data.get('task_type', 'other')
        task_category = data.get('task_category', 'other')

        # Create task
        task = ProjectTask(
            project=project,
            title=data.get('title'),
            task_type=task_type,
            task_category=task_category,
            description=data.get('description'),
            due_date=data.get('due_date'),
            assigned_by=request.user
        )
        task.save()

        # Add assignees
        assignees = data.get('assignees', [])
        assignee_users = User.objects.filter(username__in=assignees)
        task.assignees.add(*assignee_users)
        task.save()

        # Get organization using org_id
        try:
            organization = Organization.objects.get(id=project.org_id)
        except Organization.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Organization not found.'}, status=400)

        # Add CalendarEvent for each assignee
        due_str = data.get('due_date')
        try:
            due_date = datetime.strptime(due_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return JsonResponse({'status': 'error', 'message': 'Invalid due date format.'}, status=400)

        start_dt = make_aware(datetime.combine(due_date, time.min))
        end_dt = make_aware(datetime.combine(due_date, time.max))
        for user in assignee_users:
            CalendarEvent.objects.create(
                user=user,
                organization=organization,
                title=f"{task.title}",
                description=task.description,
                start_date=start_dt,
                end_date=end_dt,
                all_day=True,
                color="#FF6347",
                is_shared=True,
                project_task=task  # instead of task=task
            )
        
        return JsonResponse({'status': 'success', 'message': 'Task and calendar event created successfully.'})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})
# views.py
@login_required
@user_passes_test(is_admin_or_principal)
def admin_user_dictionary(request, org_id):
    org = get_object_or_404(Organization, id=org_id)

    categories = UserDictionaryEntry.CATEGORY_CHOICES

    return render(request, "admin/admin_user_dictionary.html", {
        "organization": org,
        "categories": categories,
    })

FundingGrantFormSet = inlineformset_factory(
        UserDictionaryEntry,
        FundingGrant,
        fields=['grant_number'],
        extra=1,
        can_delete=True
    )

@login_required
@user_passes_test(is_admin_or_principal)
def admin_dictionary_category(request, org_id, category):
    from ..forms import OrganizationDepartmentFormSet  # ✅ Import the formset

    org = get_object_or_404(Organization, id=org_id)
    if category not in dict(UserDictionaryEntry.CATEGORY_CHOICES):
        return HttpResponseBadRequest("Invalid category")

    entries = UserDictionaryEntry.objects.filter(organization=org, category=category)
    category_label = dict(UserDictionaryEntry.CATEGORY_CHOICES)[category]

    form = UserDictionaryForm()
    formset = None

    if category == "funding":
        formset = FundingGrantFormSet()

        if request.method == "POST":
            if "add_funding_source" in request.POST:
                form = UserDictionaryForm(request.POST)
                if form.is_valid():
                    entry = form.save(commit=False)
                    entry.organization = org
                    entry.category = "funding"
                    entry.created_by = request.user
                    entry.save()
                    return redirect("admin_dictionary_category", org_id=org.id, category="funding")

            elif "add_grant" in request.POST:
                entry_id = request.POST.get("entry_id")
                entry = get_object_or_404(UserDictionaryEntry, id=entry_id, organization=org)
                formset = FundingGrantFormSet(request.POST, instance=entry)
                if formset.is_valid():
                    formset.save()
                    return redirect("admin_dictionary_category", org_id=org.id, category="funding")

    elif category == "organization":
        formset = OrganizationDepartmentFormSet()

        if request.method == "POST":
            if "add_organization" in request.POST:
                form = UserDictionaryForm(request.POST)
                if form.is_valid():
                    entry = form.save(commit=False)
                    entry.organization = org
                    entry.category = "organization"
                    entry.created_by = request.user
                    entry.save()
                    return redirect("admin_dictionary_category", org_id=org.id, category="organization")

            elif "add_department" in request.POST:
                entry_id = request.POST.get("entry_id")
                entry = get_object_or_404(UserDictionaryEntry, id=entry_id, organization=org)
                formset = OrganizationDepartmentFormSet(request.POST, instance=entry)
                if formset.is_valid():
                    formset.save()
                    return redirect("admin_dictionary_category", org_id=org.id, category="organization")
    elif category == "procedure":
        if request.method == "POST":
            if "add_procedure" in request.POST:
                form = UserDictionaryForm(request.POST)
                if form.is_valid():
                    entry = form.save(commit=False)
                    entry.organization = org
                    entry.category = "procedure"
                    entry.created_by = request.user
                    entry.save()
                    return redirect("admin_dictionary_category", org_id=org.id, category="procedure")
    elif category == "drug":
        if request.method == "POST":
            if "add_drug" in request.POST:
                form = UserDictionaryForm(request.POST, initial={"category": "drug"})
                if form.is_valid():
                    entry = form.save(commit=False)
                    entry.organization = org
                    entry.category = "drug"
                    entry.created_by = request.user
                    entry.save()
                    return redirect("admin_dictionary_category", org_id=org.id, category="drug")
    elif category == "agent":
        if request.method == "POST":
            if "add_agent" in request.POST:
                form = UserDictionaryForm(request.POST, initial={"category": "agent"})
                if form.is_valid():
                    entry = form.save(commit=False)
                    entry.organization = org
                    entry.category = "agent"
                    entry.created_by = request.user
                    entry.save()
                    return redirect("admin_dictionary_category", org_id=org.id, category="agent")
        else:
            # 👇 You need this to trigger correct labels and fields in GET render too
            form = UserDictionaryForm(initial={"category": "agent"})
    context = {
        "organization": org,
        "category_key": category,
        "category_label": category_label,
        "entries": entries,
        "form": form,
        "formset": formset if category in ["funding", "organization"] else None,
    }

    return render(request, "admin/admin_dictionary_category.html", context)
@login_required
def get_departments_by_organization(request):
    dict_entry_id = request.GET.get('org_id')

    try:
        org_entry = UserDictionaryEntry.objects.get(id=dict_entry_id, category='organization')
    except UserDictionaryEntry.DoesNotExist:
        return JsonResponse({'departments': []})

    departments = OrganizationDepartment.objects.filter(dictionary_entry=org_entry)
    data = [{'id': dept.id, 'name': dept.department_name} for dept in departments]

    return JsonResponse({'departments': data})

def admin_create_dictionary_entry(request, org_id):
    org = get_object_or_404(Organization, id=org_id)
    initial = {'category': request.GET.get('category')} if 'category' in request.GET else {}

    if request.method == "POST":
        form = UserDictionaryForm(request.POST)
        formset = FundingGrantFormSet(request.POST)

        if form.is_valid():
            entry = form.save(commit=False)
            entry.organization = org
            entry.created_by = request.user
            entry.save()

            if entry.category == "funding":
                formset = FundingGrantFormSet(request.POST, instance=entry)
                if formset.is_valid():
                    formset.save()

            return redirect('admin_dictionary_category', org_id=org.id, category=entry.category)
    else:
        form = UserDictionaryForm(initial=initial)
        formset = FundingGrantFormSet()

    return render(request, 'admin/admin_create_dictionary_entry.html', {
        'form': form,
        'formset': formset if initial.get("category") == "funding" else None,
        'org_id': org.id
    })
@login_required
def get_drug_class(request):
    entry_id = request.GET.get('entry_id')
    try:
        entry = UserDictionaryEntry.objects.get(id=entry_id, category='drug')
        return JsonResponse({'drug_class': entry.definition})
    except UserDictionaryEntry.DoesNotExist:
        return JsonResponse({'drug_class': None})
    