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
from datetime import datetime, timedelta, time, date
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


@login_required
def fund_dashboard(request, org_id):
    user = request.user
    fund_projects = []

    if user.position_type == "fund_manager":
        fund_projects = Project.objects.filter(
            status="Funded",
            org_id=org_id,
            users=user
        ).select_related("fund", "principal_investigator") \
         .prefetch_related("budget_period_entries") \
         .distinct().order_by("-updated_at")

    user_cost_centers = []
    
    if user.position_type == "fund_manager":
        funds = Fund.objects.filter(id__in=fund_projects.values_list("fund_id", flat=True)) \
                            .prefetch_related('user_assignments', 'projects__budget_period_entries', 'projects__principal_investigator')
        fund_to_pi = {}
        today = date.today()
        for fund in funds:
            project = None
            for p in fund.projects.all():
                periods = p.budget_period_entries.all().order_by('start_date')
                for period in periods:
                    if period.start_date <= today <= period.end_date:
                        project = p
                        break
                if project:
                    break
            if not project:
                project = fund.projects.first()

            if project and project.principal_investigator:
                fund_to_pi[fund.id] = project.principal_investigator
       
        suffix_map = {
            'direct_personnel': 'DP',
            'direct_non_personnel': 'DNP',
            'indirect_personnel': 'IP',
            'indirect_non_personnel': 'INP',
        }

        today = date.today()

        for fund in funds:
            # --- Aggregate financials ---
            direct_cost_types = fund.cost_types.filter(cost_center_type='direct', is_idc=False).prefetch_related('entries')
            indirect_cost_types = fund.cost_types.filter(cost_center_type='indirect', is_idc=False).prefetch_related('entries')

            aggregated_totals = {
                'direct_personnel': defaultdict(Decimal),
                'direct_non_personnel': defaultdict(Decimal),
                'indirect_personnel': defaultdict(Decimal),
                'indirect_non_personnel': defaultdict(Decimal),
            }

            for ct in direct_cost_types:
                ct_totals = ct.calculate_totals()
                if ct.category == "personnel":
                    for field in ["budget", "encumbrance", "projected", "expense", "balance"]:
                        aggregated_totals['direct_personnel'][field] += Decimal(ct_totals.get(field, Decimal("0.0")))
                elif ct.category == "non_personnel":
                    for field in ["budget", "encumbrance", "projected", "expense", "balance"]:
                        aggregated_totals['direct_non_personnel'][field] += Decimal(ct_totals.get(field, Decimal("0.0")))

            for ct in indirect_cost_types:
                ct_totals = ct.calculate_totals()
                if ct.category == "personnel":
                    for field in ["budget", "encumbrance", "projected", "expense", "balance"]:
                        aggregated_totals['indirect_personnel'][field] += Decimal(ct_totals.get(field, Decimal("0.0")))
                elif ct.category == "non_personnel":
                    for field in ["budget", "encumbrance", "projected", "expense", "balance"]:
                        aggregated_totals['indirect_non_personnel'][field] += Decimal(ct_totals.get(field, Decimal("0.0")))

            # --- Find correct PI ---
            project = None
            for p in fund.projects.all():
                periods = p.budget_period_entries.all().order_by('start_date')
                for period in periods:
                    if period.start_date <= today <= period.end_date:
                        project = p
                        break
                if project:
                    break

            if not project:
                project = fund.projects.first()

            pi_user = None
            if project and project.principal_investigator:
                pi_user = project.principal_investigator

            # --- Build cost centers ---
            for key, suffix in suffix_map.items():
                totals = aggregated_totals.get(key, defaultdict(Decimal))
                user_cost_centers.append({
                    "fund_id": fund.fund_id,
                    "cost_center_name": f"{fund.fund_id} {key.replace('_', ' ').title()}",
                    "cost_center_id": f"CC-{fund.fund_id}-{suffix}",
                    "cost_center_key": key,   # ✅ Add this line
                    "pi_first_name": pi_user.first_name if pi_user else None,
                    "pi_last_name": pi_user.last_name if pi_user else None,
                    "pi_unique_id": pi_user.unique_id if pi_user else None,

                    "budget": totals.get("budget", Decimal("0.00")),
                    "encumbrance": totals.get("encumbrance", Decimal("0.00")),
                    "projected": totals.get("projected", Decimal("0.00")),
                    "expense": totals.get("expense", Decimal("0.00")),
                    "balance": totals.get("balance", Decimal("0.00")),
                })

    # --- Fund project financials display ---
    references = CostEntry.objects.filter(
        is_reference=True,
        fund__in=funds
    ).select_related("fund", "cost_type")
    transactions = CostEntry.objects.filter(
        is_reference=False,
        fund__in=funds
    ).select_related("fund", "organization")
    for ref in references:
            ref.principal_investigator = fund_to_pi.get(ref.fund_id)
    for tx in transactions:
        tx.principal_investigator = fund_to_pi.get(tx.fund_id)
    today = date.today()
    for project in fund_projects:
        periods = list(project.budget_period_entries.all().order_by("start_date"))
        current_period = None
        total_period_budget = sum([p.budget_amount for p in periods]) if periods else Decimal("0.00")
        current_budget = Decimal("0.00")

        for i, period in enumerate(periods, start=1):
            if period.start_date <= today <= period.end_date:
                current_period = {
                    "number": i,
                    "start": period.start_date,
                    "end": period.end_date,
                }
                current_budget = period.budget_amount
                break

        if not current_period and periods:
            period = periods[0]
            current_period = {
                "number": 1,
                "start": period.start_date,
                "end": period.end_date,
            }
            current_budget = period.budget_amount

        financials = getattr(project, "financials", None)
        org = getattr(project, 'fund', None).organization if getattr(project, 'fund', None) else None
        idc_rate = (Decimal(org.idc_rate or 0) / Decimal("100.00")) if org else Decimal("0.00")
        budget_fa = (current_budget * idc_rate).quantize(Decimal("0.01"))
        budget_total = current_budget + budget_fa
        project.financials_display = {
            "budget_direct_cost": current_budget,
            "budget_fa": budget_fa,
            "budget_total": budget_total,

            "expenses_direct_cost": financials.expenses_direct_cost if financials else Decimal("0.00"),
            "expenses_fa": financials.expenses_fa if financials else Decimal("0.00"),
            "expenses_total": financials.expenses_total if financials else Decimal("0.00"),

            "balance_direct_cost": financials.balance_direct_cost if financials else Decimal("0.00"),
            "balance_fa": financials.balance_fa if financials else Decimal("0.00"),
            "balance_total": financials.balance_total if financials else Decimal("0.00"),

            "encumbrance_direct_cost": financials.encumbrance_direct_cost if financials else Decimal("0.00"),
            "encumbrance_fa": financials.encumbrance_fa if financials else Decimal("0.00"),
            "encumbrance_total": financials.encumbrance_total if financials else Decimal("0.00"),

            "projected_direct_cost": financials.projected_direct_cost if financials else Decimal("0.00"),
            "projected_fa": financials.projected_fa if financials else Decimal("0.00"),
            "projected_total": financials.projected_total if financials else Decimal("0.00"),

            "projected_balance_direct_cost": financials.projected_balance_direct_cost if financials else Decimal("0.00"),
            "projected_balance_fa": financials.projected_balance_fa if financials else Decimal("0.00"),
            "projected_balance_total": financials.projected_balance_total if financials else Decimal("0.00"),
        }
    context = {
        'user': user,
        'org_id': org_id,
        'fund_projects': fund_projects,
        'user_cost_centers': user_cost_centers,
        
        'funds': Fund.objects.filter(id__in=fund_projects.values_list("fund_id", flat=True)),
        'total_users': User.objects.count(),
        'references': references,  # ✅ new
        'transactions': transactions,
        'upcoming_events': 0,
        'pending_tasks': 0,
    }

    return render(request, "admin/admin_dashboard.html", context)


