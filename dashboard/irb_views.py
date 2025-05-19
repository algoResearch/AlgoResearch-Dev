from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test, login_required
from .forms import ProjectForm, PersonnelForm, PersonnelInfoForm, IRBMemberForm, FullPersonnelForm,SpeciesStrainForm,  SpeciesJustificationForm, SpeciesUseLocationForm, SpeciesInfoForm, PersonnelTrainingForm, PersonnelActivitiesForm, PersonnelTrainingForm, EuthanasiaForm, IACUCMemberForm, MeetingForm, MeetingItemForm, IRBStudyDrugForm,IRBStudyDeviceForm, IRBDocumentForm, IRBStudyScopeForm, IRBFundingInfoForm, IRBInitialForm, IRBSubmissionForm, ReplaceForm, RefineForm, ReduceForm, EuthanasiaMethodForm, EuthanasiaNumbersForm, EuthanasiaPainForm, EuthanasiaAdverseForm, EuthanasiaExemptionsForm, SurgeryInfoForm, SurgeryPreOpForm, SurgeryPostOpForm, SurgeryLocationForm, DatabaseSearchForm, OffCampusWorkForm, HazardousAgentForm, MSSForm, VetDrugForm, RestraintForm, ProcedureForm, BreedingForm, WildlifeCaptureForm, FieldSafetyPrecautionsForm, FieldStudyPermitForm, FieldStudyDetailsForm, PublicTransportForm, IACUCFundingSourceForm, OutsideHousingForm, ExternalCollaborationForm, TissueSourceForm, IACUCPrivateFundingSourceForm, IACUCInternalFundingSourceForm, IACUCProtocolSpeciesForm, IACUCSubmissionDetailsForm, DepartmentForm, IACUCProtocolForm, ProjectTaskForm, FormPackageForm,  TaskAttachmentForm, TaskCommentForm, OpportunityForm, TrainingFolderForm, SF424FormForm, OtherPersonnelForm, BudgetPeriodForm, PerformanceSiteLocationForm, SubMiniStepForm, MiniStepForm, MiniStepFieldForm, CertificationForm, CustomUserCreationForm, AdminCreatedFormForm, FormField, FormFieldForm, UploadPDFTemplateForm, ProtocolCreationForm, ProtocolApprovalForm
from django.db.models import Q, F, Avg, Max, Min, Count, Prefetch, Sum
from .models import ProtocolDesign, IACUCPersonnel, IRBMember, IRBNote, IRBCommittee, IRBCertification, MeetingVote,SpeciesStrain, SpeciesUseLocation, SpeciesVetDrug, IACUCSectionNote, Meeting, MeetingItem, IRBStudyDrug, IACUCNote, IACUCCommittee, IACUCSubmissionAttachment, IACUCMember, IRBStudyDevice, IRBDocument, IRBSubmission, IRBStudyMember, IRBStudyLocation, IRBFundingSource, DatabaseSearch, IRBSubmission, SpeciesEuthanasia,HazardousAgent, SpeciesSurgery, SpeciesMSS,  Fund, WildlifeCapture, SpeciesRestraint, SpeciesProcedure,  SpeciesBreeding, FieldStudyPermit, FieldSafetyPrecautions,  FieldStudyDetails, IACUCFundingSource, PublicTransportUse, OutsideHousing, OffCampusWork, ExternalCollaboration, IACUCPrivateFundingSource, IACUCInternalFundingSource, ProjectAccess, IACUCProtocolSpecies, IACUCSubmission,  UserFundAssignment, GlossaryItem, BudgetAllocation, EmployeeEntry,ProjectBudgetPeriod, ProjectFinancials, CostEntry, CostType,  Agency, ReviewScore, Committee, CommitteeMember,  CalendarEvent, Department, RROtherInformation, ProjectOpportunity, PHSResearchPlan, ProjectAttachment, ProjectHistory, Note, RoutingDecision, ProjectTask, TaskAttachment, TaskComment, Opportunity, Project, SubmittedPackage, SF424Form, SF424Submission, OtherPersonnel, BudgetPeriod, PerformanceSiteLocation, FormPackage, PackageForm, SF424Field, Organization, PDFField, SubMiniStepField, MiniStep, SubMiniStep, MiniStepField, User, UserCertification, RFIDAssignment, Building, Room, TrainingFolder, Certification, Rack, ProtocolTemplate, ApprovalComment, SpeciesEntry, Attachment, Notification, Protocol, UserFilledForm, Animal, Cage, Experiment, UserAction, UserSignature, InboxNotification, SignedForm, AdminCreatedForm, Organization, PDFFieldMapping, Conversation, Message
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
from .pdf_utils import extract_pdf_fields, convert_pdf_to_images
import logging

