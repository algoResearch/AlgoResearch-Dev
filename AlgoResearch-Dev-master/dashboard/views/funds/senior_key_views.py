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


def senior_key_person_submit(request, org_id, form_id):
    if request.method == "POST":
        package_id = request.POST.get("package_id", "").strip()
        project_id = request.POST.get("project_id") or request.session.get("project_id")

        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return HttpResponse("Project not found", status=404)

        draft = SubmittedPackage.objects.filter(
            org_id=org_id,
            package_id=package_id,
            project=project,
            is_draft=True
        ).first()

        # 🔽 Build list of senior key persons
        num_people = len(request.POST.getlist("first_name[]"))
        senior_key_persons = []
        for i in range(num_people):
            person = {
                "prefix": request.POST.getlist("prefix[]")[i],
                "first_name": request.POST.getlist("first_name[]")[i],
                "middle_name": request.POST.getlist("middle_name[]")[i],
                "last_name": request.POST.getlist("last_name[]")[i],
                "suffix": request.POST.getlist("suffix[]")[i],
                "position_title": request.POST.getlist("position_title[]")[i],
                "department": request.POST.getlist("department[]")[i],
                "organization_name": request.POST.getlist("organization_name[]")[i],
                "division": request.POST.getlist("division[]")[i],
                "street1": request.POST.getlist("street1[]")[i],
                "street2": request.POST.getlist("street2[]")[i],
                "city": request.POST.getlist("city[]")[i],
                "county": request.POST.getlist("county[]")[i],
                "state": request.POST.getlist("state[]")[i],
                "province": request.POST.getlist("province[]")[i],
                "country": request.POST.getlist("country[]")[i],
                "zip": request.POST.getlist("zip[]")[i],
                "phone": request.POST.getlist("phone[]")[i],
                "fax": request.POST.getlist("fax[]")[i],
                "email": request.POST.getlist("email[]")[i],
                "credential": request.POST.getlist("credential[]")[i],
                "project_role": request.POST.getlist("project_role[]")[i],
                "other_project_role_category": request.POST.getlist("other_project_role_category[]")[i],
                # File upload will be handled next
            }

            # ✅ Handle file attachments
            def handle_file_upload(field_name, fallback="No file uploaded"):
                if field_name in request.FILES:
                    uploaded = request.FILES[field_name]
                    name = uploaded.name
                    path = os.path.join(settings.MEDIA_ROOT, "uploads", name)
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "wb+") as dest:
                        for chunk in uploaded.chunks():
                            dest.write(chunk)
                    return f"/media/uploads/{name}"
                return fallback

            person["bio_sketch"] = handle_file_upload(f"bio_sketch_{i}")
            person["current_pending_support"] = handle_file_upload(f"current_pending_support_{i}", fallback=request.POST.get(f"existing_current_pending_support_{i}", "No file uploaded"))


            senior_key_persons.append(person)

        # 📝 Save Draft
        if "save_draft" in request.POST:
            draft, created = SubmittedPackage.objects.get_or_create(
                org_id=org_id,
                package_id=package_id,
                project=project,
                is_draft=True,
                defaults={"submission_name": f"Draft - {project.name}", "submission_date": timezone.now()}
            )

            draft.senior_key_person_data = json.dumps(senior_key_persons)
            draft.last_edited_by = request.user
            draft.save()

            messages.success(request, "Senior/Key Person draft saved successfully.")
            return redirect("specific_project_home", org_id=org_id, project_id=project_id)

    return redirect("package_display", org_id=org_id, package_id=package_id, project_id=project_id)


@login_required
def download_senior_key_persons_pdf(request, org_id, form_id):
    """Generate and serve the Senior/Key Person Profile as a downloadable PDF."""
    submission = get_object_or_404(
        SubmittedPackage, id=form_id, org_id=org_id, is_draft=False
    )

    try:
        data = submission.senior_key_person_data
        if isinstance(data, str):
            senior_key_data = json.loads(data)
        elif isinstance(data, list):
            senior_key_data = data
        else:
            senior_key_data = []
    except json.JSONDecodeError:
        logger.warning("❗ JSON decode failed for senior_key_person_data.")
        senior_key_data = []

    # ✅ Log raw format for debugging
    logger.info(f"📦 senior_key_person_data raw type: {type(submission.senior_key_person_data)}")
    logger.info(f"📦 Parsed person count: {len(senior_key_data)}")

    # ✅ Print basic preview info
    for i, person in enumerate(senior_key_data):
        if isinstance(person, dict):
            first = person.get("first_name", "")
            last = person.get("last_name", "")
            logger.info(f"▶️ Person {i+1}: {first} {last}")
            logger.info(f"📎 Bio Sketch: {person.get('bio_sketch')}")
            logger.info(f"📎 Current & Pending: {person.get('current_pending_support')}")
        else:
            logger.warning(f"❌ Unexpected item in data at index {i}: {person}")

    context = {
        "senior_key_person_data": senior_key_data,
        "submission": submission,
        "org_id": org_id,
        "form_id": form_id,
        "user": request.user,
    }

    html_string = render_to_string("admin/senior_key_person_answers.html", context)

    # ✅ CSS for PDF
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
                    f'attachment; filename="Senior_Key_Persons_{submission.submission_name}.pdf"'
                )
                return response
    except Exception as e:
        logger.exception("❌ PDF generation failed")
        return HttpResponse(f"Error generating PDF: {e}", status=500)