# Only allow fund managers
def is_fund_manager(user):
    return user.is_authenticated and user.position_type == 'fund_manager'
@login_required
@user_passes_test(is_fund_manager)
def fund_home(request, org_id):
    return render(request, "funds/fund_home.html", {"org_id": org_id})


SUBCATEGORIES_BY_CATEGORY = {
    "personnel": [
        "Standing Faculty",
        "Professional Staff",
        "Employee Benefits"
    ],
    "non_personnel": [
        "Travel and Entertainment",
        "Supplies and Minor Expenses",
        "Professional and Other Services"
    ]
}


@require_POST
@login_required
def toggle_dark_mode(request):
    try:
        # Prefer JSON if provided
        if request.META.get("CONTENT_TYPE", "").startswith("application/json"):
            raw = request.body.decode("utf-8") if request.body else "{}"
            data = json.loads(raw)
            value = bool(data.get("dark_mode", False))
        else:
            # Fallback to form-encoded
            v = (request.POST.get("dark_mode") or "").lower()
            value = v in ("1", "true", "on", "yes")

        request.user.dark_mode = value
        request.user.save(update_fields=["dark_mode"])
        return JsonResponse({"status": "ok", "dark_mode": request.user.dark_mode})
    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)
    
@login_required
def fund_detail(request, fund_id):
    fund = get_object_or_404(Fund, fund_id=fund_id)
    projects = fund.projects.all()
    project = projects.first()
    current_period = None
    current_period_budget = Decimal("0.00")
    major_personnel = Decimal("0.00")
    major_non_personnel = Decimal("0.00")
    subcategory_budgets = defaultdict(lambda: Decimal("0.00"))

    if project:
        today = date.today()
        periods = project.budget_period_entries.all().order_by("start_date")
        for i, period in enumerate(periods, start=1):
            if period.start_date <= today <= period.end_date:
                current_period = {
                    "number": i,
                    "start": period.start_date,
                    "end": period.end_date,
                }
                break

        if current_period:
            budget_period = project.budget_period_entries.filter(start_date=current_period["start"]).first()
            if budget_period:
                current_period_budget = budget_period.budget_amount
                custom_allocations = BudgetAllocation.objects.filter(
                    fund=fund,
                    period_start=budget_period.start_date
                )
                for alloc in custom_allocations:
                    normalized = alloc.subcategory.strip().lower().replace("-", " ").replace("_", " ")
                    if normalized == "personnel":
                        major_personnel = alloc.budget_amount
                    elif normalized == "non personnel":
                        major_non_personnel = alloc.budget_amount
                    else:
                        subcategory_budgets[alloc.subcategory] = alloc.budget_amount

    if major_personnel == 0 and major_non_personnel == 0:
        major_personnel = current_period_budget * Decimal("0.5")
        major_non_personnel = current_period_budget * Decimal("0.5")

    direct_cost_types = fund.cost_types.filter(cost_center_type='direct', is_idc=False).prefetch_related('entries')
    indirect_cost_types = fund.cost_types.filter(cost_center_type='indirect', is_idc=False).prefetch_related('entries')

    cost_types_grouped = {
        'direct_personnel': [],
        'direct_non_personnel': [],
        'indirect_personnel': [],
        'indirect_non_personnel': [],
    }

    aggregated_totals = {
        'direct_personnel': defaultdict(Decimal),
        'direct_non_personnel': defaultdict(Decimal),
        'indirect_personnel': defaultdict(Decimal),
        'indirect_non_personnel': defaultdict(Decimal),
    }

    # ✅ Aggregate Directs
    for ct in direct_cost_types:
        ct.totals = ct.calculate_totals()
        if ct.category == "personnel":
            cost_types_grouped['direct_personnel'].append(ct)
            for field in ["budget", "encumbrance", "projected", "expense", "balance"]:
                aggregated_totals['direct_personnel'][field] += Decimal(ct.totals.get(field, Decimal("0.0")))
        elif ct.category == "non_personnel":
            cost_types_grouped['direct_non_personnel'].append(ct)
            for field in ["budget", "encumbrance", "projected", "expense", "balance"]:
                aggregated_totals['direct_non_personnel'][field] += Decimal(ct.totals.get(field, Decimal("0.0")))

    # ✅ Aggregate Indirects
    for ct in indirect_cost_types:
        ct.totals = ct.calculate_totals()
        if ct.category == "personnel":
            cost_types_grouped['indirect_personnel'].append(ct)
            for field in ["budget", "encumbrance", "projected", "expense", "balance"]:
                aggregated_totals['indirect_personnel'][field] += Decimal(ct.totals.get(field, Decimal("0.0")))
        elif ct.category == "non_personnel":
            cost_types_grouped['indirect_non_personnel'].append(ct)
            for field in ["budget", "encumbrance", "projected", "expense", "balance"]:
                aggregated_totals['indirect_non_personnel'][field] += Decimal(ct.totals.get(field, Decimal("0.0")))

    # ✅ Now Generate Cost Center Info AFTER Aggregation
    cost_center_info = {}
    suffix_map = {
        'direct_personnel': 'DP',
        'direct_non_personnel': 'DNP',
        'indirect_personnel': 'IP',
        'indirect_non_personnel': 'INP',
    }

    for key, suffix in suffix_map.items():
        cost_center_id = f"CC-{fund.fund_id.split('-')[1]}-{suffix}"
        cost_center_name = f"{fund.fund_id} {key.replace('_', ' ').title()}"
        total_budget = aggregated_totals[key]['budget']
        cost_center_info[key] = {
            "id": cost_center_id,
            "name": cost_center_name,
            "total_budget": total_budget,
        }
    cost_categories = {
        "Direct Costs": [
            ("direct_personnel", "Direct Personnel"),
            ("direct_non_personnel", "Direct Non-Personnel"),
        ],
        "Indirect Costs": [
            ("indirect_personnel", "Indirect Personnel"),
            ("indirect_non_personnel", "Indirect Non-Personnel"),
        ]
    }

    user_total_salaries = {}
    for assignment in fund.user_assignments.select_related('user'):
        user = assignment.user
        total_salary = user.fund_assignments.aggregate(total=Sum('salary_amount'))['total'] or 0
        user_total_salaries[user.id] = total_salary

    context = {
        "fund": fund,
        "projects": projects,
        "current_budget_period": current_period,
        "current_budget_amount": current_period_budget,
        "user_total_salaries": user_total_salaries,
        "aggregated_totals": aggregated_totals,
        "cost_types_grouped": cost_types_grouped,
        "personnel_budget": major_personnel,
        "non_personnel_budget": major_non_personnel,
        "subcategory_budgets": subcategory_budgets,
        "cost_categories": cost_categories,
        "grouped_subcategories": SUBCATEGORIES_BY_CATEGORY,
        "cost_center_info": cost_center_info,  # ✅ Final position
    }

    return render(request, "admin/fund_detail.html", context)