from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login
from django.http import FileResponse
import os  # To handle file operations (e.g., saving and deleting temporary logo files)
from io import BytesIO  # For in-memory file handling (PDF generation)
from .models import PDFTemplate, CalendarEvent
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

@login_required
def irb_dashboard(request, org_id):
    user = request.user

    base_q = Q(user=user) | Q(shared_with=user)
    stage_q = Q()

    # Office Member access
    is_office_member = IRBMember.objects.filter(
        user=user,
        role='office_member',
        is_active=True,
        committee__organization_id=org_id
    ).exists()
    if is_office_member:
        stage_q |= Q(status__in=["Pre Review", "Post IRB Review"], organization_id=org_id)

    # Analyst access (add "Pre Review" here)
    is_analyst = IRBMember.objects.filter(
        user=user,
        role='analyst',
        is_active=True,
        committee__organization_id=org_id
    ).exists()
    if is_analyst:
        stage_q |= Q(status__in=["Expedited and Exempt", "IRB Pre Review"], organization_id=org_id)

    irb_submissions = IRBSubmission.objects.filter(
        (base_q | stage_q) & Q(organization_id=org_id)
    ).distinct()

    return render(request, 'admin/irb_dashboard.html', {
        'irb_submissions': irb_submissions,
        'org_id': org_id,
    })


@login_required
def irb_create(request, org_id):
    if request.method == 'POST':
        form = IRBSubmissionForm(request.POST)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.user = request.user
            submission.organization_id = org_id
            submission.save()
            return redirect('irb_dashboard', org_id=org_id)
    else:
        form = IRBSubmissionForm()
    return render(request, 'admin/irb_create.html', {'form': form, 'org_id': org_id})

def load_json(filename):
    try:
        path = os.path.join(settings.BASE_DIR, "static", filename)
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error loading {filename}: {str(e)}")
        return {}

@login_required
def irb_basic_info(request, org_id):
    user = request.user

    if request.method == "POST":
        form = IRBInitialForm(request.POST)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.user = user
            submission.organization_id = org_id
            submission.status = "Draft"
            submission.save()
            return redirect('irb_fill_out', submission_id=submission.id)
    else:
        form = IRBInitialForm()

    return render(request, 'admin/irb_basic_info.html', {
        'form': form,
        'org_id': org_id,
    })

