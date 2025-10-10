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


@require_POST
@login_required
def upload_project_attachment(request, org_id, project_id):
    project = get_object_or_404(Project, id=project_id)
    uploaded_file = request.FILES.get('file')

    if not uploaded_file:
        return JsonResponse({'status': 'error', 'message': 'No file uploaded.'})

    attachment = ProjectAttachment.objects.create(
        project=project,
        file=uploaded_file,
        uploaded_by=request.user
    )

    return JsonResponse({'status': 'success', 'message': 'File uploaded successfully.'})


@login_required
def get_project_attachments(request, org_id, project_id):
    project = get_object_or_404(Project, id=project_id)
    attachments = ProjectAttachment.objects.filter(project=project).order_by('-uploaded_at')
    
    data = [{
        'file_url': attachment.file.url,
        'file_name': attachment.file.name.split('/')[-1],
        'uploaded_by': attachment.uploaded_by.get_full_name() or attachment.uploaded_by.username,
        'uploaded_at': attachment.uploaded_at.strftime('%B %d, %Y %I:%M %p')
    } for attachment in attachments]

    return JsonResponse({'status': 'success', 'attachments': data})

def user_can_edit_project(user, project):
    # Admins always can edit
    if user.role in ['admin', 'principal_admin'] or user.is_superuser:
        return True

    # Org-wide editors can edit everything in their org
    if user.position_type == 'app_editor' and user.organization == project.organization:
        return True

    # Regular per-project access
    access = ProjectAccess.objects.filter(user=user, project=project).first()
    return access.can_edit if access else False
def user_can_view_project(user, project):
    if user_can_edit_project(user, project):
        return True  # Editors can view

    # Org-wide viewers can view all projects in their org
    if user.position_type == 'app_viewer' and user.organization == project.organization:
        return True

    # If in routing or user access list (as view-only)
    if user in project.routing_users.all():
        return True

    access = ProjectAccess.objects.filter(user=user, project=project).first()
    return True if access else False


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

def fill_out_phs_plan(request, org_id, form_id):
    phs_data = get_object_or_404(PHSResearchPlan, organization_id=org_id, id=form_id)

    if request.method == 'POST':
        for field in attachment_fields:
            uploaded_file = request.FILES.get(field['name'])
            if uploaded_file:
                setattr(phs_data, field['name'], uploaded_file)

        phs_data.save()
        return redirect(reverse('phs_answers', args=[org_id, form_id]))

    context = {
        'attachment_fields': attachment_fields,
        'phs_data': phs_data,
        'can_edit': True,
    }
    return render(request, 'admin/fill_out_PHS_Plan.html', context)


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
        return HttpResponse
def is_committee_member(user, project):
    opportunity = getattr(project, 'opportunity', None)
    if opportunity and hasattr(opportunity, 'committee'):
        return opportunity.committee.members.filter(id=user.id).exists()
    return False

@login_required
def score_submission(request, org_id, project_id):
    project = get_object_or_404(Project, pk=project_id)
    latest_submission = SubmittedPackage.objects.filter(project=project, is_draft=False).order_by('-submission_date').first()
    if not latest_submission or not latest_submission.opportunity:
        return HttpResponse("This submission has no associated opportunity.", status=400)

    opportunity = latest_submission.opportunity

    # Try to get existing score
    score_entry, created = ReviewScore.objects.get_or_create(
        user=request.user,
        project=project,
        opportunity=opportunity
    )

    if request.method == "POST":
        score_entry.factor_1_score = request.POST.get("factor_1_score") or None
        score_entry.factor_2_score = request.POST.get("factor_2_score") or None
        score_entry.factor_3_comment = request.POST.get("factor_3_comment", "")
        score_entry.human_subjects = request.POST.get("human_subjects", "")
        score_entry.vertebrate_animals = request.POST.get("vertebrate_animals", "")
        score_entry.biohazards = request.POST.get("biohazards", "")
        score_entry.resubmission_notes = request.POST.get("resubmission_notes", "")
        score_entry.authentication = request.POST.get("authentication", "")
        score_entry.budget_notes = request.POST.get("budget_notes", "")
        score_entry.overall_score = request.POST.get("overall_score") or None
        score_entry.overall_justification = request.POST.get("overall_justification", "")
        score_entry.save()

        messages.success(request, "Score saved successfully.")
        return redirect('committee_opportunity_projects', opportunity_id=opportunity.id)

    return render(request, 'admin/scoring_form.html', {
        'project': project,
        'org_id': org_id,
        'opportunity': opportunity,
        'user_role': 'committee_member',
        'score_entry': score_entry,
    })