@login_required
def subcategory_transactions(request, fund_id, subcategory_name):
    fund = get_object_or_404(Fund, fund_id=fund_id)
    cost_type = fund.cost_types.filter(name=subcategory_name).first()

    if not cost_type:
        return HttpResponseNotFound("Subcategory not found.")

    entries = cost_type.entries.filter(is_reference=False)

    ref_filter = request.GET.get("ref")
    if ref_filter:
        entries = entries.filter(ref_num1=ref_filter)

    context = {
        "fund": fund,
        "subcategory_name": subcategory_name,
        "entries": entries,
    }
    return render(request, "admin/subcategory_transactions.html", context)

@login_required
def reference_summary(request, fund_id, subcategory_name):
    fund = get_object_or_404(Fund, fund_id=fund_id)
    cost_type = get_object_or_404(CostType, fund=fund, name=subcategory_name)

    # Group entries by ref_num1
    references = defaultdict(list)
    for entry in cost_type.entries.all():
        references[entry.ref_num1].append(entry)

    # Precalculate totals
    reference_data = []
    for ref_num1, entries in references.items():
        total_budget = sum(e.budget for e in entries)
        total_adjustment = sum(e.projected for e in entries)  # Or however you define adjustment
        total_expenses = sum(e.expense for e in entries)
        ref_entry = entries[0]  # Use first entry for static fields like vendor, code, description
        reference_data.append({
            'ref_num1': ref_num1,
            'ref_num2': ref_entry.ref_num2,
            'vendor': ref_entry.vendor,
            'code': ref_entry.code,
            'description': ref_entry.description,
            'budget': total_budget,
            'adjustment': total_adjustment,
            'expenses': total_expenses,
        })

    context = {
        'fund': fund,
        'subcategory_name': subcategory_name,
        'reference_data': reference_data,
    }
    return render(request, "admin/reference_summary.html", context)

