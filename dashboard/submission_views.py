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
def add_project_task(request, org_id, project_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            title = data.get('title', '')
            description = data.get('description', '')
            due_date = data.get('due_date', '')
            assignees = data.get('assignees', [])
            assigned_by = request.user

            project = get_object_or_404(Project, id=project_id)

            # Create the task
            task = ProjectTask.objects.create(
                project=project,
                title=title,
                description=description,
                due_date=due_date,
                assigned_by=assigned_by,
            )

            # Add assignees
            assignee_users = User.objects.filter(username__in=assignees)
            task.assignees.add(*assignee_users)
            task.save()

            return JsonResponse({'status': 'success', 'message': 'Task added successfully.'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})

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
def list_project_tasks(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    tasks = ProjectTask.objects.filter(project=project).order_by('-created_at')
    task_list = []
    for task in tasks:
        task_list.append({
            'task_id': task.task_id,
            'title': task.title,
            'task_type': task.get_task_type_display(),
            'task_category': task.get_task_category_display(),
            'description': task.description,
            'status': task.get_status_display(),  # Include status
            'created_at': task.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'due_date': task.due_date.strftime('%Y-%m-%d') if task.due_date else 'N/A',
            'assigned_by': task.assigned_by.username,
            'assignees': [user.username for user in task.assignees.all()],
            'completed_by': task.task_completed_by.username if task.task_completed_by else 'N/A',  # Completed by
            'completed_at': task.completed_at.strftime('%Y-%m-%d %H:%M:%S') if task.completed_at else 'N/A'  # Completed timestamp
        })
    return JsonResponse({'tasks': task_list})

@login_required
def get_project_tasks(request, org_id, project_id):
    project = get_object_or_404(Project, id=project_id)
    tasks = ProjectTask.objects.filter(project=project)

    task_data = [
        {
            'task_id': task.task_id,
            'title': task.title,
            'description': task.description,
            'task_type': task.get_task_type_display(),
            'task_category': task.get_task_category_display(),
            'created_at': task.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            'due_date': task.due_date.strftime("%Y-%m-%d") if task.due_date else 'N/A',
            'status': task.status,
            'assigned_by': task.assigned_by.username,
            'assignees': [user.username for user in task.assignees.all()],
            'completed_by': task.task_completed_by.username if task.task_completed_by else 'N/A',
            'completed_at': task.completed_at.strftime("%Y-%m-%d %H:%M:%S") if task.completed_at else 'N/A',
            'attachments': [
                {
                    'id': attachment.id,
                    'file_url': attachment.file.url,
                    'uploaded_by': attachment.uploaded_by.username if attachment.uploaded_by else 'Unknown',
                    'uploaded_at': attachment.uploaded_at.strftime("%Y-%m-%d %H:%M:%S"),
                }
                for attachment in task.attachments.all()
            ],
            'comments': [
                {
                    'id': comment.id,
                    'author': comment.author.username if comment.author else 'Unknown',
                    'content': comment.content,
                    'created_at': comment.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                }
                for comment in task.comments.all()
            ],
        }
        for task in tasks
    ]

    return JsonResponse({'tasks': task_data})
@login_required
@csrf_exempt
def add_task_attachment(request, project_id, task_id):
    task = get_object_or_404(ProjectTask, project_id=project_id, task_id=task_id)
    if request.method == "POST":
        form = TaskAttachmentForm(request.POST, request.FILES)
        if form.is_valid():
            attachment = form.save(commit=False)
            attachment.task = task
            attachment.uploaded_by = request.user
            attachment.save()
            return JsonResponse({
                'status': 'success',
                'message': 'Attachment uploaded successfully!',
                'attachment': {
                    'id': attachment.id,
                    'file_url': attachment.file.url,
                    'uploaded_by': attachment.uploaded_by.username if attachment.uploaded_by else 'Unknown',
                    'uploaded_at': attachment.uploaded_at.strftime("%Y-%m-%d %H:%M:%S"),
                }
            })
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid file upload.'})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})

@login_required
@csrf_exempt
def add_task_comment(request, project_id, task_id):
    task = get_object_or_404(ProjectTask, project_id=project_id, task_id=task_id)
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            content = data.get('content', '').strip()

            if not content:
                return JsonResponse({'status': 'error', 'message': 'Comment content cannot be empty.'})

            # Create the comment
            comment = TaskComment.objects.create(
                task=task,
                author=request.user,
                content=content
            )
            return JsonResponse({
                'status': 'success',
                'message': 'Comment added successfully!',
                'comment': {
                    'id': comment.id,
                    'author': comment.author.username,
                    'content': comment.content,
                    'created_at': comment.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                }
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f'Error processing request: {str(e)}'})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})