@login_required
def download_all_forms_combined_pdf(request, org_id, form_id):
    submission = get_object_or_404(SubmittedPackage, id=form_id, org_id=org_id, is_draft=False)
    form_package = get_object_or_404(FormPackage, id=submission.package_id)
    form_types = form_package.get_form_types()

    # Collect form data (deserialize where needed)
    def safe_json(data):
        if isinstance(data, str):
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return {}
        return data or {}
    rr_other_info = safe_json(submission.RR_Other_Info_data)
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

    context = {
        "submission": submission,
        "sf424_data": safe_json(submission.sf424_data),
        "rr_budget_data": safe_json(submission.rr_budget_data),
        "budget_periods": safe_json(submission.budget_periods),
        "cumulative_totals": safe_json(submission.cumulative_totals),
        "is_cumulative_summary": True,  # ✅ MATCH standalone version
        "senior_key_person_data": safe_json(submission.senior_key_person_data),
        "project_performance_data": safe_json(submission.project_performance_data),
        "RR_Other_Info_data": rr_other_info,
        "rr_data": rr_other_info,
        "rr_other_info_attachments": attachment_fields,
        "phs_plan_data": safe_json(submission.phs_plan_data),
        "phs_data": safe_json(submission.phs_human_subject_data),
        "data": safe_json(submission.phs_human_subject_data),
        "attachment_fields": attachment_fields,
        "org_id": org_id,
        "form_id": form_id,
    }
    # List of templates to include
    included_templates = []
    if "sf424" in form_types:
        included_templates.append("admin/Sf424_Answers.html")
    if "rr_budget" in form_types:
        included_templates.append("admin/RR_Budget_Answers.html")
    if "skp" in form_types:
        included_templates.append("admin/senior_key_person_answers.html")
    if "site" in form_types:
        included_templates.append("admin/Project_Performance_Sites_Answers.html")
    if "rr_other_info" in form_types:
        included_templates.append("admin/RR_Other_Information_Answers.html")
    if "phs_plan" in form_types:
        included_templates.append("admin/PHS_Research_Plan_Answers.html")
    if "phs_subjects" in form_types:
        included_templates.append("admin/phs_human_subject_answers.html")

    # Combine all rendered templates into a single HTML string
    html_sections = [render_to_string(template, context) for template in included_templates]
    combined_html = "<div style='page-break-after: always;'></div>".join(html_sections)

    pdf_css = CSS(string="""
        @page { size: Letter; margin: 0.5in; }
        body { font-family: 'Times New Roman', serif; font-size: 10pt; margin: 0; }
        table { width: 100%; border-collapse: collapse; font-size: 9pt; }
        td, th { border: 1px solid black; padding: 4px; word-wrap: break-word; }
        .TableHeader { font-weight: bold; background-color: #f0f0f0; }
        .page-break { page-break-before: always; }
    """)

    with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as pdf_file:
        HTML(string=combined_html).write_pdf(pdf_file.name, stylesheets=[pdf_css])
        with open(pdf_file.name, "rb") as pdf:
            response = HttpResponse(pdf.read(), content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="Full_Submission_{submission.submission_name}.pdf"'
            return response
        