@require_POST
@login_required
def update_budget_allocation(request, fund_id):
    fund = get_object_or_404(Fund, fund_id=fund_id)
    project = fund.projects.first()

    if project:
        today = date.today()
        period = project.budget_period_entries.filter(start_date__lte=today, end_date__gte=today).first()
        if not period:
            # fallback to first period
            period = project.budget_period_entries.order_by("start_date").first()

        if period:
            # Clear previous
            BudgetAllocation.objects.filter(fund=fund, period_start=period.start_date).delete()

            # Major splits
            try:
                personnel_amt = Decimal(request.POST.get("personnel", "0").replace(",", "").strip())
            except InvalidOperation:
                personnel_amt = Decimal("0.00")

            try:
                non_personnel_amt = Decimal(request.POST.get("non_personnel", "0").replace(",", "").strip())
            except InvalidOperation:
                non_personnel_amt = Decimal("0.00")
            # Save major splits (if needed)
            for key, amount in [("Personnel", personnel_amt), ("Non-Personnel", non_personnel_amt)]:
                BudgetAllocation.objects.create(
                    fund=fund,
                    period_start=period.start_date,
                    subcategory=key,
                    budget_amount=amount
                )

            # Save subcategories
            for field in request.POST:
                if field.startswith("subcategory_"):
                    subcategory = field.replace("subcategory_", "").replace("_", " ")
                    raw_val = request.POST.get(field, "0").replace(",", "").strip()
                    try:
                        value = Decimal(raw_val)
                    except InvalidOperation:
                        value = Decimal("0.00")
                    BudgetAllocation.objects.create(
                        fund=fund,
                        period_start=period.start_date,
                        subcategory=subcategory,
                        budget_amount=value
                    )

    return redirect("fund_detail", fund_id=fund_id)