@login_required
def irb_fill_out(request, submission_id):
    submission = get_object_or_404(IRBSubmission, id=submission_id)

    if request.user != submission.user and not request.user.is_superuser:
        raise PermissionDenied()
    section = request.GET.get("section", "study_funding")

    # ---- FUNDING ----
    funding_form = IRBFundingInfoForm(request.POST or None, instance=submission)
    funding_entries = IRBFundingSource.objects.filter(submission=submission)

    if request.method == "POST" and "save_funding_info" in request.POST:
        try:
            funding_data = json.loads(request.POST.get("funding_json", "[]"))
        except json.JSONDecodeError:
            funding_data = []

        IRBFundingSource.objects.filter(submission=submission).delete()
        for entry in funding_data:
            IRBFundingSource.objects.create(
                submission=submission,
                project_name=entry.get("project_name"),
                sponsor=entry.get("sponsor"),
                sponsor_number=entry.get("sponsor_number"),
                pi_id=entry.get("pi_id") or None,
            )

        if funding_form.is_valid():
            funding_form.save()

        return redirect(f"{request.path}?section=study_funding")

    # ---- MEMBERS ----
    if request.method == "POST" and "save_members_info" in request.POST:
        try:
            members_data = json.loads(request.POST.get("members_json", "[]"))
        except json.JSONDecodeError:
            members_data = []

        IRBStudyMember.objects.filter(submission=submission).delete()

        # Reset coordinator
        submission.coordinator = None

        for m in members_data:
            new_member = IRBStudyMember.objects.create(
                submission=submission,
                user_id=m.get("user_id"),
                role=m.get("role"),
                involved_in_consent=m.get("consent") == True,
                financial_interest=m.get("interest") == True,
            )

            # Set coordinator if applicable
            if m.get("role") == "Research Coordinator" and m.get("user_id"):
                try:
                    coordinator_user = User.objects.get(id=m["user_id"])
                    submission.coordinator = coordinator_user
                except User.DoesNotExist:
                    pass  # fail silently

        submission.save()
        return redirect(f"{request.path}?section=study_members")

    # ---- LOCATIONS ----
    if request.method == "POST" and "save_locations_info" in request.POST:
        try:
            location_data = json.loads(request.POST.get("locations_json", "[]"))
        except json.JSONDecodeError:
            location_data = []

        IRBStudyLocation.objects.filter(submission=submission).delete()
        for loc in location_data:
            IRBStudyLocation.objects.create(
                submission=submission,
                location_name=loc.get("location_name", ""),
                address_line1=loc.get("address_line1", ""),
                address_line2=loc.get("address_line2", ""),
                address_line3=loc.get("address_line3", ""),
                city=loc.get("city", ""),
                state=loc.get("state", ""),
                postal_code=loc.get("postal_code", ""),
                country=loc.get("country", ""),
            )

        return redirect(f"{request.path}?section=study_locations")

    # ---- DOCUMENTS ----
    if request.method == "POST" and "save_documents_info" in request.POST:
        IRBDocument.objects.filter(submission=submission).delete()

        doc_types = request.POST.getlist('document_type[]')
        names = request.POST.getlist('name[]')
        versions = request.POST.getlist('version[]')
        categories = request.POST.getlist('category[]')
        descriptions = request.POST.getlist('category_description[]')
        files = request.FILES.getlist('file[]')

        for i in range(len(names)):
            IRBDocument.objects.create(
                submission=submission,
                document_type=doc_types[i],
                name=names[i],
                version=versions[i],
                file=files[i],
                category=categories[i] if doc_types[i] == "Other" else "",
                category_description=descriptions[i] if doc_types[i] == "Other" else "",
            )

        return redirect(f"{request.path}?section=study_documents")

    # ---- PRELOAD DATA FOR JS ----
    funding_entries_json = json.dumps([
        {
            "project_name": f.project_name,
            "sponsor": f.sponsor,
            "sponsor_number": f.sponsor_number,
            "pi_id": f.pi.id if f.pi else None,
            "pi_name": f"{f.pi.first_name} {f.pi.last_name}" if f.pi else "",
        }
        for f in funding_entries
    ])

    member_entries = IRBStudyMember.objects.filter(submission=submission)
    member_entries_json = json.dumps([
        {
            "user_id": m.user.id if m.user else None,
            "name": m.user.get_full_name() if m.user else "Unknown",
            "role": m.role,
            "consent": m.involved_in_consent,
            "interest": m.financial_interest,
            "email": m.user.email if m.user else "",
            "phone": m.user.phone_number if m.user and m.user.phone_number else "",
        }
        for m in member_entries
    ])

    location_entries = IRBStudyLocation.objects.filter(submission=submission)
    location_entries_json = json.dumps([
        {
            "location_name": l.location_name,
            "address_line1": l.address_line1,
            "address_line2": l.address_line2,
            "address_line3": l.address_line3,
            "city": l.city,
            "state": l.state,
            "postal_code": l.postal_code,
            "country": l.country,
        } for l in location_entries
    ])

    document_entries = IRBDocument.objects.filter(submission=submission)
    consent_docs = [
        {"name": d.name, "version": d.version, "file_url": d.file.url}
        for d in document_entries.filter(document_type="Consent")
    ]
    recruit_docs = [
        {"name": d.name, "version": d.version, "file_url": d.file.url}
        for d in document_entries.filter(document_type="Recruitment")
    ]
    other_docs = [
        {
            "name": d.name,
            "version": d.version,
            "category": d.category if d.category != "Other" else f"Other: {d.category_description}",
            "file_url": d.file.url
        }
        for d in document_entries.filter(document_type="Other")
    ]
    
    scope_form = IRBStudyScopeForm(request.POST or None, instance=submission)


    if request.method == "POST" and "save_study_scope_info" in request.POST:
        if scope_form.is_valid():
            scope_form.save()
        return redirect(f"{request.path}?section=study_scope")
    # Dynamic sidebar sections
    sections = ['study_funding', 'study_members', 'study_scope']

    if submission.uses_drug_or_biologic:
        sections.append('study_drug')

    if submission.uses_device:
        sections.append('study_device')
    drug_form = IRBStudyDrugForm(request.POST or None, instance=submission)
    if request.method == "POST" and "save_study_drug_info" in request.POST:
        try:
            drugs_data = json.loads(request.POST.get("drugs_json", "[]"))
        except json.JSONDecodeError:
            drugs_data = []

        IRBStudyDrug.objects.filter(submission=submission).delete()
        for drug in drugs_data:
            IRBStudyDrug.objects.create(
                submission=submission,
                generic_name=drug.get("generic"),
                brand_name=drug.get("brand"),
                drug_type=drug.get("type") if not drug.get("type", "").startswith("Other:") else "Other",
                other_type_description=drug.get("type").replace("Other: ", "") if "Other:" in drug.get("type", "") else "",
            )

        if drug_form.is_valid():
            drug_form.save()

        return redirect(f"{request.path}?section=study_drug")

    study_drug_entries = IRBStudyDrug.objects.filter(submission=submission)
    study_drugs_json = json.dumps([
        {
            "generic": d.generic_name,
            "brand": d.brand_name,
            "type": d.drug_type if d.drug_type != "Other" else f"Other: {d.other_type_description}"
        }
        for d in study_drug_entries
    ])
    device_form = IRBStudyDeviceForm(request.POST or None, instance=submission)
    if request.method == "POST" and "save_study_device_info" in request.POST:
        try:
            devices_data = json.loads(request.POST.get("devices_json", "[]"))
        except json.JSONDecodeError:
            devices_data = []

        IRBStudyDevice.objects.filter(submission=submission).delete()
        for device in devices_data:
            IRBStudyDevice.objects.create(
                submission=submission,
                device_name=device.get("device_name"),
                is_humanitarian_use=device.get("is_humanitarian_use") == True,
                exemption_status=device.get("exemption_status"),
                evaluates_safety_effectiveness=device.get("evaluates_safety_effectiveness") == True,
            )

        # ✅ Save fields on the IRBSubmission itself
        if device_form.is_valid():
            device_form.save()

        return redirect(f"{request.path}?section=study_device")

    # preload device JSON for JS table
    study_device_entries = IRBStudyDevice.objects.filter(submission=submission)
    study_devices_json = json.dumps([
        {
            "device_name": d.device_name,
            "is_humanitarian_use": d.is_humanitarian_use,
            "exemption_status": d.exemption_status,
            "evaluates_safety_effectiveness": d.evaluates_safety_effectiveness,
        }
        for d in study_device_entries
    ])
    if request.method == "POST" and "submit_irb" in request.POST:
        submission.status = "Pre Submission"
        submission.save()
        messages.success(request, "IRB submission saved as 'Pre Submission'. You must formally submit for review from the dashboard.")
        return redirect('irb_dashboard', org_id=submission.organization_id)
    section_templates = {
        'study_funding': 'irb_funding.html',
        'study_members': 'irb_members.html',
        'study_scope': 'irb_study_scope.html',
        'study_locations': 'irb_study_locations.html',
        'study_documents': 'irb_study_documents.html',
        'study_drug': 'irb_study_drug.html',
        'study_device': 'irb_study_device.html',
        'submit': 'irb_submit.html',  # 👈 Add this line
    }
    sections += ['study_locations', 'study_documents', 'submit']

    return render(request, "admin/irb_fill_out.html", {
        "submission": submission,
        "funding_form": funding_form,
        "funding_entries_json": funding_entries_json,
        "member_entries_json": member_entries_json,
        "location_entries_json": location_entries_json,
        "consent_docs_json": json.dumps(consent_docs),
        "recruit_docs_json": json.dumps(recruit_docs),
        "other_docs_json": json.dumps(other_docs),
        "section": section,
        "countries": load_json("countries.json"),
        "states": load_json("states.json"),
        "scope_form": scope_form,
        "sections": sections,
        "drug_form": drug_form,
        "section_templates": section_templates,  # 👈 Add this line
        "study_drugs_json": study_drugs_json,
        "device_form": device_form,
        "study_devices_json": study_devices_json,

    })
