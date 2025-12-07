from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test, login_required
from dashboard.forms import ProjectForm, PersonnelForm, PersonnelInfoForm, IRBMemberForm, FullPersonnelForm,SpeciesStrainForm,  SpeciesJustificationForm, SpeciesUseLocationForm, SpeciesInfoForm, PersonnelTrainingForm, PersonnelActivitiesForm, PersonnelTrainingForm, EuthanasiaForm, IACUCMemberForm, MeetingForm, MeetingItemForm, IRBStudyDrugForm,IRBStudyDeviceForm, IRBDocumentForm, IRBStudyScopeForm, IRBFundingInfoForm, IRBInitialForm, IRBSubmissionForm, ReplaceForm, RefineForm, ReduceForm, EuthanasiaMethodForm, EuthanasiaNumbersForm, EuthanasiaPainForm, EuthanasiaAdverseForm, EuthanasiaExemptionsForm, SurgeryInfoForm, SurgeryPreOpForm, SurgeryPostOpForm, SurgeryLocationForm, DatabaseSearchForm, OffCampusWorkForm, HazardousAgentForm, MSSForm, VetDrugForm, RestraintForm, ProcedureForm, BreedingForm, WildlifeCaptureForm, FieldSafetyPrecautionsForm, FieldStudyPermitForm, FieldStudyDetailsForm, PublicTransportForm, IACUCFundingSourceForm, OutsideHousingForm, ExternalCollaborationForm, TissueSourceForm, IACUCPrivateFundingSourceForm, IACUCInternalFundingSourceForm, IACUCProtocolSpeciesForm, IACUCSubmissionDetailsForm, DepartmentForm, IACUCProtocolForm, ProjectTaskForm, FormPackageForm,  TaskAttachmentForm, TaskCommentForm, OpportunityForm, TrainingFolderForm, SF424FormForm, OtherPersonnelForm, BudgetPeriodForm, PerformanceSiteLocationForm, SubMiniStepForm, MiniStepForm, MiniStepFieldForm, CertificationForm, CustomUserCreationForm, AdminCreatedFormForm, FormField, FormFieldForm, UploadPDFTemplateForm, ProtocolCreationForm, ProtocolApprovalForm
from django.db.models import Q, F, Avg, Max, Min, Count, Prefetch, Sum
from dashboard.models import ProtocolDesign, IACUCPersonnel, IRBMember, IRBNote, IRBCommittee, IRBCertification, MeetingVote,SpeciesStrain, SpeciesUseLocation, SpeciesVetDrug, IACUCSectionNote, Meeting, MeetingItem, IRBStudyDrug, IACUCNote, IACUCCommittee, IACUCSubmissionAttachment, IACUCMember, IRBStudyDevice, IRBDocument, IRBSubmission, IRBStudyMember, IRBStudyLocation, IRBFundingSource, DatabaseSearch, IRBSubmission, SpeciesEuthanasia,HazardousAgent, SpeciesSurgery, SpeciesMSS,  Fund, WildlifeCapture, SpeciesRestraint, SpeciesProcedure,  SpeciesBreeding, FieldStudyPermit, FieldSafetyPrecautions,  FieldStudyDetails, IACUCFundingSource, PublicTransportUse, OutsideHousing, OffCampusWork, ExternalCollaboration, IACUCPrivateFundingSource, IACUCInternalFundingSource, ProjectAccess, IACUCProtocolSpecies, IACUCSubmission,  UserFundAssignment, GlossaryItem, BudgetAllocation, EmployeeEntry,ProjectBudgetPeriod, ProjectFinancials, CostEntry, CostType,  Agency, ReviewScore, Committee, CommitteeMember,  CalendarEvent, Department, RROtherInformation, ProjectOpportunity, PHSResearchPlan, ProjectAttachment, ProjectHistory, Note, RoutingDecision, ProjectTask, TaskAttachment, TaskComment, Opportunity, Project, SubmittedPackage, SF424Form, SF424Submission, OtherPersonnel, BudgetPeriod, PerformanceSiteLocation, FormPackage, PackageForm, SF424Field, Organization, PDFField, SubMiniStepField, MiniStep, SubMiniStep, MiniStepField, User, UserCertification, RFIDAssignment, Building, Room, TrainingFolder, Certification, Rack, ProtocolTemplate, ApprovalComment, SpeciesEntry, Attachment, Notification, Protocol, UserFilledForm, Animal, Cage, Experiment, UserAction, UserSignature, InboxNotification, SignedForm, AdminCreatedForm, Organization, PDFFieldMapping, Conversation, Message
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
try:
    import pdfkit
except ImportError:
    pdfkit = None

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
from django.http import JsonResponse, FileResponse, Http404, HttpResponseNotFound, HttpRequest, HttpResponseRedirect, HttpResponseNotAllowed
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

def is_admin_or_principal(user):
    return user.role in ['admin', 'principal_admin']

def is_principal_admin(user):
    return user.role == 'principal_admin'

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
def can_create_protocol(user):
    return user.role in ['admin', 'principal_admin']

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
def can_approve_protocol(user):
    return user.role in ['approval_member', 'principal_admin']
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


# Check if user is Admin, Researcher, or Officer (for protocol creation)

# Check if user is Approval Member or Principal Admin (for approval)

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
def is_committee_member(user):
    return user.is_authenticated and user.agency is not None and CommitteeMember.objects.filter(user=user).exists()


@login_required
@user_passes_test(is_committee_member)
def committee_dashboard(request):
    user = request.user
    committees = Committee.objects.filter(members__user=user).select_related('agency').prefetch_related('members')
    
    opportunities = Opportunity.objects.filter(committee__in=committees).order_by('-created_at')

    context = {
        'user': user,
        'committees': committees,
        'opportunities': opportunities,
    }
    return render(request, 'admin/committee_dashboard.html', context)
@login_required
@user_passes_test(is_committee_member)
def committee_opportunity_projects(request, opportunity_id):
    opportunity = get_object_or_404(Opportunity, id=opportunity_id, committee__members__user=request.user)

    submissions = SubmittedPackage.objects.filter(
        opportunity=opportunity,
        is_draft=False,
        approval_status__in=['submitted', 'approved', 'routed']
    ).select_related('project', 'user')

    projects = []
    for sub in submissions:
        proj = sub.project
        if proj:
            proj.latest_submitter = sub.user
            proj.submitting_org = sub.user.organization
            projects.append(proj)

    context = {
        'opportunity': opportunity,
        'projects': projects,
        'user': request.user,
    }

    return render(request, 'admin/committee_opportunity_projects.html', context)

def fill_out_form(request):
    return render(request, "admin/fill_out_forms.html")

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

def get_form_fields(request, form_id):
    """Retrieve extracted fields for a given form"""
    pdf_template = get_object_or_404(PDFTemplate, id=form_id)

    try:
        fields = json.loads(pdf_template.fields)  # Ensure fields are stored as JSON
    except json.JSONDecodeError:
        fields = []

    return JsonResponse({"fields": fields})