@login_required
def add_cost_type(request, fund_id):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        is_idc = request.POST.get("is_idc") == "true"
        category = request.POST.get("category")  # New line

        if name and category:
            fund = get_object_or_404(Fund, fund_id=fund_id)
            CostType.objects.create(fund=fund, name=name, is_idc=is_idc, category=category)
    return redirect("fund_detail", fund_id=fund_id)
@login_required
def cost_center_detail(request, fund_id, cost_center_key):
    fund = get_object_or_404(Fund, fund_id=fund_id)


    cost_center_labels = {
        "direct_personnel": "Direct Personnel",
        "direct_non_personnel": "Direct Non-Personnel",
        "indirect_personnel": "Indirect Personnel",
        "indirect_non_personnel": "Indirect Non-Personnel",
    }

    suffix_map = {
        'direct_personnel': 'DP',
        'direct_non_personnel': 'DNP',
        'indirect_personnel': 'IP',
        'indirect_non_personnel': 'INP',
    }
    today = date.today()
    project = None
    pi = None

    # Find project with current budget period active today
    for p in fund.projects.all():
        periods = p.budget_period_entries.all().order_by('start_date')
        for period in periods:
            if period.start_date <= today <= period.end_date:
                project = p
                break
        if project:
            break

    # Fallback: if no active period project found, use first project
    if not project:
        project = fund.projects.first()

    if project and project.principal_investigator:
        pi = project.principal_investigator.get_full_name() or project.principal_investigator.username
    label = cost_center_labels.get(cost_center_key)
    if not label:
        return HttpResponse("Invalid Cost Center", status=400)
    if cost_center_key.startswith('direct'):
        cost_center_type = 'direct'
    elif cost_center_key.startswith('indirect'):
        cost_center_type = 'indirect'
    else:
        return HttpResponse("Invalid cost center type", status=400)

    if 'non_personnel' in cost_center_key:
        category = 'non_personnel'
    else:
        category = 'personnel'

    cost_types = fund.cost_types.filter(
        cost_center_type=cost_center_type,
        category=category,
    ).prefetch_related('entries')

    for ct in cost_types:
        ct.totals = ct.calculate_totals()

    # 🔥 CORRECT UNIQUE Cost Center ID
    # 🔥 Correct Unique Cost Center ID
    cost_center_id = f"CC-{fund.fund_id}-{suffix_map.get(cost_center_key, 'UNK')}"
    cost_center_name = f"{fund.fund_id} {label}"

    total_budget = Decimal('0.00')
    total_encumbrance = Decimal('0.00')
    total_projected = Decimal('0.00')
    total_expense = Decimal('0.00')
    total_balance = Decimal('0.00')
    # Calculate totals properly
    for ct in cost_types:
        ct.totals = ct.calculate_totals()
        total_budget += ct.totals.get('budget', Decimal('0.00'))
        total_encumbrance += ct.totals.get('encumbrance', Decimal('0.00'))
        total_projected += ct.totals.get('projected', Decimal('0.00'))
        total_expense += ct.totals.get('expense', Decimal('0.00'))
        total_balance += ct.totals.get('balance', Decimal('0.00'))
    context = {
        "fund": fund,
        "cost_center_label": label,
        "cost_center_key": cost_center_key,
        "cost_types": cost_types,
        "cost_center_id": cost_center_id,
        "cost_center_name": cost_center_name,
        "total_budget": total_budget,
        "total_encumbrance": total_encumbrance,
        "total_projected": total_projected,
        "total_expense": total_expense,
        "total_balance": total_balance,
        "principal_investigator": pi, 
    }

    return render(request, "admin/cost_center_detail.html", context)