@csrf_exempt
@login_required
def save_irb_funding_entries(request, submission_id):
    if request.method == 'POST':
        submission = get_object_or_404(IRBSubmission, id=submission_id)

        data = json.loads(request.body)
        entries = data.get('entries', [])
        additional_info = data.get('funding_additional_info', '')

        # Save funding entries
        IRBFundingSource.objects.filter(submission=submission).delete()
        for e in entries:
            IRBFundingSource.objects.create(
                submission=submission,
                project_name=e['project_name'],
                sponsor=e.get('sponsor', ''),
                sponsor_number=e.get('sponsor_number', ''),
                pi_id=e.get('pi_id') or None,
            )

        # Save additional info on the submission object
        submission.funding_additional_info = additional_info
        submission.save()

        return JsonResponse({'status': 'success'})
    return JsonResponse({'error': 'Invalid request'}, status=400)

def irb_fill_out_next_section(request, submission_id, current_section):
    sections = ['study_funding', 'study_members', 'study_locations', 'study_documents']
    try:
        current_index = sections.index(current_section)
        next_section = sections[current_index + 1]
    except (ValueError, IndexError):
        # If current_section is not in the list or it's the last section
        return redirect('irb_dashboard', org_id=request.user.organization.id)

    return redirect(reverse('irb_fill_out_section', kwargs={
        'submission_id': submission_id,
        'section': next_section
    }))

