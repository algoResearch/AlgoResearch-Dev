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

def is_admin_or_principal(user):
    return user.role in ['admin', 'principal_admin']

def is_principal_admin(user):
    return user.role == 'principal_admin'

def fill_out_sf424(request):
    if request.method == 'POST':
        form = SF424Form(request.POST)
        if form.is_valid():
            # Retrieve user input
            position_title = form.cleaned_data['position_title'].replace(' ', '&#160;')
            authorized_rep_title = form.cleaned_data['authorized_representative_title'].replace(' ', '&#160;')
            
            # Load the XML template
            xml_file = '/Users/ryancarmody/algoresearch/dashboard/templates/admin/SF4X.xml'
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
        # Handle file uploads with an existing file check
        draft = SubmittedPackage.objects.filter(
            org_id=org_id,
            package_id=package_id,
            project=project,
            is_draft=True
        ).first()
        existing_sf424_data = json.loads(draft.sf424_data) if draft and draft.sf424_data else {}
        existing_sflll_attachment = existing_sf424_data.get("sflll_attachment", "No file uploaded")
        existing_pre_application_attachment = existing_sf424_data.get("pre_application_attachment", "No file uploaded")
        existing_cover_letter_attachment = existing_sf424_data.get("cover_letter_attachment", "No file uploaded")
        def get_uploaded_file(request, file_field, existing_file):
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
            return existing_file  # Return the existing file if no new file is uploaded
       
        sf424_data = {
            "submission_types": request.POST.getlist("submission_types"),
            "application_types": request.POST.getlist("application_types"),
            "agency_routing_identifier": request.POST.get("agency_routing_identifier", "Not Provided"),
            "previous_grants_gov_tracking_id": request.POST.get("previousGrantsGovTrackingID", "Not Provided"),
            "revision_type": request.POST.getlist("revision_type"),
            "otherRevisionText": request.POST.get("otherRevisionText", "Not Provided"),
            "submittedToOtherAgencies": request.POST.get("submittedToOtherAgencies", "Not Provided"),
            "otherAgencies": request.POST.get("otherAgencies", "Not Provided"),
            "date_submitted": request.POST.get("date_submitted", "Not Provided"),
            "applicant_identifier": request.POST.get("applicant_identifier", "Not Provided"),
            "date_received_by_state": request.POST.get("date_received_by_state", "Not Provided"),
            "state_application_identifier": request.POST.get("state_application_identifier", "Not Provided"),
            "federal_identifier": request.POST.get("federal_identifier", "Not Provided"),
            "agency_routing_number": request.POST.get("agency_routing_number", "Not Provided"),
            "previous_tracking_id": request.POST.get("previous_tracking_id", "Not Provided"),
            "uei": request.POST.get("uei", "Not Provided"),
            "legal_name": request.POST.get("legal_name", "Not Provided"),
            "department": request.POST.get("department", "Not Provided"),
            "division": request.POST.get("division", "Not Provided"),
            "address_street1": request.POST.get("address_street1", "Not Provided"),
            "address_street2": request.POST.get("address_street2", "Not Provided"),
            "city": request.POST.get("city", "Not Provided"),
            "county": request.POST.get("county", "Not Provided"),
            "province": request.POST.get("province", "Not Provided"),
            "zip_code": request.POST.get("zipPostal", "Not Provided"),
            "country": request.POST.get("country", "Not Provided"),
            "state": request.POST.get("state", "Not Provided"),
            "prefix": request.POST.get("prefix", "Not Provided"),
            "first_name": request.POST.get("first_name", "Not Provided"),
            "middle_name": request.POST.get("middle_name", "Not Provided"),
            "last_name": request.POST.get("last_name", "Not Provided"),
            "suffix": request.POST.get("suffix", "Not Provided"),
            "contact_street1": request.POST.get("contact_street1", "Not Provided"),
            "contact_street2": request.POST.get("contactStreet2", "Not Provided"),
            "contact_zip": request.POST.get("contactZipPostal", "Not Provided"),
            "contact_state": request.POST.get("contactState", "Not Provided"),
            "contact_province": request.POST.get("contactProvince", "Not Provided"),
            "contact_country": request.POST.get("contactCountry", "Not Provided"),
            "contact_city": request.POST.get("contactCity", "Not Provided"),
            "contact_county": request.POST.get("contactCounty", "Not Provided"),
            "contact_fax": request.POST.get("contactFax", "Not Provided"),
            "contact_phone": request.POST.get("contact_phone", "Not Provided"),
            "contact_email": request.POST.get("contact_email", "Not Provided"),
            "ein_tin": request.POST.get("ein_tin", "Not Provided"),
            "federal_agency": request.POST.get("federal_agency", "Not Provided"),
            "assistance_listing_number": request.POST.get("assistance_listing_number", "Not Provided"),
            "assistance_listing_title": request.POST.get("assistance_listing_title", "Not Provided"),
            "project_title": request.POST.get("project_title", "Not Provided"),
            "congressional_district": request.POST.get("congressional_district", "Not Provided"),
            "start_date": request.POST.get("startDate", "Not Provided"),
            "end_date": request.POST.get("endDate", "Not Provided"),
            "total_federal_funds": request.POST.get("total_federal_funds", "0.00"),
            "total_non_federal_funds": request.POST.get("total_non_federal_funds", "0.00"),
            "total_combined_funds": request.POST.get("total_combined_funds", "0,00"),
            "estimated_income": request.POST.get("estimated_income", "0.00"),
            "eo_review_check": request.POST.get("eo_review_check", "No"),
            "eo_review_date": request.POST.get("eo_review_date", "Not Provided") if request.POST.get("eo_review_check") else "Not Applicable",
            "eo_not_covered": request.POST.get("eo_not_covered", "No"),
            "eo_not_selected": request.POST.get("eo_not_selected", "No"),
            "pi_prefix": request.POST.get("pi_prefix", "Not Provided"),
            "pi_first_name": request.POST.get("pi_first_name", "Not Provided"),
            "position_title": request.POST.get("positionTitle", "Not Provided"),
            "pi_middle_name": request.POST.get("pi_middle_name", "Not Provided"),
            "pi_last_name": request.POST.get("pi_last_name", "Not Provided"),
            "pi_suffix": request.POST.get("piSuffix", "Not Provided"),
            "pi_position": request.POST.get("pi_position", "Not Provided"),
            "pi_organization": request.POST.get("pi_organization", "Not Provided"),
            "pi_department": request.POST.get("pi_department", "Not Provided"),
            "pi_division": request.POST.get("pi_division", "Not Provided"),
            "pi_street1": request.POST.get("pi_street1", "Not Provided"),
            "pi_street2": request.POST.get("pi_street2", "Not Provided"),
            "pi_city": request.POST.get("pi_city", "Not Provided"),
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
            "eo_review_check": "Yes" if request.POST.get("eo_review_check") == "Yes" else "No",
            "eo_review_date": request.POST.get("eo_review_date", "Not Provided") if request.POST.get("eo_review_check") == "Yes" else "Not Applicable",
            "eo_not_covered": "Yes" if request.POST.get("eo_not_covered") == "Yes" else "No",
            "eo_not_selected": "Yes" if request.POST.get("eo_not_selected") == "Yes" else "No",
            # ✅ New: Store Uploaded File Name
            "certification_agree": "Yes" if request.POST.get("certification_agree") == "Yes" else "No",
            "attachment_agree": "Yes" if request.POST.get("attachment_agree") == "Yes" else "No",
            "sflll_attachment": get_uploaded_file(request, "sflllAttachment", existing_sflll_attachment),
            "pre_application_attachment": get_uploaded_file(request, "preApplicationAttachment", existing_pre_application_attachment),
            "cover_letter_attachment": get_uploaded_file(request, "coverLetterAttachment", existing_cover_letter_attachment),
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
            "type_of_applicant": request.POST.get("typeOfApplicant", "Not Provided"),
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
        print(f"SF-424 Data to be saved: {json.dumps(sf424_data, indent=4)}")

        if "save_draft" in request.POST:
            if not user_can_edit_project(request.user, project):
                messages.error(request, "You do not have permission to edit this project.")
                return redirect("package_display", org_id=org_id, package_id=package_id, project_id=project_id)
            try:
                
                draft, created = SubmittedPackage.objects.get_or_create(
                    org_id=org_id,
                    package_id=package_id,
                    project=project,
                    is_draft=True,
                    defaults={
                        "submission_name": f"Draft - {project.name if project else 'Unknown'}",
                        "submission_date": timezone.now(),
                        "sf424_data": sf424_data,
                        "last_edited_by": request.user,  # Track last person to edit
                    }
                )

                if not created:
                    draft.submission_name = f"Draft - {project.name if project else 'Unknown'}"
                    draft.submission_date = timezone.now()
                    existing_rr_budget_data = draft.rr_budget_data if draft else {}
                    existing_budget_periods = draft.budget_periods if draft else []
                    existing_cumulative_totals = draft.cumulative_totals if draft else {}
                    save_full_draft(
                        project=project,
                        org_id=org_id,
                        package_id=package_id,
                        user=request.user,
                        sf424_data=sf424_data,
                        rr_budget_data=existing_rr_budget_data,
                        budget_periods=existing_budget_periods,
                        cumulative_totals=existing_cumulative_totals
                    )
                    draft.last_edited_by = request.user
                    

                # ✅ Define attachment function OUTSIDE if-block
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

                    filename = os.path.basename(full_path)
                    new_relative_path = f"project_attachments/{filename}"

                    if ProjectAttachment.objects.filter(project=project, file=new_relative_path).exists():
                        print(f"⚠️ ProjectAttachment already exists: {new_relative_path}")
                        return

                    with open(full_path, 'rb') as f:
                        django_file = File(f)
                        attachment = ProjectAttachment(
                            project=project,
                            uploaded_by=user,
                        )
                        attachment.file.save(filename, django_file, save=True)
                        print(f"📎 ProjectAttachment created for {filename}")
                # ✅ Place safe_upload right below here:
                def safe_upload(storage_path, uploaded_file):
                    if default_storage.exists(storage_path):
                        print(f"⚠️ Skipping upload, file already exists: {storage_path}")
                        return default_storage.url(storage_path)
                    return default_storage.url(default_storage.save(storage_path, uploaded_file))
                    # ✅ Create ProjectAttachments for SF-424 files
                create_project_attachment(sf424_data["sflll_attachment"], request.user, project)
                create_project_attachment(sf424_data["pre_application_attachment"], request.user, project)
                create_project_attachment(sf424_data["cover_letter_attachment"], request.user, project)
                
                print(f"✅ Draft saved successfully for user {request.user.username}, package ID {package_id}, project ID {project_id}")
                messages.success(request, "SF-424 draft saved successfully.")
                return redirect("specific_project_home", org_id=org_id, project_id=project_id)

            except Exception as e:
                print(f"❌ Error saving SF-424 draft: {str(e)}")
                messages.error(request, f"Error saving SF-424 draft: {str(e)}")    
                return redirect("package_display", org_id=org_id, package_id=package_id, project_id=project_id)
        session_key = f"sf424_data_{org_id}_{package_id}"
        request.session[session_key] = sf424_data
        request.session.modified = True
        request.session[f"budget_periods_{org_id}_{package_id}"] = draft.budget_periods
        request.session[f"cumulative_totals_{org_id}_{package_id}"] = draft.cumulative_totals


        print(f"✅ Redirecting to summary for project ID {project_id}")
        return redirect("package_summary", org_id=org_id, package_id=package_id)

    print("❗ Invalid request method")
    return redirect("package_display", org_id=org_id, package_id=package_id)
@login_required
def download_filled_sf424_pdf(request, org_id, form_id, project_id):
    """Generate and serve the filled SF-424 form as a downloadable PDF"""
    import json

    # ✅ Fetch the most recent submission for this package
    submission = SubmittedPackage.objects.filter(
        org_id=org_id,
        package_id=form_id,
        project_id=project_id,
        is_draft=False  # Only allow downloading finalized versions
    ).order_by('-submission_date').first()

    if not submission:
        messages.error(request, "No SF-424 data available for this submission.")
        return redirect("view_submission", org_id=org_id, submission_id=form_id)

    # ✅ Fetch SF-424 data from the stored submission
    sf424_data = submission.sf424_data if submission and submission.sf424_data else {}

    # ✅ Convert JSON string to dictionary if necessary
    if isinstance(sf424_data, str):
        sf424_data = json.loads(sf424_data)
    sf424_data["sflll_attachment"] = (
        request.FILES["sflllAttachment"] if "sflllAttachment" in request.FILES
        else request.POST.get("existing_sflll_attachment", sf424_data.get("sflll_attachment", "No file uploaded"))
    )


   
    sf424_data["pre_application_attachment"] = (
        request.FILES["pre_application_attachment"] if "pre_application_attachment" in request.FILES
        else request.POST.get("existing_pre_application_attachment", "No file uploaded")
    )
    sf424_data["cover_letter_attachment"] = (
        request.FILES["coverLetterAttachment"] if "coverLetterAttachment" in request.FILES
        else request.POST.get("existing_cover_letter_attachment", sf424_data.get("cover_letter_attachment", "No file uploaded"))
    )

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