@login_required
def add_cost_entry(request, fund_id):
    if request.method == "POST":
        type_id = request.POST.get("cost_type_id")
        description = request.POST.get("description")
        budget = Decimal(request.POST.get("budget") or 0)
        enc = Decimal(request.POST.get("encumbrance") or 0)
        proj = Decimal(request.POST.get("projected") or 0)
        balance = Decimal(request.POST.get("balance") or 0)

        cost_type = get_object_or_404(CostType, id=type_id)
        CostEntry.objects.create(
            cost_type=cost_type,
            description=description,
            budget=budget,
            encumbrance=enc,
            projected=proj,
            balance=balance
        )
    return redirect("fund_detail", fund_id=fund_id)


def fund_review(request, org_id):
    return render(request, 'fund/fund_review.html', {'org_id': org_id})

def fund_projections(request, org_id):
    return render(request, 'fund/fund_projections.html', {'org_id': org_id})

def task_review(request, org_id):
    return render(request, 'fund/task_review.html', {'org_id': org_id})
@login_required
def fund_personnel(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    users = User.objects.filter(organization=organization).select_related('organization')

    return render(request, 'admin/fund_personnel.html', {
        'org_id': org_id,
        'users': users,
    })



@login_required
def specific_personnel(request, org_id, unique_id):
    user = get_object_or_404(
        User.objects.prefetch_related(
            Prefetch('fund_assignments', queryset=UserFundAssignment.objects.select_related('fund'))
        ),
        unique_id=unique_id,
        organization_id=org_id
    )
    total_salary = user.fund_assignments.aggregate(total=Sum('salary_amount'))['total'] or 0

    return render(request, 'admin/specific_personnel.html', {
        'user_detail': user,
        'org_id': org_id,
        'total_salary': total_salary,
    })

@login_required
def fund_report(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)

    # Fetch funded projects
    fund_projects = Project.objects.filter(status="Funded", org_id=org_id).select_related("fund").distinct()
    funds = [p.fund for p in fund_projects if p.fund]

    # Employee Entries grouped by fund
    entries_by_fund = defaultdict(list)
    all_entries = EmployeeEntry.objects.filter(organization=organization).select_related("fund")
    for entry in all_entries:
        entries_by_fund[entry.fund_id].append(entry)

    glossary = GlossaryItem.objects.filter(organization=organization)
    glossary_dict = {
        'corporation_codes': glossary.filter(category='corporation_code'),
        'object_sets': glossary.filter(category='object_set'),
        'object_codes': glossary.filter(category='object_code'),
        'cost_centers': glossary.filter(category='cost_center'),
    }
    refs = CostEntry.objects.filter(
        fund__in=funds,
        is_reference=True
    ).values('ref_num1', 'description', 'cost_type__name', 'fund_id')

    # Organize by fund_id + subcategory
    refs_by_fund_subcat = defaultdict(list)
    for ref in refs:
        key = (ref['fund_id'], ref['cost_type__name'])
        refs_by_fund_subcat[key].append(ref)
    return render(request, 'admin/fund_report.html', {
        'organization': organization,
        'funds': funds,
        'entries_by_fund': entries_by_fund,
        'glossary': glossary_dict,
        'ref_lookup': refs_by_fund_subcat,
        'position_choices': User.POSITION_CHOICES,
        'benefits_choices': User.BENEFITS_CHOICES,
        'paytype_choices': User.PAYTYPE_CHOICES,
        'payperiod_choices': User.PAY_PERIOD_CHOICES,
    })
@login_required
def add_employee_entry(request, org_id):
    if request.method == "POST":
        fund = get_object_or_404(Fund, id=request.POST.get("fund_id"))
        cost_type_choice = request.POST.get("cost_type")
        subcategory = request.POST.get("personnel_subcategory")

        employee_id = request.POST.get("employee_id")
        employee_name = request.POST.get("employee_name")

        entry = EmployeeEntry.objects.create(
            fund=fund,
            organization_id=org_id,
            employee_name=employee_name,
            employee_id=employee_id,
            position=request.POST.get("position"),
            cost_type=cost_type_choice,
            corporation_code=request.POST.get("corporation_code"),
            object_set=request.POST.get("object_set"),
            object_code=request.POST.get("object_code"),
            cost_center=request.POST.get("cost_center"),
            start_date=request.POST.get("start_date"),
            end_date=request.POST.get("end_date"),
            salary=Decimal(request.POST.get("salary") or 0),
            benefits_package=request.POST.get("benefits_package"),
            pay_type=request.POST.get("pay_type"),
            pay_period=request.POST.get("pay_period"),
            hours_worked=Decimal(request.POST.get("hours_worked") or 0),
        )

        # 🛠️ Create the CostEntry too
        is_idc = cost_type_choice == "indirect"
        category = "personnel"
        cost_type_name = "Personnel" if is_idc else subcategory

        cost_type, _ = CostType.objects.get_or_create(
            fund=fund,
            name=cost_type_name,
            is_idc=is_idc,
            category=category
        )

        CostEntry.objects.create(
            cost_type=cost_type,
            description=f"{employee_name} (Employee) [ID: {employee_id}]",
            budget=entry.salary,
            encumbrance=Decimal("0.00"),
            projected=Decimal("0.00"),
            expense=entry.salary,
            balance=Decimal("0.00"),
        )

        # 🆕 Create a UserFundAssignment for this EmployeeEntry
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.get(unique_id=employee_id)
            UserFundAssignment.objects.create(
                user=user,
                fund=fund,
                salary_amount=entry.salary,
                start_date=entry.start_date,
                end_date=entry.end_date
            )
        except User.DoesNotExist:
            # user not found - maybe log warning or ignore
            pass

    return redirect("fund_report", org_id=org_id)

@login_required
def org_glossary(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    glossary_items = organization.glossary_items.all()  # Assumes related_name="glossary_items"
    return render(request, 'admin/org_glossary.html', {
        'organization': organization,
        'glossary_items': glossary_items,
        'category_labels': dict(GlossaryItem.CATEGORY_CHOICES),
    })

def glossary_view(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    glossary_items = GlossaryItem.objects.filter(organization=organization).order_by('term')

    category_labels = dict(GlossaryItem.CATEGORY_CHOICES)

    return render(request, 'admin/org_glossary.html', {
        'organization': organization,
        'glossary_items': glossary_items,
        'category_labels': category_labels,
    })

def add_glossary_item(request, org_id):
    if request.method == "POST":
        GlossaryItem.objects.create(
            organization_id=org_id,
            term=request.POST["term"],
            definition=request.POST["definition"],
            category=request.POST["category"]
        )
    return redirect('glossary_view', org_id=org_id)

@login_required
def update_idc_rate(request, org_id):
    if request.method == "POST":
        organization = get_object_or_404(Organization, id=org_id)
        try:
            rate = Decimal(request.POST.get("idc_rate", "0.00"))
            if 0 <= rate <= 100:
                organization.idc_rate = rate
                organization.save()
        except (ValueError, InvalidOperation):
            pass  # You could optionally show an error message here
    return redirect('glossary_view', org_id=org_id)