@login_required
def irb_fill_out_section(request, submission_id, section):
    submission = get_object_or_404(IRBSubmission, id=submission_id)
    countries = load_json('countries.json')
    states = load_json('states.json')

    if request.user != submission.user and not request.user.is_superuser:
        return render(request, '403.html', status=403)

    funding_entries = IRBFundingSource.objects.filter(submission=submission)
    funding_data = [
        {
            'project_name': f.project_name,
            'sponsor': f.sponsor,
            'sponsor_number': f.sponsor_number,
            'pi_id': f.pi.id if f.pi else None,
            'pi_name': f"{f.pi.first_name} {f.pi.last_name}" if f.pi else '',
            'additional_info': '',  # Handle separately if needed
            
        } for f in funding_entries
    ]

    funding_form = IRBFundingInfoForm(instance=submission)

    return render(request, 'admin/irb_fill_out.html', {
        'submission': submission,
        'form': funding_form,
        'active_section': section,
        'sections': ['study_funding', 'study_members', 'study_locations', 'study_documents'],
        'funding_entries_json': json.dumps(funding_data),
        'countries': countries,
        'states': states,
    })

@csrf_exempt
@login_required
def save_irb_document(request, submission_id):
    submission = get_object_or_404(IRBSubmission, id=submission_id)

    if request.method == 'POST':
        form = IRBDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.submission = submission
            document.save()
            return JsonResponse({'status': 'success', 'message': 'Document uploaded successfully'})
        else:
            return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)

    return JsonResponse({'error': 'Invalid request method'}, status=405)


@login_required
def irb_home(request, submission_id):
    submission = get_object_or_404(IRBSubmission, id=submission_id)
    user = request.user

    # Base permission: Owner, superuser, or shared
    has_access = user == submission.user or user.is_superuser or user in submission.shared_with.all()

    # Add conditional access based on stage + IRB role
    if not has_access:
        if submission.status == "Pre Review":
            has_access = IRBMember.objects.filter(
                user=user,
                role='office_member',
                is_active=True,
                committee__organization=submission.organization
            ).exists()
        elif submission.status in ["IRB Pre Review", "Expedited and Exempt"]:
            has_access = IRBMember.objects.filter(
                user=user,
                role='analyst',
                is_active=True,
                committee__organization=submission.organization
            ).exists()
        elif submission.status == "Post IRB Review":
            has_access = IRBMember.objects.filter(
                user=user,
                role='office_member',
                is_active=True,
                committee__organization=submission.organization
            ).exists()
    if not has_access:
        return render(request, '403.html', status=403)
    # Handle formal submission action
    if request.method == "POST" and "submit_irb" in request.POST:
        if submission.status == "Pre Submission":
            submission.status = "Pre Review"
            submission.save()
            messages.success(request, "IRB submission successfully submitted for Pre Review.")
        else:
            messages.warning(request, "Submission must be in 'Pre Submission' state to submit.")
        return redirect("irb_home", submission_id=submission.id)

    certified_users = IRBCertification.objects.filter(submission=submission).values_list('user_id', flat=True)
    shared_users = submission.shared_with.all()

    context = {
        "submission": submission,
        "members": submission.members.all(),
        "locations": submission.locations.all(),
        "documents": submission.documents.all(),
        "modals": ["funding", "contacts", "documents", "reviews", "history"],
        "shared_users": shared_users,
        "certified_users": certified_users,
        "all_certified": all(u.id in certified_users for u in shared_users),
    }
    return render(request, "admin/irb_home.html", context)