@login_required
def task_detail(request, project_id, task_id):
    task = get_object_or_404(ProjectTask, project_id=project_id, task_id=task_id)

    attachments = [
        {
            'id': attachment.id,
            'file_url': attachment.file.url,
            'uploaded_by': attachment.uploaded_by.username if attachment.uploaded_by else 'Unknown',
            'uploaded_at': attachment.uploaded_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for attachment in task.attachments.all()
    ]

    comments = [
        {
            'id': comment.id,
            'author': comment.author.username if comment.author else 'Unknown',
            'content': comment.content,
            'created_at': comment.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for comment in task.comments.all()
    ]

    task_data = {
        'task_id': task.task_id,
        'title': task.title,
        'description': task.description,
        'task_type': task.get_task_type_display(),
        'task_category': task.get_task_category_display(),
        'created_at': task.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        'due_date': task.due_date.strftime("%Y-%m-%d") if task.due_date else 'N/A',
        'status': task.status,
        'assigned_by': task.assigned_by.username,
        'assignees': [user.username for user in task.assignees.all()],
        'completed_by': task.task_completed_by.username if task.task_completed_by else 'N/A',
        'completed_at': task.completed_at.strftime("%Y-%m-%d %H:%M:%S") if task.completed_at else 'N/A',
        'attachments': attachments,
        'comments': comments,
    }

    return JsonResponse({'task': task_data})
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
def package_display(request, org_id, package_id, project_id):
    try:
        # 📝 Step 1: Use the project_id directly from the function argument
        print(f"✅ Received Project ID: {project_id}")
        request.session["project_id"] = project_id
        
        # 🔥 Log the final project_id that will be used

        print(f"✅ Final Project ID to use: {project_id}")
        project = get_object_or_404(Project, id=project_id)

        # 📝 Step 4: Retrieve the draft using the correctly set project_id
        draft = SubmittedPackage.objects.filter(
            org_id=org_id,
            package_id=package_id,
            project_id=project_id,
            is_draft=True
        ).last()
        # Initialize draft data variables
        sf424_data = {}
        rr_budget_data = {}
        budget_periods = []
        cumulative_totals = {}
        senior_key_person_data = {}
        project_performance_data = {}
        RR_Other_Info_data = {}
        
        phs_cover_page_data = {}
        
        phs_human_subject_data = {}
        draft_exists = False
        
        # 📝 Step 5: Check if draft exists
        if draft:
            try:
                # Load the data from the draft, ensuring proper JSON deserialization
                sf424_data = json.loads(draft.sf424_data) if isinstance(draft.sf424_data, str) else draft.sf424_data
                
                try:
                    project_performance_data = (
                        json.loads(draft.project_performance_data)
                        if isinstance(draft.project_performance_data, str)
                        else draft.project_performance_data or {}
                    )
                except (json.JSONDecodeError, TypeError):
                    project_performance_data = {}
                # ✅ Checkbox Confirmation
                if hasattr(draft, 'RR_Other_Info_data') and draft.RR_Other_Info_data:
                    if isinstance(draft.RR_Other_Info_data, str):
                        try:
                            RR_Other_Info_data = json.loads(draft.RR_Other_Info_data)
                        except json.JSONDecodeError:
                            RR_Other_Info_data = {}
                    elif isinstance(draft.RR_Other_Info_data, dict):
                        RR_Other_Info_data = draft.RR_Other_Info_data
                    else:
                        RR_Other_Info_data = {}
                else:
                    RR_Other_Info_data = {}

                # ✅ Add this immediately after loading RR_Other_Info_data
                rr_other_info_file_fields = {
                    7: "project_summary_abstract",
                    8: "project_narrative",
                    9: "bibliography_references",
                    10: "facilities_resources",
                    11: "equipment_description",
                    12: "other_attachments_1",
                    13: "other_attachments_2"
                }
                rr_other_info_attachments = [
                    {"name": "project_summary_abstract", "label": "7. Project Summary/Abstract"},
                    {"name": "project_narrative", "label": "8. Project Narrative"},
                    {"name": "bibliography_references", "label": "9. Bibliography & References Cited"},
                    {"name": "facilities_resources", "label": "10. Facilities & Other Resources"},
                    {"name": "equipment_description", "label": "11. Equipment"},
                ]
                for i, actual_key in rr_other_info_file_fields.items():
                    RR_Other_Info_data[f"existing_attachment_{i}"] = RR_Other_Info_data.get(actual_key, "No file uploaded")
                
                phs_cover_page_data = draft.phs_cover_page_data or {}
                # ✅ Feedback Form
                phs_human_subject_data = json.loads(draft.phs_human_subject_data) if hasattr(draft, 'phs_human_subject_data') and draft.phs_human_subject_data else {}
                print("🧠 Loaded phs_human_subject_data for display:", phs_human_subject_data)  # 🔍 Add this
                # Load other draft-related data with proper handling for JSON strings and lists
                if isinstance(draft.rr_budget_data, str):
                    rr_budget_data = json.loads(draft.rr_budget_data) if draft.rr_budget_data else {}
                else:
                    rr_budget_data = draft.rr_budget_data

                if isinstance(draft.budget_periods, str):
                    budget_periods = json.loads(draft.budget_periods) if draft.budget_periods else []
                else:
                    budget_periods = draft.budget_periods

                if isinstance(draft.cumulative_totals, str):
                    cumulative_totals = json.loads(draft.cumulative_totals) if draft.cumulative_totals else {}
                else:
                    cumulative_totals = draft.cumulative_totals
                if draft and hasattr(draft, 'senior_key_person_data'):
                    if isinstance(draft.senior_key_person_data, str):
                        try:
                            senior_key_person_data = json.loads(draft.senior_key_person_data)
                            print("✅ Loaded Senior Key person for display:", senior_key_person_data)
                            if not isinstance(senior_key_person_data, list):
                                senior_key_person_data = []
                        except json.JSONDecodeError:
                            senior_key_person_data = []
                    elif isinstance(draft.senior_key_person_data, list):
                        senior_key_person_data = draft.senior_key_person_data               
                    else:
                        senior_key_person_data = []
                if hasattr(draft, "phs_plan_data"):
                    if isinstance(draft.phs_plan_data, str):
                        try:
                            phs_plan_data = json.loads(draft.phs_plan_data)
                        except json.JSONDecodeError:
                            phs_plan_data = {}
                    elif isinstance(draft.phs_plan_data, dict):
                        phs_plan_data = draft.phs_plan_data
                    else:
                        phs_plan_data = {}
                draft_exists = True
                print(f"✅ Draft found for user {request.user.username}, package ID {package_id}, project ID {project_id}")
            except json.JSONDecodeError as e:
                print(f"❌ JSON decoding error: {str(e)}")
        else:
            print(f"❌ No draft found for user {request.user.username}, package ID {package_id}, project ID {project_id}")
        sf424_questions = [
            {"key": "submission_types", "label": "1. Type of Submission"},
            {"key": "date_submitted", "label": "2. Date Submitted"},
            {"key": "applicant_identifier", "label": "2. Applicant Identifier"},
            {"key": "date_received_by_state", "label": "3. Date Received by State"},
            {"key": "state_application_identifier", "label": "4. State Application Identifier"},
            {"key": "federal_identifier", "label": "4a. Federal Identifier"},
            {"key": "agency_routing_identifier", "label": "4b. Agency Routing Identifier"},
            {"key": "previous_grants_gov_tracking_id", "label": "4c. Previous Grants.gov Tracking ID"},
            {"key": "applicant_information", "label": "* 5. Applicant Information"},
            {"key": "ein", "label": "* 6. Employer Identification (EIN or TIN)"},
            {"key": "applicant_type", "label": "* 7. Type of Applicant"},
            {"key": "application_type", "label": "* 8. Type of Application"},
            {"key": "federal_agency_name", "label": "9. Name of Federal Agency"},
            {"key": "assistance_listing_number", "label": "10. Assistance Listing Number"},
            {"key": "assistance_listing_title", "label": "10. Assistance Listing Title"},
            {"key": "project_title", "label": "* 11. Descriptive Title of Applicant's Project"},
            {"key": "project_start_date", "label": "12. Proposed Project: * a. Start Date"},
            {"key": "project_end_date", "label": "12. Proposed Project: * b. End Date"},
            {"key": "congressional_district", "label": "13. Congressional Districts Of Applicant"},
            {"key": "pd_pi_contact_info", "label": "* 14. Project Director / Principal Investigator Contact Information"},
            {"key": "estimated_funding", "label": "15. Estimated Funding ($)"},
            {"key": "executive_order_12372", "label": "* 16. Is Application Subject to Review By State Under Executive Order 12372 Process?"},
            {"key": "certification", "label": "17. Certification Statement"},
            {"key": "lobbying_disclosure", "label": "* 18. SFLLL (Disclosure of Lobbying Activities) or Other Explanatory Documentation"},
            {"key": "authorized_representative", "label": "* 19. Authorized Representative Information"},
            {"key": "pre_application_attachment", "label": "* 20. Pre-Application Attachment"},
            {"key": "cover_letter_attachment", "label": "* 21. Cover Letter Attachment"},
        ]
        sf424_questions_display = {
            "submission_types": "Type of Submission",
            "date_submitted": "Date Submitted",
            "applicant_identifier": "Applicant Identifier",
            "date_received_by_state": "Date Received by State",
            "state_application_identifier": "State Application Identifier",
            "federal_identifier": "Federal Identifier",
            "agency_routing_identifier": "Agency Routing Identifier",
            "previous_grants_gov_tracking_id": "Previous Grants.gov Tracking ID",
            "applicant_information": "*Applicant Information",
            "ein": "* Employer Identification (EIN or TIN)",
            "applicant_type": "* Type of Applicant",
            "application_type": "* Type of Application",
            "federal_agency_name": "Name of Federal Agency",
            "assistance_listing_number": "Assistance Listing Number",
            "assistance_listing_title": "Assistance Listing Title",
            "project_title": "* Descriptive Title of Applicant's Project",
            "project_start_date": "Proposed Project: * a. Start Date",
            "project_end_date": "Proposed Project: * b. End Date",
            "congressional_district": "Congressional Districts Of Applicant",
            "pd_pi_contact_info": "Project Director / Principal Investigator Contact Information",
            "estimated_funding": "Estimated Funding ($)",
            "executive_order_12372": "* Is Application Subject to Review By State Under Executive Order 12372 Process?",
            "certification": "Certification Statement",
            "lobbying_disclosure": "* SFLLL (Disclosure of Lobbying Activities) or Other Explanatory Documentation",
            "authorized_representative": "* Authorized Representative Information",
            "pre_application_attachment": "* Pre-Application Attachment",
            "cover_letter_attachment": "* Cover Letter Attachment",
        }
        sf424_status = {}
        for question, value in sf424_data.items():
            if isinstance(value, list):
                # Mark as answered if the list has at least one non-empty element
                sf424_status[question] = any(item.strip() for item in value if isinstance(item, str))
            elif isinstance(value, str):
                # Mark as answered if the string is neither empty nor the literal "Not Provided"
                sf424_status[question] = value.strip() not in ["", "Not Provided"]
            elif value is not None:
                # Consider any non-empty, non-None value as answered
                sf424_status[question] = True
            else:
                sf424_status[question] = False
        

        def load_json(file_name):
            try:
                file_path = os.path.join(settings.BASE_DIR, "static", file_name)
                with open(file_path, "r") as file:
                    return json.load(file)
            except Exception as e:
                print(f"❌ Error loading {file_name}: {str(e)}")
                return []

        name_titles = load_json("name_titles.json")
        prefixes = name_titles.get("prefixes", [])
        suffixes = name_titles.get("suffixes", [])
        countries = load_json("countries.json")
        states = load_json("states.json")
        applicant_types = load_json("applicant_types.json")
        print(f"✅ Loaded prefixes, suffixes, countries, states, and applicant types")
        # 📝 Step 6: Get the package, allowing for null organization
        package = FormPackage.objects.filter(id=package_id).first()
        if not package:
            print(f"❌ No FormPackage matches the given query. Package ID: {package_id}")
            return HttpResponse("Form Package not found", status=404)

        

    except FormPackage.DoesNotExist:
        print(f"❌ No FormPackage matches the given query. Package ID: {package_id}, Org ID: {org_id}")
        return HttpResponse("Form Package not found", status=404)

    # 📝 Step 7: Fetch package forms and user data
    package_forms = list(PackageForm.objects.filter(package=package))
    user = request.user
    

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
    additional_forms = list(package.package_forms.all())
    all_forms = additional_forms  # If no PDF forms, this is enough
    session_progress_key = f"{org_id}_{package_id}_progress"
    form_progress = request.session.get(session_progress_key, {})

    selected_form_id = request.GET.get("form") or (str(all_forms[0].id) if all_forms else None)
    selected_form = next((form for form in all_forms if str(form.id) == selected_form_id), None)
    current_index = next((i for i, form in enumerate(all_forms) if str(form.id) == selected_form_id), None)
    previous_form = all_forms[current_index - 1] if current_index is not None and current_index > 0 else None
    next_form = all_forms[current_index + 1] if current_index is not None and current_index < len(all_forms) - 1 else None

    print(f"Selected Form: {selected_form}")
    print(f"Previous Form: {previous_form}")
    
    print(f"Next Form: {next_form}")
    try:
        access = ProjectAccess.objects.get(user=user, project=project)
        print(f"👤 User '{user.username}' has permission: '{access.permission}' (can_edit={access.can_edit})")
    except ProjectAccess.DoesNotExist:
        print(f"🚫 User '{user.username}' has NO access to this project.")
    # ⬇ Add this before the return statement, once selected_form is known
    if selected_form and selected_form.html_template_name == "admin/fill_out_PHS_Plan.html":
        if not 'phs_plan_data' in locals():
            phs_plan_data = {}
        context_phs_plan_data = phs_plan_data  # fallback to empty if not set
    else:
        context_phs_plan_data = {}
    form_template = selected_form.html_template_name if selected_form else None
    # 🔍 DEBUG: Log what type this is and what the actual value is
    print(f"form_template type: {type(form_template)}")
    print(f"form_template raw value: {form_template}")
    exemption_numbers = [str(i) for i in range(1, 9)]

    return render(request, "admin/package_display.html", {
        "package": package,
        "can_edit": access.can_edit if 'access' in locals() else False,
        "project_id": project_id,
        "org_id": org_id,
        "package_id": package_id,
        "package_forms": package_forms,
        "exemption_numbers": exemption_numbers,
        "additional_forms": additional_forms,
        "selected_form": selected_form,
        "form_id": selected_form.id if selected_form else None,
        "template_name": selected_form.html_template_name if selected_form else None,
        "form_template": form_template,
        "user_data": user_data,
        "sf424_status": sf424_status,
        "sf424_questions_metadata": sf424_questions,
        "form_progress": form_progress,
        "previous_form": previous_form,
        "next_form": next_form,
        "draft_exists": draft_exists,
        "sf424_questions_display": sf424_questions_display,
        "rr_other_info_attachments": rr_other_info_attachments,
        "prefixes": prefixes,
        "senior_key_person_data": senior_key_person_data,
        "project_performance_data": project_performance_data,
        "RR_Other_Info_data": RR_Other_Info_data,
        "RR_Other_Info_data_json": json.dumps(RR_Other_Info_data),
        "phs_cover_page_data": phs_cover_page_data,
        "phs_human_subject_data": phs_human_subject_data,
        "suffixes": suffixes,
        "countries": countries,
        "states": states,
        "applicant_types": applicant_types,
        "budget_periods": json.dumps(budget_periods),
        "budget_periods_raw": budget_periods,
        "cumulative_totals": json.dumps(cumulative_totals),
        "sf424_data": sf424_data,  # Pass as dictionary
        "rr_budget_data": json.dumps(rr_budget_data),
        "phs_plan_data": json.dumps(context_phs_plan_data),
        "phs_data": context_phs_plan_data,
        "attachment_fields": [
            {"name": "introductionAttachment", "label": "1. Introduction to Application"},
            {"name": "specificAimsAttachment", "label": "2. Specific Aims"},
            {"name": "researchStrategyAttachment", "label": "3. Research Strategy"},
            {"name": "progressReportPublicationList", "label": "4. Progress Report Publication List"},
            {"name": "protectionHumanSubjectsAttachment", "label": "5. Protection of Human Subjects"},
            {"name": "inclusionWomenMinoritiesAttachment", "label": "6. Inclusion of Women and Minorities"},
            {"name": "targetedPlannedEnrollmentAttachment", "label": "7. Targeted/Planned Enrollment"},
            {"name": "inclusionEnrollmentReportAttachment", "label": "8. Inclusion Enrollment Report"},
            {"name": "vertebrateAnimalsAttachment", "label": "9. Vertebrate Animals"},
            {"name": "selectAgentResearchAttachment", "label": "10. Select Agent Research"},
            {"name": "multiplePDPILeadershipPlan", "label": "11. Multiple PD/PI Leadership Plan"},
            {"name": "consortiumContractualArrangements", "label": "12. Consortium/Contractual Arrangements"},
        ],
    })


@login_required
def download_phs_research_plan_pdf(request, org_id, form_id):
    """Generate and serve the filled PHS Research Plan as a downloadable PDF."""
    submission = get_object_or_404(SubmittedPackage, id=form_id, user=request.user)

    # You may want to adjust this key depending on how it's stored
    phs_data = submission.phs_plan_data
    attachment_fields = [
        {"name": "introductionAttachment", "label": "1. Introduction to Application"},
        {"name": "specificAimsAttachment", "label": "2. Specific Aims"},
        {"name": "researchStrategyAttachment", "label": "3. Research Strategy"},
        {"name": "progressReportPublicationList", "label": "4. Progress Report Publication List"},
        {"name": "protectionHumanSubjectsAttachment", "label": "5. Protection of Human Subjects"},
        {"name": "inclusionWomenMinoritiesAttachment", "label": "6. Inclusion of Women and Minorities"},
        {"name": "targetedPlannedEnrollmentAttachment", "label": "7. Targeted/Planned Enrollment"},
        {"name": "inclusionEnrollmentReportAttachment", "label": "8. Inclusion Enrollment Report"},
        {"name": "vertebrateAnimalsAttachment", "label": "9. Vertebrate Animals"},
        {"name": "selectAgentResearchAttachment", "label": "10. Select Agent Research"},
        {"name": "multiplePDPILeadershipPlan", "label": "11. Multiple PD/PI Leadership Plan"},
        {"name": "consortiumContractualArrangements", "label": "12. Consortium/Contractual Arrangements"},
    ]

    html_string = render_to_string(
        "admin/PHS_Research_Plan_Answers.html",
        {
            "phs_data": phs_data,
            "attachment_fields": attachment_fields,
            "submission": submission,
        }
    )

    pdf_css = CSS(string="""
        @page { size: Letter; margin: 0.5in; }
        body { font-family: 'Times New Roman', serif; font-size: 10pt; margin: 0; }
        table { width: 100%; border-collapse: collapse; font-size: 9pt; }
        td, th { border: 1px solid black; padding: 4px; word-wrap: break-word; }
        input { border: none; background: transparent; width: 100%; font-size: 9pt; }
        .TableHeader { font-weight: bold; background-color: #f0f0f0; }
    """)

    with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as pdf_file:
        HTML(string=html_string).write_pdf(pdf_file.name, stylesheets=[pdf_css])

        with open(pdf_file.name, "rb") as pdf:
            response = HttpResponse(pdf.read(), content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="PHS_Research_Plan_{submission.submission_name}.pdf"'
            return response

@login_required
def save_full_package_draft(request, org_id, package_id, project_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    print("📂 FILES received:", request.FILES)
    project = get_object_or_404(Project, id=project_id)
    def compute_file_hash_from_path(path):
        sha256 = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    package = get_object_or_404(FormPackage, id=package_id)
    user = request.user

    # Get existing draft or create a new one
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

    try:
        # Raw incoming data
        sf424_raw = request.POST.get("sf424_data")

        rr_budget_raw = request.POST.get("rr_budget_data")
        budget_periods_raw = request.POST.get("budget_periods")
        cumulative_totals_raw = request.POST.get("cumulative_totals")
        senior_key_person_raw = request.POST.get("senior_key_person_data")
        project_performance_raw = request.POST.get("project_performance_data")
        phs_human_subject_raw = request.POST.get("phs_human_subject_data")
        rr_other_info_raw = request.POST.get("RR_Other_Info_data")
    
        phs_cover_page_raw = request.POST.get("phs_cover_page_data")
        def create_project_attachment(file_url, user, project):
            if not file_url or file_url == "No file uploaded":
                return

            from urllib.parse import urlparse, unquote

            parsed = urlparse(file_url)
            relative_path = parsed.path
            if relative_path.startswith(settings.MEDIA_URL):
                relative_path = relative_path[len(settings.MEDIA_URL):]
            relative_path = unquote(relative_path).lstrip("/")
            full_path = os.path.join(settings.MEDIA_ROOT, relative_path)

            if not os.path.exists(full_path):
                print(f"❌ File not found for attachment copy: {full_path}")
                return

            file_hash = compute_file_hash_from_path(full_path)

            if ProjectAttachment.objects.filter(project=project, file_hash=file_hash).exists():
                print(f"⚠️ Duplicate file skipped based on hash: {file_hash}")
                return

            filename = os.path.basename(full_path)
            normalized_path = f"project_attachments/{filename}"

            with open(full_path, 'rb') as f:
                django_file = File(f)
                attachment = ProjectAttachment(project=project, uploaded_by=user)
                attachment.file.save(filename, django_file, save=False)
                attachment.file_hash = file_hash
                attachment.save()
                print(f"📎 New ProjectAttachment created with hash: {file_hash}")
        def safe_upload(storage_path, uploaded_file):
            if default_storage.exists(storage_path):
                print(f"⚠️ Skipping upload, file already exists: {storage_path}")
                return default_storage.url(storage_path)
            return default_storage.url(default_storage.save(storage_path, uploaded_file))
        def maybe_create_attachment(file_url):
            if not file_url or file_url == "No file uploaded":
                return

            from urllib.parse import urlparse, unquote

            parsed = urlparse(file_url)
            relative_path = parsed.path
            if relative_path.startswith(settings.MEDIA_URL):
                relative_path = relative_path[len(settings.MEDIA_URL):]
            relative_path = unquote(relative_path).lstrip("/")
            full_path = os.path.join(settings.MEDIA_ROOT, relative_path)

            if not os.path.exists(full_path):
                print(f"❌ File not found for dedup check: {full_path}")
                return

            file_hash = compute_file_hash_from_path(full_path)

            if ProjectAttachment.objects.filter(project=project, file_hash=file_hash).exists():
                print(f"⚠️ Skipped hash-duplicate ProjectAttachment: {file_hash}")
                return

            create_project_attachment(file_url, user, project)
                # Parse raw JSON s  afely
        try:
            parsed_sf424_data = json.loads(sf424_raw) if sf424_raw else {}
        except json.JSONDecodeError:
            parsed_sf424_data = {}

        try:
            parsed_rr_budget_data = json.loads(rr_budget_raw) if rr_budget_raw else {}
        except json.JSONDecodeError:
            parsed_rr_budget_data = {}
        try:
            rr_other_info_data = json.loads(rr_other_info_raw) if rr_other_info_raw else {}
            print("🧪 RR_Other_Info_data parsed:", rr_other_info_data)
        except json.JSONDecodeError:
            rr_other_info_data = {}

        try:
            parsed_budget_periods = json.loads(budget_periods_raw) if budget_periods_raw else []
        except json.JSONDecodeError:
            parsed_budget_periods = []

        try:
            parsed_cumulative_totals = json.loads(cumulative_totals_raw) if cumulative_totals_raw else {}
        except json.JSONDecodeError:
            parsed_cumulative_totals = {}

        project_performance_data = json.loads(project_performance_raw) if project_performance_raw else {}
        phs_cover_page_data = json.loads(phs_cover_page_raw) if phs_cover_page_raw else {}
        try:
            senior_key_person_data = json.loads(senior_key_person_raw) if senior_key_person_raw else []
            for i, person in enumerate(senior_key_person_data):
                # 🔁 Replace with uploaded file URL if exists
                for field in ["bio_sketch", "current_pending_support"]:
                    file_field_name = f"{field}_{i}"
                    uploaded_file = request.FILES.get(file_field_name)
                    if uploaded_file:
                        path = default_storage.save(
                            f"senior_key_person/{project_id}_{file_field_name}_{uploaded_file.name}",
                            uploaded_file
                        )
                        person[field] = default_storage.url(path)
                    else:
                        # Preserve existing value if file not re-uploaded
                        person[field] = person.get(field, "No file uploaded")

            # 📎 Automatically copy bio_sketch and pending support to Project Attachments
            for person in senior_key_person_data:
                for field in ["bio_sketch", "current_pending_support"]:
                    file_url = person.get(field)
                    maybe_create_attachment(file_url)

            if not isinstance(senior_key_person_data, list):
                senior_key_person_data = []

        except json.JSONDecodeError:
            senior_key_person_data = []
        try:
            phs_human_subject_data = json.loads(phs_human_subject_raw) if phs_human_subject_raw else {}
            print("🧪 Saving PHS Human Subject Data:", phs_human_subject_data)
        except json.JSONDecodeError:
            phs_human_subject_data = {}

        # Optional file: non-human explanation
        non_human_file = request.FILES.get("non_human_attachment")
        if non_human_file:
            path = default_storage.save(f"phs_human_subjects/non_human_{project_id}_{non_human_file.name}", non_human_file)
            phs_human_subject_data["non_human_attachment"] = default_storage.url(path)
        else:
            existing_data = draft.phs_human_subject_data if isinstance(draft.phs_human_subject_data, dict) else json.loads(draft.phs_human_subject_data or "{}")
            phs_human_subject_data["non_human_attachment"] = existing_data.get("non_human_attachment", "No file uploaded")

        maybe_create_attachment(phs_human_subject_data.get("non_human_attachment"))

        # Optional file: other requested information
        other_info_file = request.FILES.get("other_requested_info")
        if other_info_file:
            path = default_storage.save(f"phs_human_subjects/other_info_{project_id}_{other_info_file.name}", other_info_file)
            phs_human_subject_data["other_requested_info"] = default_storage.url(path)
        else:
            existing_data = draft.phs_human_subject_data if isinstance(draft.phs_human_subject_data, dict) else json.loads(draft.phs_human_subject_data or "{}")
            phs_human_subject_data["other_requested_info"] = existing_data.get("other_requested_info", "No file uploaded")

        maybe_create_attachment(phs_human_subject_data.get("other_requested_info"))
        # Study record uploads
        study_record_urls = []
        for name in phs_human_subject_data.get("study_records", []):
            file = request.FILES.get(name)
            if file:
                path = default_storage.save(f"phs_human_subjects/study_record_{project_id}_{file.name}", file)
                url = default_storage.url(path)
            else:
                existing = draft.phs_human_subject_data if isinstance(draft.phs_human_subject_data, dict) else json.loads(draft.phs_human_subject_data or "{}")
                existing_records = existing.get("study_records", [])
                url = existing_records[len(study_record_urls)] if len(existing_records) > len(study_record_urls) else "No file uploaded"
    
            study_record_urls.append(url)
            create_project_attachment(url, user, project)

        phs_human_subject_data["study_records"] = study_record_urls

        # Delayed onset studies
        for i, study in enumerate(phs_human_subject_data.get("delayed_onset_studies", [])):
            file_key = f"delayed_justification_{i}"
            uploaded = request.FILES.get(file_key)
            if uploaded:
                path = default_storage.save(f"phs_human_subjects/delayed_justification_{project_id}_{uploaded.name}", uploaded)
                url = default_storage.url(path)
                study["justification"] = url
            else:
                existing = draft.phs_human_subject_data if isinstance(draft.phs_human_subject_data, dict) else json.loads(draft.phs_human_subject_data or "{}")
                previous = existing.get("delayed_onset_studies", [])
                url = previous[i]["justification"] if i < len(previous) else "No file uploaded"
                study["justification"] = url

            maybe_create_attachment(study["justification"])
        # Load existing data from draft
        existing_sf424_data = draft.sf424_data if isinstance(draft.sf424_data, dict) else json.loads(draft.sf424_data or "{}")
        existing_rr_budget_data = draft.rr_budget_data if isinstance(draft.rr_budget_data, dict) else json.loads(draft.rr_budget_data or "{}")
        existing_budget_periods = draft.budget_periods if isinstance(draft.budget_periods, list) else json.loads(draft.budget_periods or "[]")
        existing_cumulative_totals = draft.cumulative_totals if isinstance(draft.cumulative_totals, dict) else json.loads(draft.cumulative_totals or "{}")

        # ✅ Merge the data
        sf424_data = {**existing_sf424_data, **parsed_sf424_data}
        rr_budget_data = {**existing_rr_budget_data, **parsed_rr_budget_data}
        cumulative_totals = {**existing_cumulative_totals, **parsed_cumulative_totals}

        # Merge budget periods by period_number
        # 🔁 Start with existing budget periods
        budget_period_dict = {int(p["period_number"]): p for p in existing_budget_periods if "period_number" in p}

        # 🔁 Process file uploads and update dict
        # 🔁 Process file uploads and update dict
        for period in parsed_budget_periods:
            period_num = period.get("period_number")
            if not period_num:
                continue

            period_key = int(period_num)

            # -- Senior attachment --
            senior_field = f"additional_senior_attachment_{period_key}"
            senior_file = request.FILES.get(senior_field)
            if senior_file:
                storage_path = f"rr_budget/period_{period_key}_senior_{project_id}_{senior_file.name}"
                period["additional_senior_attachment"] = safe_upload(storage_path, senior_file)
            else:
                # ✅ Get fallback from POST hidden input or from saved draft
                period["additional_senior_attachment"] = (
                    request.POST.get(f"existing_additional_senior_attachment_{period_key}")
                    or budget_period_dict.get(period_key, {}).get("additional_senior_attachment", "No file uploaded")
                )

            # -- Equipment attachment --
            equipment_field = f"equipment_attachment_{period_key}"
            equipment_file = request.FILES.get(equipment_field)
            if equipment_file:
                storage_path = f"rr_budget/period_{period_key}_equipment_{project_id}_{equipment_file.name}"
                period["equipment_attachment"] = safe_upload(storage_path, equipment_file)
            else:
                # ✅ Same fallback logic
                period["equipment_attachment"] = (
                    request.POST.get(f"existing_equipment_attachment_{period_key}")
                    or budget_period_dict.get(period_key, {}).get("equipment_attachment", "No file uploaded")
                )
            # Update budget period dict
            budget_period_dict[period_key] = period
        # ✅ Finalize updated list of budget periods (missing currently)
        budget_periods = list(budget_period_dict.values())
        # 📎 Automatically copy RR Budget attachments to Project Attachments
        for period in budget_periods:
            for field in ["additional_senior_attachment", "equipment_attachment"]:
                file_url = period.get(field)
                maybe_create_attachment(file_url)
        # Handle cover page file
        uploaded_cover = request.FILES.get("cover_page_attachment")
        if uploaded_cover:
            path = default_storage.save(f"phs_cover_page/{project_id}_cover_{uploaded_cover.name}", uploaded_cover)
            phs_cover_page_data["cover_page_attachment"] = default_storage.url(path)
        else:
            existing_cover_data = draft.phs_cover_page_data if isinstance(draft.phs_cover_page_data, dict) else json.loads(draft.phs_cover_page_data or "{}")
            phs_cover_page_data["cover_page_attachment"] = existing_cover_data.get("cover_page_attachment", "No file uploaded")
        # Handle PHS plan attachments
        phs_plan_data = {}
        existing_phs_data = draft.phs_plan_data if isinstance(draft.phs_plan_data, dict) else json.loads(draft.phs_plan_data or "{}")
        attachment_fields = [
            "introductionAttachment", "specificAimsAttachment", "researchStrategyAttachment",
            "progressReportPublicationList", "protectionHumanSubjectsAttachment", "inclusionWomenMinoritiesAttachment",
            "targetedPlannedEnrollmentAttachment", "inclusionEnrollmentReportAttachment", "vertebrateAnimalsAttachment",
            "selectAgentResearchAttachment", "multiplePDPILeadershipPlan", "consortiumContractualArrangements"
        ]
        existing_rr_other_info_data = (
            draft.RR_Other_Info_data if isinstance(draft.RR_Other_Info_data, dict)
            else json.loads(draft.RR_Other_Info_data or "{}")
        )
        def smart_merge(existing: dict, incoming: dict) -> dict:
            result = existing.copy()
            for k, v in incoming.items():
                # Don't overwrite non-empty existing values with blank ones
                if v not in [None, "", [], "No file uploaded"]:
                    result[k] = v
            return result
        merged_rr_other_info_data = smart_merge(existing_rr_other_info_data, rr_other_info_data)
        removed_keys_raw = request.POST.get("removed_attachments")
        removed_keys = json.loads(removed_keys_raw) if removed_keys_raw else []

        for key in removed_keys:
            old_url = merged_rr_other_info_data.get(key)
            if old_url and old_url != "No file uploaded":
                try:
                    # 🔍 Parse path from full URL
                    parsed = urlparse(old_url)
                    relative_path = parsed.path.replace(settings.MEDIA_URL, "").lstrip("/")

                    # 🔐 Only delete if it exists
                    if default_storage.exists(relative_path):
                        default_storage.delete(relative_path)
                        print(f"🗑️ Deleted file from storage: {relative_path}")
                    else:
                        print(f"⚠️ File not found: {relative_path}")
                except Exception as e:
                    print(f"⚠️ Failed to delete file: {old_url} — {e}")
    
            # Remove from the data to save
            merged_rr_other_info_data[key] = "No file uploaded"
        rr_other_info_file_fields = {
            "attachment_7": "project_summary_abstract",
            "attachment_8": "project_narrative",
            "attachment_9": "bibliography_references",
            "attachment_10": "facilities_resources",
            "attachment_11": "equipment_description",
            "attachment_12": "other_attachments_1",
            "attachment_13": "other_attachments_2",
            "attachment_14": "other_attachments_3",
            "attachment_15": "other_attachments_4",
            "attachment_16": "other_attachments_2",
            "attachment_17": "other_attachments_5",
            "attachment_18": "other_attachments_6",
            "attachment_19": "other_attachments_7",
            "attachment_20": "other_attachments_8",
            "attachment_21": "other_attachments_9",
        }
        # Single file fields: 7–11, 13
        for field, key in rr_other_info_file_fields.items():
            if field != "attachment_12":  # 👈 Skip multi-upload here
                uploaded = request.FILES.get(field)
                if uploaded:
                    path = default_storage.save(f"rr_other_info/{project_id}_{field}_{uploaded.name}", uploaded)
                    merged_rr_other_info_data[key] = default_storage.url(path)
                else:
                    existing = existing_rr_other_info_data.get(key, "No file uploaded")
                    merged_rr_other_info_data[key] = existing

        # ✅ Separate block for handling multiple uploads for Question 12
        existing_other_attachments = [
            existing_rr_other_info_data.get(f"other_attachments_{i+1}", "No file uploaded")
            for i in range(10)
        ]
        existing_other_attachments = [url for url in existing_other_attachments if url != "No file uploaded"]

        multi_files = request.FILES.getlist("attachment_12")
        for i, file in enumerate(multi_files):
            if len(existing_other_attachments) >= 10:
                break
            path = default_storage.save(f"rr_other_info/{project_id}_attachment_12_{i}_{file.name}", file)
            existing_other_attachments.append(default_storage.url(path))

        # Save merged list
        for i in range(10):
            key = f"other_attachments_{i+1}"
            merged_rr_other_info_data[key] = existing_other_attachments[i] if i < len(existing_other_attachments) else "No file uploaded"

        if multi_files:
            for i in range(min(10, len(multi_files))):
                file = multi_files[i]
                save_path = default_storage.save(f"rr_other_info/{project_id}_attachment_12_{i}_{file.name}", file)
                merged_rr_other_info_data[f"other_attachments_{i + 1}"] = default_storage.url(save_path)
        else:
            # Preserve any previously saved attachments 1–10
            for i in range(1, 11):
                existing = existing_rr_other_info_data.get(f"other_attachments_{i}", "No file uploaded")
                merged_rr_other_info_data[f"other_attachments_{i}"] = existing
        for field in attachment_fields:
            uploaded_file = request.FILES.get(field)
            if uploaded_file:
                path = default_storage.save(f"phs_attachments/{project_id}_{field}_{uploaded_file.name}", uploaded_file)
                phs_plan_data[field] = default_storage.url(path)
            elif field in existing_phs_data:
                phs_plan_data[field] = existing_phs_data[field]
            else:
                phs_plan_data[field] = "No file uploaded"
        attachment_fields = [
            "introductionAttachment", "specificAimsAttachment", "researchStrategyAttachment",
            "progressReportPublicationList", "protectionHumanSubjectsAttachment", "inclusionWomenMinoritiesAttachment",
            "targetedPlannedEnrollmentAttachment", "inclusionEnrollmentReportAttachment", "vertebrateAnimalsAttachment",
            "selectAgentResearchAttachment", "multiplePDPILeadershipPlan", "consortiumContractualArrangements"
        ]
        # 📎 Automatically copy to Project Attachments
        
        # Preserve file fields in sf424
        sf424_upload_fields = [
            ("sflll_attachment", "existing_sflll_attachment"),
            ("pre_application_attachment", "existing_pre_application_attachment"),
            ("cover_letter_attachment", "existing_cover_letter_attachment"),
        ]  
        
        
        for file_field, fallback_field in sf424_upload_fields:
            uploaded_file = request.FILES.get(file_field)
            if uploaded_file:
                path = default_storage.save(f"sf424_attachments/{project_id}_{file_field}_{uploaded_file.name}", uploaded_file)
                sf424_data[file_field] = default_storage.url(path)
            else:
                # Fallback: check hidden field for previously uploaded file
                fallback = request.POST.get(fallback_field)
                sf424_data[file_field] = fallback or existing_sf424_data.get(file_field, "No file uploaded")
        maybe_create_attachment(sf424_data.get("sflll_attachment"))
        maybe_create_attachment(sf424_data.get("pre_application_attachment"))
        maybe_create_attachment(sf424_data.get("cover_letter_attachment"))
        for field in attachment_fields:
            file_url = phs_plan_data.get(field)
            maybe_create_attachment(file_url)
        # Save final merged values
        # 📎 Also copy RR Other Info attachments to Project Attachments
        rr_other_info_attachment_keys = [
            "project_summary_abstract",
            "project_narrative",
            "bibliography_references",
            "facilities_resources",
            "equipment_description",
        ]

        for key in rr_other_info_attachment_keys:
            file_url = merged_rr_other_info_data.get(key)
            maybe_create_attachment(file_url)
        draft.sf424_data = sf424_data
        draft.rr_budget_data = rr_budget_data
    
        draft.budget_periods = list(budget_period_dict.values())  # ✅ This has merged periods + file URLs
        draft.cumulative_totals = cumulative_totals
        draft.phs_plan_data = phs_plan_data
        draft.phs_cover_page_data = phs_cover_page_data
        existing_data = (
            json.loads(draft.project_performance_data)
            if isinstance(draft.project_performance_data, str) else draft.project_performance_data or {}
        )
        merged_data = {**existing_data, **project_performance_data}
        draft.project_performance_data = json.dumps(merged_data)
        draft.RR_Other_Info_data = merged_rr_other_info_data
        draft.senior_key_person_data = json.dumps(senior_key_person_data)
        draft.submission_date = timezone.now()
        draft.last_edited_by = user
        draft.phs_human_subject_data = json.dumps(phs_human_subject_data)
        draft.save()
        print("✅ Saved human subject data:", draft.phs_human_subject_data)  # 🔍 Add this
        print("✅ Received Senior Key Person Data:", senior_key_person_data)
        print(f"✅ Package draft saved successfully for project {project.name}")

    except Exception as e:
        print(f"❌ Error parsing or saving form data: {e}")
        return HttpResponse("Error reading form data.", status=400)

    redirect_url = request.POST.get("redirect_url")
    if redirect_url:
        print(f"🔁 Redirecting to provided URL: {redirect_url}")
        return redirect(redirect_url)

    return redirect("package_display", org_id=org_id, package_id=package_id, project_id=project_id)

SF_424_PATH = os.path.join(os.path.dirname(__file__), "/static/pdfs/sf424_18.pdf")

def load_json(filename):
    try:
        path = os.path.join(settings.BASE_DIR, "static", filename)
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error loading {filename}: {str(e)}")
        return {}

@csrf_exempt
def get_senior_key_person_block(request):
    index = request.GET.get("index", "0")

    name_titles = load_json("name_titles.json")
    prefixes = name_titles.get("prefixes", [])
    suffixes = name_titles.get("suffixes", [])
    countries = load_json("countries.json")
    states = load_json("states.json")

    context = {
        "index": index,
        "person": None,
        "can_edit": True,
        "prefixes": prefixes,
        "suffixes": suffixes,
        "states": states,
        "countries": countries,
    }

    html = render_to_string("admin/senior_key_person_block.html", context)
    return HttpResponse(html)
@csrf_exempt
def get_project_performance_block(request):
    index = request.GET.get("index", "0")

    countries = load_json("countries.json")
    states = load_json("states.json")

    # ⬅️ Manually include default org/package/project IDs for reverse URL safety
    context = {
        "index": index,
        "site": {},
        "can_edit": True,
        "countries": countries,
        "states": states,
        "org_id": 0,  # Use dummy placeholder values to avoid reverse errors
        "package_id": 0,
        "project_id": 0,
    }

    html = render_to_string("admin/project_performance_site_block.html", context)
    return HttpResponse(html)
@login_required
def phs_cover_page_submit(request, org_id, package_id, project_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    project = get_object_or_404(Project, id=project_id)
    user = request.user
    package = get_object_or_404(FormPackage, id=package_id)

    draft, created = SubmittedPackage.objects.get_or_create(
        org_id=org_id,
        package_id=package_id,
        project=project,
        is_draft=True,
        defaults={"submission_name": f"Draft - {project.name}", "submission_date": timezone.now(), "last_edited_by": user}
    )

    try:
        # Parse JSON from hidden input
        phs_cover_data_raw = request.POST.get("phs_cover_page_data")
        phs_cover_data = json.loads(phs_cover_data_raw) if phs_cover_data_raw else {}

        # Optional file: non-human attachment
        uploaded_file = request.FILES.get("non_human_attachment")
        if uploaded_file:
            path = default_storage.save(f"phs_cover_page/{project_id}_{uploaded_file.name}", uploaded_file)
            phs_cover_data["non_human_attachment"] = default_storage.url(path)
        else:
            existing = draft.phs_cover_page_data or {}
            phs_cover_data["non_human_attachment"] = existing.get("non_human_attachment", "No file uploaded")

        draft.phs_cover_page_data = phs_cover_data
        draft.last_edited_by = user
        draft.submission_date = timezone.now()
        draft.save()

        messages.success(request, "PHS Cover Page saved successfully.")
        return redirect("package_display", org_id=org_id, package_id=package_id, project_id=project_id)

    except Exception as e:
        messages.error(request, f"Error saving PHS Cover Page: {e}")
        return redirect("package_display", org_id=org_id, package_id=package_id, project_id=project_id)
@login_required
def phs_human_subject_submit(request, org_id, package_id, project_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    project = get_object_or_404(Project, id=project_id)
    package = get_object_or_404(FormPackage, id=package_id)
    user = request.user

    draft, _ = SubmittedPackage.objects.get_or_create(
        org_id=org_id,
        package_id=package_id,
        project=project,
        is_draft=True,
        defaults={
            "submission_name": f"Draft - {project.name}",
            "submission_date": timezone.now(),
            "last_edited_by": user,
        }
    )

    try:
        data_raw = request.POST.get("phs_human_subject_data", "{}")
        try:
            data = json.loads(data_raw)
        except json.JSONDecodeError:
            data = {}

        # ✅ Handle non-human explanation attachment only
        if "non_human_attachment" in request.FILES:
            f = request.FILES["non_human_attachment"]
            path = default_storage.save(f"phs_human_subjects/{project_id}_non_human_{f.name}", f)
            data["non_human_attachment"] = default_storage.url(path)
        else:
            existing = draft.phs_human_subject_data or {}
            if isinstance(existing, str):
                try:
                    existing = json.loads(existing)
                except json.JSONDecodeError:
                    existing = {}
            data["non_human_attachment"] = existing.get("non_human_attachment", "No file uploaded")

        # ✅ Handle Other Requested Information
        if "other_requested_info" in request.FILES:
            f = request.FILES["other_requested_info"]
            path = default_storage.save(f"phs_human_subjects/{project_id}_other_info_{f.name}", f)
            data["other_requested_info"] = default_storage.url(path)
        else:
            existing = draft.phs_human_subject_data or {}
            if isinstance(existing, str):
                try:
                    existing = json.loads(existing)
                except json.JSONDecodeError:
                    existing = {}
            data["other_requested_info"] = existing.get("other_requested_info", "No file uploaded")

        # ✅ Handle study record files
        study_records = []
        for key in request.FILES:
            if key.startswith("study_record_"):
                f = request.FILES[key]
                path = default_storage.save(f"phs_human_subjects/{project_id}_study_{key}_{f.name}", f)
                study_records.append(default_storage.url(path))
        existing_study_records = []
        if isinstance(draft.phs_human_subject_data, str):
            try:
                existing_data = json.loads(draft.phs_human_subject_data)
                existing_study_records = existing_data.get("study_records", [])
            except json.JSONDecodeError:
                pass
        study_records = study_records or existing_study_records
        data["study_records"] = study_records

        # ✅ Handle delayed onset study file uploads
        delayed_studies = data.get("delayed_onset_studies", [])
        for i, study in enumerate(delayed_studies):
            file_key = f"delayed_justification_{i}"
            if file_key in request.FILES:
                f = request.FILES[file_key]
                path = default_storage.save(f"phs_human_subjects/{project_id}_delayed_{i}_{f.name}", f)
                delayed_studies[i]["justification"] = default_storage.url(path)
            else:
                if isinstance(draft.phs_human_subject_data, str):
                    try:
                        existing_data = json.loads(draft.phs_human_subject_data)
                        existing_studies = existing_data.get("delayed_onset_studies", [])
                        if i < len(existing_studies):
                            delayed_studies[i]["justification"] = existing_studies[i].get("justification", "No file uploaded")
                    except json.JSONDecodeError:
                        delayed_studies[i]["justification"] = "No file uploaded"

        data["delayed_onset_studies"] = delayed_studies

        # ✅ Final save
        draft.phs_human_subject_data = json.dumps(data)
        draft.submission_date = timezone.now()
        draft.last_edited_by = user
        draft.save()

        print("✅ Saved PHS Human Subjects data")
    except Exception as e:
        print("❌ Error in phs_human_subject_submit:", str(e))
        return HttpResponse("Failed to save PHS Human Subjects data.", status=400)

    redirect_url = request.POST.get("redirect_url")
    if redirect_url:
        return redirect(redirect_url)

    return redirect("package_display", org_id=org_id, package_id=package_id, project_id=project_id)

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
        package_id = request.POST.get("package_id")
        project_id = request.POST.get("project_id")
        package = FormPackage.objects.get(id=package_id)
        project = Project.objects.get(id=project_id)
        try:
            # Radio and checkbox fields
            proprietary_info = request.POST.get("proprietary_info", "")
            environmental_impact = request.POST.get("environmental_impact", "")
            historic_properties = request.POST.get("historic_properties", "")
            human_subjects = request.POST.get("human_subjects", "")
            vertebrate_animals = request.POST.get("vertebrate_animals", "")
            international_collab = request.POST.get("international_collaboration", "")
            exemption_numbers = request.POST.getlist("exemption_numbers")

            # Text fields
            human_assurance_number = request.POST.get("human_assurance_number", "")
            irb_approval_date = request.POST.get("irb_approval_date", "")
            animal_welfare_number = request.POST.get("animal_welfare_number", "")
            iacuc_approval_date = request.POST.get("iacuc_approval_date", "")
            environmental_explanation = request.POST.get("environmental_explanation", "")
            environmental_exemption_explanation = request.POST.get("environmental_exemption_explanation", "")
            historic_explanation = request.POST.get("historic_explanation", "")
            international_countries = request.POST.get("international_countries", "")
            international_explanation = request.POST.get("international_explanation", "")

            uploaded_file = request.FILES.get("attachments", None)

            # Save to database (you may need to adjust for your model)
            rr_info = RROtherInformation.objects.create(
                organization_id=org_id,
                package=package,
                project=project,
                proprietary_info=proprietary_info,
                environmental_impact=environmental_impact,
                historic_properties=historic_properties,
                human_subjects=human_subjects,
                vertebrate_animals=vertebrate_animals,
                international_collaboration=international_collab,
                exemption_numbers=exemption_numbers,
                human_assurance_number=human_assurance_number,
                irb_approval_date=irb_approval_date,
                animal_welfare_number=animal_welfare_number,
                iacuc_approval_date=iacuc_approval_date,
                environmental_explanation=environmental_explanation,
                environmental_exemption_explanation=environmental_exemption_explanation,
                historic_explanation=historic_explanation,
                international_countries=international_countries,
                international_explanation=international_explanation,
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
        "organization": organization,
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
