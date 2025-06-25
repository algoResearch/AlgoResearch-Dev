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
logger = logging.getLogger(__name__)  # Set up a logger for error tracking
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


@login_required
def download_rr_other_info_pdf(request, org_id, form_id):
    submission = get_object_or_404(SubmittedPackage, id=form_id, org_id=org_id, is_draft=False)

    # ❌ Don't decode it if it's already a dict
    rr_data = submission.RR_Other_Info_data or {}
    rr_other_info_file_fields = {
        7: "project_summary_abstract",
        8: "project_narrative",
        9: "bibliography_references",
        10: "facilities_resources",
        11: "equipment_description",
    }

    # 📁 Populate RR_Other_Info_data with expected keys for template access
    for i, actual_key in rr_other_info_file_fields.items():
        rr_data[f"existing_attachment_{i}"] = rr_data.get(actual_key, "No file uploaded")
    html_string = render_to_string(
        "admin/RR_Other_Information_Answers.html",
        {
            "rr_data": rr_data,
            "RR_Other_Info_data": rr_data,
            "submission": submission,
            "org_id": org_id,
            "form_id": form_id,
            "rr_other_info_attachments": attachment_fields,  # make sure this exists
            "uei": rr_data.get("uei", ""),
            "organization_name": rr_data.get("organization_name", ""),
        },
    )

    pdf_css = CSS(string="""
        @page { size: Letter; margin: 0.5in; }
        body { font-family: 'Times New Roman', serif; font-size: 10pt; }
        table { width: 100%; border-collapse: collapse; }
        td, th { border: 1px solid black; padding: 4px; }
    """)

    with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as pdf_file:
        HTML(string=html_string).write_pdf(pdf_file.name, stylesheets=[pdf_css])
        with open(pdf_file.name, "rb") as pdf:
            response = HttpResponse(pdf.read(), content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="RR_Other_Information_{submission.submission_name}.pdf"'
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
        return redirect('package_summary', org_id=org_id, package_id=package_id)        

@login_required
def rr_budget_submit(request, org_id, package_id, project_id):
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
            # Extract fields from the POST data
            uei = request.POST.get(f"uei_{i}", "Not Provided")
            start_date = request.POST.get(f"start_date_{i}", "").strip()
            end_date = request.POST.get(f"end_date_{i}", "").strip()
            organization_name = request.POST.get(f"organization_name_{i}", "Not Provided")
            total_direct_costs = float(request.POST.get(f"total_direct_costs_{i}", 0) or 0)
            total_indirect_costs = float(request.POST.get(f"total_indirect_costs_{i}", 0) or 0)
            fee = float(request.POST.get(f"fee_{i}", "0") or 0)
            total_cost_with_fee = total_direct_costs + total_indirect_costs + fee


            # Senior Key Persons
            # Senior Key Persons
            senior_key_persons = []
            total_funds_senior_key_persons = 0
            first_names = request.POST.getlist(f"first_name_{i}[]")
            middle_names = request.POST.getlist(f"middle_name_{i}[]")
            last_names = request.POST.getlist(f"last_name_{i}[]")
            base_salaries = request.POST.getlist(f"base_salary_{i}[]")
            calendar_months = request.POST.getlist(f"calendar_months_{i}[]")
            requested_salaries = request.POST.getlist(f"requested_salary_{i}[]")
            fringe_benefits = request.POST.getlist(f"fringe_benefits_{i}[]")
            project_roles = request.POST.getlist(f"project_role_{i}[]")
            print(f"Period {i} - Retrieved Key Persons Data:")
            print(f"First Names: {first_names}")
            print(f"Middle Names: {middle_names}")
            print(f"Last Names: {last_names}")
            print(f"Base Salaries: {base_salaries}")
            print(f"Calendar Months: {calendar_months}")
            print(f"Requested Salaries: {requested_salaries}")
            print(f"Fringe Benefits: {fringe_benefits}")
            print(f"Project Roles: {project_roles}")
            for j in range(len(first_names)):
                if first_names[j].strip():
                    requested_salary = float(requested_salaries[j] or 0)
                    fringe_benefit = float(fringe_benefits[j] or 0)
                    base_salary = float(base_salaries[j] or 0)
                    calendar_month = float(calendar_months[j] or 0)
                    funds_requested = requested_salary + fringe_benefit
                    senior_key_persons.append({
                        "first_name": first_names[j],
                        "middle_name": middle_names[j] if j < len(middle_names) else "",
                        "last_name": last_names[j] if j < len(last_names) else "",
                        "base_salary": base_salary,
                        "calendar_months": calendar_month,
                        "requested_salary": requested_salary,
                        "fringe_benefits": fringe_benefit,
                        "funds_requested": funds_requested,
                        "project_role": project_roles[j] if j < len(project_roles) else "",
                    })
                    total_funds_senior_key_persons += funds_requested

            # Other Personnel
            other_personnel = []
            total_other_personnel = 0
            personnel_roles = ["postdoc", "grad", "undergrad", "secretarial"]

            for role in personnel_roles:
                num_personnel = int(request.POST.get(f"num_personnel_{role}_{i}", 0) or 0)
                calendar_months = float(request.POST.get(f"calendar_months_{role}_{i}", 0) or 0)
                academic_months = float(request.POST.get(f"academic_months_{role}_{i}", 0) or 0)
                summer_months = float(request.POST.get(f"summer_months_{role}_{i}", 0) or 0)
                requested_salary = float(request.POST.get(f"requested_salary_{role}_{i}", 0) or 0)
                fringe_benefits = float(request.POST.get(f"fringe_benefits_{role}_{i}", 0) or 0)
                funds_requested = requested_salary + fringe_benefits

                if num_personnel > 0:
                    other_personnel.append({
                        "role": role.capitalize(),
                        "num": num_personnel,
                        "calendar_months": calendar_months,
                        "academic_months": academic_months,
                        "summer_months": summer_months,
                        "requested_salary": requested_salary,
                        "fringe_benefits": fringe_benefits,
                        "funds_requested": funds_requested
                    })
                    total_other_personnel += funds_requested

            # Equipment
            equipment = []
            total_equipment_cost = 0
            equipment_items = request.POST.getlist(f"equipment_item_{i}[]")
            equipment_funds = request.POST.getlist(f"equipment_funds_requested_{i}[]")

            for j in range(len(equipment_items)):
                if equipment_items[j].strip():
                    funds_requested = float(equipment_funds[j] or 0)
                    equipment.append({"item": equipment_items[j], "funds_requested": funds_requested})
                    total_equipment_cost += funds_requested

            # Travel Costs
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
            total_other_direct_costs = 0
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


            # Calculate the total other direct costs
            total_other_direct_costs = sum(direct_costs.values())
            total_funds_requested_attachment = float(request.POST.get(f"total_funds_requested_attachment_{i}", "0") or 0)
            equipment_file_total = float(request.POST.get(f"equipment_file_total_{i}", "0") or 0)
            # Budget Period Data
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
                    funds = float(indirect_funds_requested[j] or 0)
                    indirect_costs.append({
                        "type": indirect_cost_types[j],
                        "rate": rate,
                        "base": base,
                        "funds_requested": funds
                    })
                    total_indirect_costs += funds

            # Add to period data
            
            
            period_data = {
                "period_number": i,
                "uei": uei,
                "organization_name": organization_name,
                "start_date": start_date,
                "end_date": end_date,
                "senior_key_persons": senior_key_persons,
                "total_funds_senior_key_persons": total_funds_senior_key_persons,
                "other_personnel": other_personnel,
                "total_other_personnel": total_other_personnel,
                "equipment": equipment,
                "equipment_file_total": equipment_file_total,  
                "total_equipment_cost": total_equipment_cost,
                "total_travel_cost": total_travel,
                "total_domestic_travel": domestic_travel,
                "total_foreign_travel": foreign_travel,
                "trainee_costs": trainee_costs,  # ✅ Now properly included
                "total_participant_support_costs": trainee_costs["total_support_costs"],
                "direct_costs": direct_costs,
                "total_other_direct_costs": total_other_direct_costs,

                "total_direct_costs": total_direct_costs,
                "indirect_costs": indirect_costs,
                "total_indirect_costs": total_indirect_costs,
                "total_direct_indirect_costs": total_direct_costs + total_indirect_costs,
                "fee": fee,
                "total_cost_with_fee": total_cost_with_fee,
                "total_funds_requested_attachment": total_funds_requested_attachment
            }
            period_data["indirect_costs"] = indirect_costs
            period_data["total_indirect_costs"] = total_indirect_costs

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
                
                project_id = request.POST.get("project_id") or request.GET.get("project_id") or request.session.get("project_id")
                if not project_id:
                    messages.error(request, "Project ID is missing.")
                    return redirect("specific_project_home", org_id=org_id)
                print(f"✅ Received Project ID: {project_id}")
                project = Project.objects.filter(id=project_id).first()
                opportunity = Opportunity.objects.filter(form_package_id=package_id, project=project).first()

                # Ensure the draft is uniquely linked to both project and package
                draft, created = SubmittedPackage.objects.get_or_create(
                    org_id=org_id,
                    package_id=package_id,
                    project=project,  # Use the correct project object
                    opportunity=opportunity,
                    is_draft=True,
                    defaults={
                        "submission_name": f"Draft - {project.name if project else 'Unknown'}",
                        "submission_date": timezone.now(),
                        "budget_periods": budget_periods,
                        "cumulative_totals": cumulative_totals,
                    }
                )

                # Update existing draft if it already exists
                if not created:
                    draft.submission_name = f"Draft - {project.name if project else 'Unknown'}"
                    draft.submission_date = timezone.now()
                    
                    existing_sf424_data = draft.sf424_data if draft else {}
                    save_full_draft(
                        project=project,
                        org_id=org_id,
                        package_id=package_id,
                        user=request.user,
                        sf424_data=existing_sf424_data,
                        rr_budget_data={},  # you could also create and pass `rr_budget_data` dict if needed
                        budget_periods=budget_periods,
                        cumulative_totals=cumulative_totals
                    )
                    draft.is_draft = True
                    draft.last_edited_by = request.user
                    draft.save()
                messages.success(request, "Draft saved successfully.")
                print("✅ Draft saved successfully.")
                return redirect("specific_project_home", org_id=org_id, project_id=project.id)

            except Exception as e:
                messages.error(request, f"Error saving draft: {str(e)}")
                print(f"❌ Error saving draft: {str(e)}")
                return redirect("specific_project_home", org_id=org_id, project_id=package_id)

        request.session[f"budget_periods_{org_id}_{package_id}"] = budget_periods
        request.session[f"cumulative_totals_{org_id}_{package_id}"] = cumulative_totals
        request.session.modified = True

        package = get_object_or_404(FormPackage, id=package_id, organization_id=org_id)
        try:
            included_templates = get_included_form_templates(package)

            if "admin/RR_Budget.html" in included_templates and "admin/fill_out_sf424.html" in included_templates:
                summary_url = reverse("package_summary", kwargs={"org_id": org_id, "package_id": package_id})
                print(f"✅ Redirecting to Combined Summary: {summary_url}")
                return HttpResponseRedirect(summary_url)

            elif "admin/RR_Budget.html" in included_templates:
                summary_url = reverse("rr_budget_summary", kwargs={"org_id": org_id, "package_id": package_id})
                print(f"✅ Redirecting to RR Budget Summary: {summary_url}")
                return HttpResponseRedirect(summary_url)

            elif "admin/fill_out_sf424.html" in included_templates:
                summary_url = reverse("sf424_summary", kwargs={"org_id": org_id, "package_id": package_id})
                print(f"✅ Redirecting to SF-424 Summary: {summary_url}")
                return HttpResponseRedirect(summary_url)

            else:
                print("❗ No recognized templates found. Defaulting to generic package summary.")
                return redirect("package_summary", org_id=org_id, package_id=package_id)

        except Exception as e:
            print(f"❌ Error in redirecting: {e}")
            messages.error(request, "Error: Could not redirect to the summary page.")
            return redirect("package_display", org_id=org_id, package_id=package_id)

@login_required
def download_rr_budget_pdf(request, org_id, form_id):
    """Generate and serve the filled RR Budget form as a downloadable PDF."""
    submission = get_object_or_404(
        SubmittedPackage, id=form_id, org_id=org_id, is_draft=False
    )

    # ✅ Load data safely
    try:
        budget_periods = submission.budget_periods or []
        cumulative_totals = submission.cumulative_totals or {}
    except Exception as e:
        logger.warning("⚠️ Error loading budget data: %s", e)
        budget_periods = []
        cumulative_totals = {}

    context = {
        "budget_periods": budget_periods,
        "cumulative_totals": cumulative_totals,
        "submission": submission,
        "org_id": org_id,
        "form_id": form_id,
        "is_cumulative_summary": True,
    }

    html_string = render_to_string("admin/RR_Budget_Answers.html", context)

    pdf_css = CSS(string="""
        @page { size: Letter; margin: 0.5in; }
        body { font-family: 'Times New Roman', serif; font-size: 10pt; margin: 0; }
        table { width: 100%; border-collapse: collapse; font-size: 9pt; }
        td, th { border: 1px solid black; padding: 4px; word-wrap: break-word; }
        input { border: none; background: transparent; width: 100%; font-size: 9pt; }
        .TableHeader { font-weight: bold; background-color: #f0f0f0; }
        .page-break { page-break-before: always; }
    """)

    try:
        with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as pdf_file:
            HTML(string=html_string).write_pdf(pdf_file.name, stylesheets=[pdf_css])
            with open(pdf_file.name, "rb") as pdf:
                response = HttpResponse(pdf.read(), content_type="application/pdf")
                response["Content-Disposition"] = (
                    f'attachment; filename="RR_Budget_{submission.submission_name}.pdf"'
                )
                return response
    except Exception as e:
        logger.exception("❌ PDF generation failed for RR Budget")
        return HttpResponse(f"Error generating PDF: {e}", status=500)

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