@login_required
def get_irb_shared_users(request, submission_id):
    submission = get_object_or_404(IRBSubmission, id=submission_id)

    if request.user != submission.user and not request.user.is_superuser:
        return JsonResponse({'status': 'unauthorized'}, status=403)

    users = submission.shared_with.all()
    users_data = [{
        'id': u.id,
        'username': u.username,
        'first_name': u.first_name,
        'last_name': u.last_name
    } for u in users]

    return JsonResponse({'users': users_data})


@login_required
def add_irb_shared_users(request, submission_id):
    if request.method != "POST":
        return JsonResponse({'status': 'invalid_method'}, status=405)

    submission = get_object_or_404(IRBSubmission, id=submission_id)

    if request.user != submission.user and not request.user.is_superuser:
        return JsonResponse({'status': 'unauthorized'}, status=403)

    try:
        data = json.loads(request.body)
        user_ids = [u["id"] for u in data.get("selected_users", [])]
        users = User.objects.filter(id__in=user_ids)

        submission.shared_with.add(*users)
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
@login_required
def certify_irb_submission(request, submission_id):
    submission = get_object_or_404(IRBSubmission, id=submission_id)

    if request.user != submission.user and not submission.shared_with.filter(id=request.user.id).exists():
        return JsonResponse({'status': 'unauthorized'}, status=403)

    IRBCertification.objects.get_or_create(submission=submission, user=request.user)
    return JsonResponse({'status': 'success'})

# views.py

@login_required
def manage_irb_committee(request, org_id):
    org = get_object_or_404(Organization, id=org_id)
    committee, _ = IRBCommittee.objects.get_or_create(organization=org)
    members = IRBMember.objects.filter(committee=committee).select_related('user')

    if request.method == 'POST':
        form = IRBMemberForm(request.POST)
        if form.is_valid():
            member = form.save(commit=False)
            member.committee = committee
            member.save()
            messages.success(request, f"{member.user.get_full_name()} added as {member.get_role_display()}")
            return redirect('manage_irb_committee', org_id=org.id)
    else:
        form = IRBMemberForm()

    return render(request, 'admin/manage_irb_committee.html', {
        'organization': org,
        'committee': committee,
        'members': members,
        'form': form,
    })
@login_required
@require_POST
def remove_irb_member(request, member_id):
    member = get_object_or_404(IRBMember, id=member_id)
    org_id = member.committee.organization.id
    member.delete()
    messages.success(request, "Member removed.")
    return redirect('manage_irb_committee', org_id=org_id)
@login_required
@require_POST
def irb_status_transition(request, submission_id):
    submission = get_object_or_404(IRBSubmission, id=submission_id)
    user = request.user
    action = request.POST.get("action")
    note = request.POST.get("note", "").strip()
    review_type = request.POST.get("review_type")

    committee = getattr(submission.user.organization, "irb_committee", None)

    # ✅ Move checks into action blocks instead of blocking early
    if action == "send_back":
        is_office_member = IRBMember.objects.filter(
            user=user,
            role='office_member',
            is_active=True,
            committee=committee
        ).exists()
        if not is_office_member:
            return HttpResponseForbidden("Only IRB Office Members can send back.")

        if not note:
            return JsonResponse({"status": "error", "message": "A note is required to send back."}, status=400)

        submission.revision_stages = submission.revision_stages or {}
        submission.revision_stages[submission.status] = "revisions_requested"
        submission.status = "Pre Submission"
        submission.save()

        IRBNote.objects.create(submission=submission, author=user, content=note)
        messages.success(request, "Protocol sent back to PI for revisions.")

    elif action == "approve_and_forward":
        is_office_member = IRBMember.objects.filter(
            user=user,
            role='office_member',
            is_active=True,
            committee=committee
        ).exists()
        if not is_office_member:
            return HttpResponseForbidden("Only IRB Office Members can approve and forward.")

        if review_type not in ["exempt", "expedited", "full"]:
            return JsonResponse({"status": "error", "message": "Invalid review type."}, status=400)

        submission.review_type = review_type

        if review_type in ["exempt", "expedited"]:
            submission.status = "Expedited and Exempt"
        elif review_type == "full":
            submission.status = "IRB Pre Review"  # ✅ NEW intermediate step
        submission.save()
        IRBNote.objects.create(
            submission=submission,
            author=user,
            content=f"Office approved and forwarded as {review_type}."
        )
        messages.success(request, f"Submission forwarded as {review_type.title()} review.")
    elif action == "analyst_forward_to_board":
        if submission.status != "IRB Pre Review":
            return JsonResponse({"status": "error", "message": "Submission is not in IRB Pre Review."}, status=400)

        is_analyst = IRBMember.objects.filter(
            user=user,
            role='analyst',
            is_active=True,
            committee=committee
        ).exists()

        if not is_analyst:
            return HttpResponseForbidden("Only IRB Analysts can forward to full board review.")

        submission.status = "IRB Review"
        submission.save()

        IRBNote.objects.create(
            submission=submission,
            author=user,
            content="Analyst determined protocol is ready for IRB Full Review."
        )
        messages.success(request, "Submission forwarded to IRB Review.")
    elif action == "analyst_approve":
        if submission.status != "Expedited and Exempt":
            return JsonResponse({"status": "error", "message": "Invalid stage for analyst approval."}, status=400)

        is_analyst = IRBMember.objects.filter(
            user=user,
            role='analyst',
            is_active=True,
            committee__organization=submission.organization
        ).exists()

        if not is_analyst:
            return HttpResponseForbidden("Only IRB Analysts can perform this action.")

        submission.status = "Post IRB Review"
        submission.save()

        IRBNote.objects.create(
            submission=submission,
            author=user,
            content="IRB Analyst approved expedited/exempt review. Sent to Post IRB Review."
        )
        messages.success(request, "Submission moved to Post IRB Review.")

    elif action == "final_office_approval":
        if submission.status != "Post IRB Review":
            return JsonResponse({"status": "error", "message": "Submission is not ready for final approval."}, status=400)

        is_office_member = IRBMember.objects.filter(
            user=user,
            role='office_member',
            is_active=True,
            committee=committee
        ).exists()
        if not is_office_member:
            return HttpResponseForbidden("Only IRB Office Members can finalize.")

        submission.status = "Approved"
        submission.save()

        IRBNote.objects.create(
            submission=submission,
            author=user,
            content="IRB Office finalized approval."
        )
        messages.success(request, "Submission has been approved.")

    else:
        return JsonResponse({"status": "error", "message": "Invalid action."}, status=400)

    return redirect("irb_home", submission_id=submission.id)
@login_required
@require_POST
def irb_add_users(request, submission_id):
    submission = get_object_or_404(IRBSubmission, id=submission_id)
    data = json.loads(request.body)
    selected_users = data.get("selected_users", [])

    for user_data in selected_users:
        user = get_object_or_404(User, username=user_data["username"])
        submission.shared_with.add(user)

    return JsonResponse({"status": "success"})
@login_required
def irb_get_users(request, submission_id):
    submission = get_object_or_404(IRBSubmission, id=submission_id)
    users = submission.shared_with.all()
    users_list = [
        {
            "username": u.username,
            "first_name": u.first_name,
            "last_name": u.last_name,
        }
        for u in users
    ]
    return JsonResponse({"users": users_list})
@login_required
def irb_meetings_dashboard(request, org_id):
    user = request.user

    # Get all active IRB memberships for the user
    memberships = IRBMember.objects.filter(
        user=user,
        is_active=True
    ).select_related('committee__organization')

    # Try to match one to the current org
    current_membership = memberships.filter(committee__organization_id=org_id).first()

    # If no membership for this org, redirect to the user's own org's dashboard
    if not current_membership:
        user_default_membership = memberships.first()
        if user_default_membership:
            correct_org_id = user_default_membership.committee.organization.id
            return redirect('irb_meetings_dashboard', org_id=correct_org_id)
        else:
            # No memberships at all
            return HttpResponseForbidden("You are not assigned to any IRB committees.")

    is_chair = current_membership.role == 'chair'

    meetings = Meeting.objects.filter(
        organization_id=current_membership.committee.organization.id,
        type='irb'
    ).order_by('-date')

    if request.method == "POST":
        if not is_chair:
            return HttpResponseForbidden("Only the IRB Chair may create meetings.")

        form = MeetingForm(request.POST)
        if form.is_valid():
            meeting = form.save(commit=False)
            meeting.organization_id = org_id
            meeting.created_by = request.user
            meeting.type = 'irb'
            meeting.save()

            attendee_ids = [int(id.strip()) for id in request.POST.get('attendees', '').split(',') if id.strip().isdigit()]
            if not attendee_ids:
                messages.error(request, "Please select at least one attendee.")
                return redirect('irb_meetings_dashboard', org_id=org_id)

            attendees = User.objects.filter(id__in=attendee_ids)
            meeting.attendees.set(attendees)

            return redirect('irb_meetings_dashboard', org_id=org_id)
    else:
        form = MeetingForm()

    return render(request, "admin/irb_meetings_dashboard.html", {
        "form": form if is_chair else None,
        "meetings": meetings,
        "org_id": org_id,
        "is_chair": is_chair
    })

def has_irb_quorum(item):
    total_attendees = item.meeting.attendees.count()
    total_votes = item.meetingvote_set.filter(item=item).count()
    return total_votes >= total_attendees  # You can change to >= ceil(0.5 * total_attendees) if needed

def irb_meeting_detail(request, meeting_id):
    meeting = get_object_or_404(Meeting, id=meeting_id, type='irb')
    items = list(meeting.items.select_related('submission_irb'))

    committee = getattr(meeting.organization, "irb_committee", None)

    # Access check
    has_access = IRBMember.objects.filter(
        user=request.user,
        committee=committee,
        is_active=True
    ).exists()
    if not has_access:
        return render(request, '403.html', status=403)

    # Chair check
    user_is_chair = IRBMember.objects.filter(
        user=request.user,
        committee=committee,
        role='chair',
        is_active=True
    ).exists()

    # Annotate each item with quorum met status
    for item in items:
        total_attendees = meeting.attendees.count()
        total_votes = item.meetingvote_set.count()
        item.has_quorum = total_votes >= total_attendees  # or threshold logic

    # Handle chair's decision
    if request.method == "POST" and user_is_chair and "final_decision_item_id" in request.POST:
        item_id = request.POST.get("final_decision_item_id")
        decision = request.POST.get("decision")
        item = get_object_or_404(MeetingItem, id=item_id, meeting=meeting)

        if item.submission_irb:
            if decision == "approve":
                item.submission_irb.status = "Post IRB Review"
            elif decision == "send_back":
                item.submission_irb.status = "IRB Review Revision"
            item.submission_irb.save()
            messages.success(request, f"Decision '{decision}' recorded.")
            return redirect('irb_meeting_detail', meeting_id=meeting.id)

    is_adding_item = request.method == "POST" and "final_decision_item_id" not in request.POST
    form = MeetingItemForm(request.POST if is_adding_item else None, meeting_type='irb', organization=meeting.organization)
    if request.method == "POST" and user_is_chair and "final_decision_item_id" not in request.POST:
        if form.is_valid():
            item = form.save(commit=False)
            item.meeting = meeting

            # ✅ Explicitly assign the submission to the item
            item.submission_irb = form.cleaned_data.get("submission_irb")
            item.submission_iacuc = form.cleaned_data.get("submission_iacuc")

            if item.submission_irb and item.submission_irb.status != "IRB Review":
                messages.error(request, "Only IRB submissions in 'IRB Review' status can be added.")
            else:
                item.save()
                messages.success(request, "Meeting item added.")
                return redirect('irb_meeting_detail', meeting_id=meeting.id)
    return render(request, "admin/irb_meeting_detail.html", {
        "meeting": meeting,
        "items": items,
        "form": form,
        "user_is_chair": user_is_chair,
    })

@login_required
def search_irb_members(request):
    query = request.GET.get("query", "").strip()
    org_id = request.user.organization_id
    terms = query.split()
    if len(terms) == 2:
        first, last = terms
        member_q = Q(user__first_name__icontains=first) & Q(user__last_name__icontains=last)
    else:
        member_q = (
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(user__username__icontains=query)
        )

    members = IRBMember.objects.filter(
        committee__organization__id=org_id,
        is_active=True
    ).filter(member_q).select_related("user")

    results = [{
        "id": member.user.id,
        "name": member.user.get_full_name() or member.user.username,
        "role": member.get_role_display()
    } for member in members]

    return JsonResponse({"users": results})
