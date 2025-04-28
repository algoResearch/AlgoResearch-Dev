from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test, login_required
from .forms import ProjectForm, DepartmentForm, ProjectTaskForm, FormPackageForm,  TaskAttachmentForm, TaskCommentForm, OpportunityForm, TrainingFolderForm, SF424FormForm, OtherPersonnelForm, BudgetPeriodForm, PerformanceSiteLocationForm, SubMiniStepForm, MiniStepForm, MiniStepFieldForm, CertificationForm, CustomUserCreationForm, AdminCreatedFormForm, FormField, FormFieldForm, UploadPDFTemplateForm, ProtocolCreationForm, ProtocolApprovalForm
from django.db.models import Q, F, Avg, Max, Min, Count, Prefetch, Sum
from .models import ProtocolDesign, Fund, ProjectAccess, UserFundAssignment, GlossaryItem, BudgetAllocation, EmployeeEntry,ProjectBudgetPeriod, ProjectFinancials, CostEntry, CostType,  Agency, ReviewScore, Committee, CommitteeMember,  CalendarEvent, Department, RROtherInformation, ProjectOpportunity, PHSResearchPlan, ProjectAttachment, ProjectHistory, Note, RoutingDecision, ProjectTask, TaskAttachment, TaskComment, Opportunity, Project, SubmittedPackage, SF424Form, SF424Submission, OtherPersonnel, BudgetPeriod, PerformanceSiteLocation, FormPackage, PackageForm, SF424Field, Organization, PDFField, SubMiniStepField, MiniStep, SubMiniStep, MiniStepField, User, UserCertification, RFIDAssignment, Building, Room, TrainingFolder, Certification, Rack, ProtocolTemplate, ApprovalComment, SpeciesEntry, Attachment, Notification, Protocol, UserFilledForm, Animal, Cage, Experiment, UserAction, UserSignature, InboxNotification, SignedForm, AdminCreatedForm, Organization, PDFFieldMapping, Conversation, Message
from django.db.models.signals import post_save
from django.contrib.staticfiles import finders

from decimal import Decimal, InvalidOperation
from myapp.utils.pdf_field_mapping import field_positions  # Import the field mapping
import boto3
from django.template.loader import render_to_string
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
from decimal import InvalidOperation
import pdfkit
from django.core.files.storage import default_storage
from django.core.exceptions import PermissionDenied
from django.core.files import File
import pymupdf as fitz
from django.forms import inlineformset_factory
from django.forms import formset_factory
from django.utils import timezone
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

    return render(request, 'admin/fund_report.html', {
        'organization': organization,
        'funds': funds,
        'entries_by_fund': entries_by_fund,
        'glossary': glossary_dict,
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
def entry_detail(request, fund_id, entry_id):
    fund = get_object_or_404(Fund, fund_id=fund_id)
    entry = get_object_or_404(CostEntry, id=entry_id)

    context = {
        "fund": fund,
        "entry": entry,
    }

    return render(request, "admin/entry_detail.html", context)


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
def calendar_event_data(request, org_id):
    events = CalendarEvent.objects.filter(organization_id=org_id)
    data = [
        {
            "title": e.title,
            "start": e.start_date.isoformat(),
            "end": e.end_date.isoformat(),
            "color": e.color,
            "allDay": e.all_day,
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

        project.financials_display = {
            "budget_direct_cost": current_budget,
            "budget_fa": Decimal("0.00"),
            "budget_total": current_budget,

            "expenses_direct_cost": Decimal("0.00"),
            "expenses_fa": Decimal("0.00"),
            "expenses_total": Decimal("0.00"),

            "balance_direct_cost": current_budget,
            "balance_fa": Decimal("0.00"),
            "balance_total": current_budget,

            "encumbrance_direct_cost": Decimal("0.00"),
            "encumbrance_fa": Decimal("0.00"),
            "encumbrance_total": Decimal("0.00"),

            "projected_direct_cost": Decimal("0.00"),
            "projected_fa": Decimal("0.00"),
            "projected_total": Decimal("0.00"),

            "projected_balance_direct_cost": current_budget,
            "projected_balance_fa": Decimal("0.00"),
            "projected_balance_total": current_budget,
        }

    context = {
        'user': user,
        'org_id': org_id,
        'fund_projects': fund_projects,
        'user_cost_centers': user_cost_centers,
        'funds': Fund.objects.filter(id__in=fund_projects.values_list("fund_id", flat=True)),
        'total_users': User.objects.count(),
        'upcoming_events': 0,
        'pending_tasks': 0,
    }

    return render(request, "admin/admin_dashboard.html", context)

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
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from .models import ProjectTask, TaskAttachment, TaskComment
from .forms import TaskAttachmentForm, TaskCommentForm

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
            "submission_types", "application_types", "agency_routing_identifier", "previous_grants_gov_tracking_id",
            "revision_type", "otherRevisionText", "submittedToOtherAgencies", "otherAgencies",
            "date_submitted", "applicant_identifier", "date_received_by_state", "state_application_identifier",
            "federal_identifier", "agency_routing_number", "previous_tracking_id", "uei", 
            "legal_name", "department", "division", "address_street1", "zip_code"
        ]
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
    additional_forms = []
    for form in package.package_forms.all():
        form_display_name = (
            form.html_template_name.replace(".html", "").replace("_", " ").title()
            if form.html_template_name else "Untitled Form"
        )
        additional_forms.append({
            "id": str(form.id),
            "name": form_display_name,
            "template": form.html_template_name
        })
    all_forms = additional_forms  # If no PDF forms, this is enough
    session_progress_key = f"{org_id}_{package_id}_progress"
    form_progress = request.session.get(session_progress_key, {})

    selected_form_id = request.GET.get("form") or (all_forms[0]["id"] if all_forms else None)
    selected_form = next((form for form in all_forms if form["id"] == selected_form_id), None)

    current_index = next((i for i, form in enumerate(all_forms) if form["id"] == selected_form_id), None)
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
    if selected_form and selected_form["template"] == "admin/fill_out_PHS_Plan.html":
        if not 'phs_plan_data' in locals():
            phs_plan_data = {}
        context_phs_plan_data = phs_plan_data  # fallback to empty if not set
    else:
        context_phs_plan_data = {}
    form_template = selected_form["template"] if selected_form else None
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
        "form_id": selected_form["id"] if selected_form else None,
        "template_name": selected_form["template"] if selected_form else None,
        "form_template": form_template,
        "user_data": user_data,
        "sf424_status": sf424_status,
        "form_progress": form_progress,
        "previous_form": previous_form,
        "next_form": next_form,
        "draft_exists": draft_exists,
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

        assignees = data.get('assignees', [])
        for username in assignees:
            user = User.objects.filter(username=username).first()
            if user:
                task.assignees.add(user)
        task.save()

        return JsonResponse({'status': 'success', 'message': 'Task created successfully.'})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})

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
    

def package_summary(request, org_id, package_id):
    project_id = request.session.get("project_id")
    if not project_id:
        return HttpResponse("Missing project context.", status=400)

    draft = SubmittedPackage.objects.filter(
        org_id=org_id,
        package_id=package_id,
        project_id=project_id,
        is_draft=True
    ).last()

    if not draft:
        return HttpResponse("No draft found for summary.", status=404)

    # Load form-specific data
    sf424_data = draft.sf424_data or {}
    budget_periods = draft.budget_periods or []
    # ⬇ With this safe version
    raw_skp = draft.senior_key_person_data
    if isinstance(raw_skp, str):
        try:
            senior_key_person_data = json.loads(raw_skp)
        except json.JSONDecodeError:
            senior_key_person_data = []
    elif isinstance(raw_skp, list):
        senior_key_person_data = raw_skp
    else:
        senior_key_person_data = []
    project_performance_data = (
        json.loads(draft.project_performance_data)
        if draft.project_performance_data and isinstance(draft.project_performance_data, str)
        else draft.project_performance_data or {}
    )
    phs_plan_data = draft.phs_plan_data or {}
    # Load PHS Human Subjects Data
    if hasattr(draft, "phs_human_subject_data"):
        if isinstance(draft.phs_human_subject_data, str):
            try:
                phs_human_subject_data = json.loads(draft.phs_human_subject_data)
            except json.JSONDecodeError:
                phs_human_subject_data = {}
        elif isinstance(draft.phs_human_subject_data, dict):
            phs_human_subject_data = draft.phs_human_subject_data
        else:
            phs_human_subject_data = {}
    else:
        phs_human_subject_data = {}
    # Load cumulative totals safely
    if isinstance(draft.cumulative_totals, str):
        try:
            cumulative_totals = json.loads(draft.cumulative_totals)
        except json.JSONDecodeError:
            cumulative_totals = {}
    else:
        cumulative_totals = draft.cumulative_totals or {}

    # Load RR Other Info data
    # Try JSON field first (SubmittedPackage)
    if draft.RR_Other_Info_data:
        rr_other_info_data = draft.RR_Other_Info_data
        if isinstance(rr_other_info_data, str):
            try:
                rr_other_info_data = json.loads(rr_other_info_data)
            except json.JSONDecodeError:
                rr_other_info_data = {}
    else:
        # Fallback to legacy model
        try:
            rr_other_info_entry = RROtherInformation.objects.filter(
                organization_id=org_id,
                project_id=project_id,
                package_id=package_id
            ).latest("created_at")

            rr_other_info_data = {
                "proprietary_info": rr_other_info_entry.proprietary_info,
                "environmental_impact": rr_other_info_entry.environmental_impact,
                "historic_properties": rr_other_info_entry.historic_properties,
                "human_subjects": rr_other_info_entry.human_subjects,
                "vertebrate_animals": rr_other_info_entry.vertebrate_animals,
                "international_collaboration": rr_other_info_entry.international_collaboration,
                "exemption_numbers": rr_other_info_entry.exemption_numbers,
                "human_assurance_number": rr_other_info_entry.human_assurance_number,
                "irb_approval_date": rr_other_info_entry.irb_approval_date,
                "animal_welfare_number": rr_other_info_entry.animal_welfare_number,
                "iacuc_approval_date": rr_other_info_entry.iacuc_approval_date,
                "environmental_explanation": rr_other_info_entry.environmental_explanation,
                "environmental_exemption_explanation": rr_other_info_entry.environmental_exemption_explanation,
                "historic_explanation": rr_other_info_entry.historic_explanation,
                "international_countries": rr_other_info_entry.international_countries,
                "international_explanation": rr_other_info_entry.international_explanation,
                "uploaded_file": rr_other_info_entry.uploaded_file.url if rr_other_info_entry.uploaded_file else "",
            }
        except RROtherInformation.DoesNotExist:
            rr_other_info_data = {}
    # Load form types for template selection
    package = get_object_or_404(FormPackage, id=package_id)
    included_form_types = get_included_form_types(package)

    # Default to combined summary if multiple form types exist
    summary_template = "admin/combined_summary.html"
    # PHS Plan attachment field config
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
    return render(request, summary_template, {
        "sf424_data": sf424_data,
        "budget_periods": budget_periods,
        "cumulative_totals": cumulative_totals,
        "senior_key_person_data": senior_key_person_data,
        "project_performance_data": project_performance_data,
        "rr_other_info_data": rr_other_info_data,
        "phs_plan_data": phs_plan_data,
        "phs_human_subject_data": phs_human_subject_data, 
        "attachment_fields": attachment_fields,  # ✅ Include this
        "org_id": org_id,
        "package_id": package_id,
        "included_form_types": included_form_types,
    })

def save_combined_draft(request, org_id, package_id, project, opportunity, sf424_data, budget_periods, cumulative_totals):
    try:
        # Combine both data into one JSON object
        combined_data = {
            "sf424_data": sf424_data,
            "budget_periods": budget_periods,
            "cumulative_totals": cumulative_totals,
        }

        # Convert to JSON
        combined_data_json = json.dumps(combined_data)

        # Check if a draft already exists
        draft, created = SubmittedPackage.objects.get_or_create(
            user=request.user,
            org_id=org_id,
            package_id=package_id,
            project=project,
            opportunity=opportunity,
            is_draft=True,
            defaults={
                "submission_name": f"Draft - {project.name if project else 'Unknown'}",
                "submission_date": timezone.now(),
                "sf424_data": json.dumps(sf424_data),
                "budget_periods": budget_periods,
                "cumulative_totals": cumulative_totals,
            }
        )

        # Update the existing draft if it already exists
        if not created:
            draft.submission_name = f"Draft - {project.name if project else 'Unknown'}"
            draft.submission_date = timezone.now()
            draft.sf424_data = json.dumps(sf424_data)
            draft.budget_periods = budget_periods
            draft.cumulative_totals = cumulative_totals
            draft.save()

        print(f"✅ Draft saved successfully for combined package: {project.name}")
        messages.success(request, "Draft saved successfully.")
    except Exception as e:
        print(f"❌ Error saving combined draft: {str(e)}")
        messages.error(request, f"Error saving combined draft: {str(e)}")

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
    print("Submitting package...")

    if request.method == "POST":
        submission_name = request.POST.get("submission_name", "").strip()
        print(f"Submission Name: {submission_name}")

        if not submission_name:
            messages.error(request, "Submission name is required.")
            return redirect("package_summary", org_id=org_id, package_id=package_id)

        # Load draft data from session
        sf424_key = f"sf424_data_{org_id}_{package_id}"
        budget_periods_key = f"budget_periods_{org_id}_{package_id}"
        cumulative_totals_key = f"cumulative_totals_{org_id}_{package_id}"

        sf424_data = request.session.get(sf424_key, {})
        budget_periods = request.session.get(budget_periods_key, [])
        cumulative_totals = request.session.get(cumulative_totals_key, {})

        print(f"SF-424 Data: {sf424_data}")
        print(f"Budget Periods: {budget_periods}")
        print(f"Cumulative Totals: {cumulative_totals}")

        # ✅ Get project from session
        project_id = request.session.get("project_id")
        if not project_id:
            messages.error(request, "Project ID missing from session.")
            return redirect("package_summary", org_id=org_id, package_id=package_id)

        project = get_object_or_404(Project, id=project_id)
        print(f"✅ Project: {project.name} (ID: {project.id})")

        # ✅ Get opportunity via ProjectOpportunity
        project_opportunity = ProjectOpportunity.objects.filter(
            project=project,
            opportunity__form_package_id=package_id
        ).first()

        if not project_opportunity:
            messages.error(request, "No opportunity linked to this package and project.")
            return redirect("package_summary", org_id=org_id, package_id=package_id)

        opportunity = project_opportunity.opportunity
        print(f"✅ Opportunity: {opportunity.title} (#{opportunity.number})")

        # ✅ Save final submission
        SubmittedPackage.objects.create(
            user=request.user,
            org_id=org_id,
            package_id=package_id,
            project=project,
            opportunity=opportunity,
            submission_name=submission_name,
            sf424_data=sf424_data,
            budget_periods=budget_periods,
            cumulative_totals=cumulative_totals,
            is_draft=True,
            last_edited_by=request.user,
        )

        messages.success(request, f"Package '{submission_name}' submitted successfully.")
        print(f"✅ Submission successful. Redirecting to project home...")
        return redirect("specific_project_home", org_id=org_id, project_id=project.id)

    # If not POST, redirect to summary page
    print("⚠️ Submission method not POST. Redirecting to package summary...")
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
    submission = get_object_or_404(SubmittedPackage, id=submission_id)

    import hashlib, os
    from django.core.files import File
    from dashboard.models import ProjectAttachment
    from django.conf import settings

    # ✅ Hash helper
    def compute_file_hash_from_path(path):
        sha256 = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()

    # ✅ Attach a single PDF if not already present
    def maybe_attach_pdf_to_project(path, label):
        if not os.path.exists(path):
            print(f"❌ Skipping: {path} not found.")
            return

        file_hash = compute_file_hash_from_path(path)
        if ProjectAttachment.objects.filter(project=submission.project, file_hash=file_hash).exists():
            print(f"⚠️ Already attached (hash matched): {label}")
            return

        with open(path, 'rb') as f:
            django_file = File(f)
            filename = os.path.basename(path)
            attachment = ProjectAttachment(
                project=submission.project,
                uploaded_by=submission.user,
                label=label,
                file_hash=file_hash
            )
            attachment.file.save(filename, django_file, save=True)
            print(f"📎 Attached PDF to project: {filename}")

    # ✅ Only attach PDFs if the submission is finalized
    if not submission.is_draft:
        base_path = os.path.join(settings.MEDIA_ROOT, 'generated_pdfs')
        pdf_map = {
            "SF-424 PDF": f"{base_path}/sf424_{submission.id}.pdf",
            "RR Budget PDF": f"{base_path}/rr_budget_{submission.id}.pdf",
            "PHS Human Subjects PDF": f"{base_path}/phs_subjects_{submission.id}.pdf",
            "PHS Research Plan PDF": f"{base_path}/phs_plan_{submission.id}.pdf",
            "Project Performance PDF": f"{base_path}/project_sites_{submission.id}.pdf",
            "Senior/Key Personnel PDF": f"{base_path}/skp_{submission.id}.pdf",
            "RR Other Info PDF": f"{base_path}/rr_other_info_{submission.id}.pdf",
            "Combined Forms PDF": f"{base_path}/combined_{submission.id}.pdf",
        }

        for label, full_path in pdf_map.items():
            maybe_attach_pdf_to_project(full_path, label)

    try:
        package = FormPackage.objects.get(id=submission.package_id)
        print(f"✅ FormPackage found: {package.name}")
    except FormPackage.DoesNotExist:
        print(f"❌ FormPackage ID {submission.package_id} not found.")
        return HttpResponse("Form package not found", status=404)

    included_form_types = list(package.package_forms.values_list("form_type", flat=True))

    def safe_json(data, fallback):
        if isinstance(data, str):
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return fallback
        return data or fallback

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
        "org_id": org_id,
        "form_id": submission.package_id,
        "included_form_types": included_form_types,
        "sf424_data": safe_json(submission.sf424_data, {}),
        "budget_periods": safe_json(submission.budget_periods, []),
        "cumulative_totals": safe_json(submission.cumulative_totals, {}),
        "attachment_fields": attachment_fields,
        "senior_key_person_data": safe_json(submission.senior_key_person_data, []),
        "project_performance_data": safe_json(submission.project_performance_data, {}),
        "rr_other_info_data": safe_json(submission.RR_Other_Info_data, {}),
        "phs_plan_data": safe_json(submission.phs_plan_data, {}),
        "phs_human_subject_data": safe_json(submission.phs_human_subject_data, {}),
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
    

@login_required
def assign_pi(request, org_id, project_id):
    project = get_object_or_404(Project, id=project_id, org_id=org_id)

    if request.method == "POST":
        user_id = request.POST.get("user_id")

        if not user_id or not user_id.isdigit():
            messages.error(request, "Please select a valid user from the suggestions.")
            return redirect("specific_project_home", org_id=org_id, project_id=project_id)

        try:
            user = User.objects.get(id=user_id, organization_id=org_id)
            project.principal_investigator = user
            project.save()
            messages.success(request, f"{user.get_full_name()} assigned as Principal Investigator.")
        except User.DoesNotExist:
            messages.error(request, "User not found or not part of this organization.")

    return redirect("specific_project_home", org_id=org_id, project_id=project_id)

@login_required
def project_dashboard(request, org_id):
    # Projects where the user is either:
    # - in the access list (always), OR
    # - in the routing list AND the project is under review or later
    projects = Project.objects.filter(
        org_id=org_id
    ).filter(
        Q(users__in=[request.user]) |
        Q(routing_users__in=[request.user], status__in=["Under Review", "Approved", "Rejected"])
    ).distinct()

    if request.method == "POST":
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.org_id = org_id
            project.project_identifier = project.generate_unique_identifier(org_id)
            project.save()
            project.users.add(request.user)
            ProjectAccess.objects.get_or_create(
                project=project,
                user=request.user,
                defaults={
                    'can_edit': True,
                    'permission': 'edit',
                }
            )
            # Add creator to routing and auto-approve
            project.routing_users.add(request.user)

            RoutingDecision.objects.create(
                project=project,
                user=request.user,
                decision="approve",
                comments="Automatically approved by creator",
                decision_date=timezone.now(),
                status="approved"
            )
            ProjectHistory.objects.create(
                project=project,
                event_type="Project Created",
                description=f"{request.user.get_full_name() or request.user.username} created project '{project.name}'."
            )
            project.save()
            return redirect('specific_project_home', org_id=org_id, project_id=project.id)
    else:
        form = ProjectForm()

    return render(request, 'admin/project_dashboard.html', {
        'projects': projects,
        'form': form,
        'org_id': org_id
    })

@login_required
@user_passes_test(is_admin_or_principal)
def add_project_users(request, org_id, project_id):
    organization = get_object_or_404(Organization, id=org_id)
    project = get_object_or_404(Project, id=project_id)

    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            selected_users = data.get('selected_users', [])
            logger.warning(f"Received selected_users: {selected_users}")
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)

        if not selected_users:
            logger.warning("No users submitted.")
            return JsonResponse({'status': 'success', 'message': 'No users added.'})

        added_users = []

        for entry in selected_users:
            username = entry.get('username')
            permission = entry.get('permission', 'view')

            logger.warning(f"Checking username: {username}, permission: {permission}")
            if user.position_type in ['app_editor', 'dept_app_editor']:
                can_edit = True
                permission = 'edit'
            else:
                can_edit = permission == 'edit'
            if username and permission in ['view', 'edit']:
                try:
                    user = User.objects.get(username=username, organization=organization)
                    logger.warning(f"User found: {user.username}")

                    can_edit = permission == 'edit'

                    ProjectAccess.objects.update_or_create(
                        project=project,
                        user=user,
                        defaults={'can_edit': can_edit, 'permission': permission}
                    )

                    project.users.add(user)
                    added_users.append(username)
                except User.DoesNotExist:
                    logger.warning(f"User not found or not in org: {username}")
                    continue

        if added_users:
            return JsonResponse({'status': 'success', 'message': 'Users added to project successfully.', 'added_users': added_users})
        else:
            return JsonResponse({'status': 'error', 'message': 'No valid users found.'}, status=400)

        # GET fallback
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

@login_required
def search_project_users(request, org_id):
    query = request.GET.get('query', '').strip()
    organization = get_object_or_404(Organization, id=org_id)

    # Filter users in the organization matching the query
    users = User.objects.filter(
        organization=organization
    ).filter(
        Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query)
    ).exclude(id=request.user.id)

    # Prepare the user data for the response
    user_data = [
        {
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'profile_picture': user.profile_picture.url if user.profile_picture else None,
        }
        for user in users
    ]

    return JsonResponse({'users': user_data})
def specific_project_home(request, org_id, project_id):
    # ✅ Get the project
    project = get_object_or_404(Project, id=project_id)

    # ✅ Handle search and pagination
    search_query = request.GET.get("q", "")
    page_number = request.GET.get("page", 1)

    # ✅ Get submissions and drafts
    submissions = SubmittedPackage.objects.filter(project=project, is_draft=False).order_by("-submission_date")
    drafts = SubmittedPackage.objects.filter(project=project, is_draft=True).order_by("-submission_date")

    # ✅ Get the current user's draft, if any
    user_draft = drafts.filter(user=request.user).first()

    # ✅ Project users and routing users
    users = project.users.all()
    routing_users = project.routing_users.all() if project.status == "Under Review" else []

    # ✅ Get opportunities not yet added to this project
    added_opportunity_ids = ProjectOpportunity.objects.filter(
        project=project
    ).values_list("opportunity_id", flat=True)

    opportunities = Opportunity.objects.filter(
        form_package__isnull=False
    ).exclude(id__in=added_opportunity_ids)

    if search_query:
        opportunities = opportunities.filter(
            Q(title__icontains=search_query) |
            Q(number__icontains=search_query) |
            Q(agency_ref__name__icontains=search_query)
        )

    paginator = Paginator(opportunities.order_by("-close_date"), 10)
    paginated_opportunities = paginator.get_page(page_number)

    # ✅ Determine if any extra forms like RR_Other_Info are included
    latest_submission = submissions.first()
    included_form_types = []
    if latest_submission and latest_submission.RR_Other_Info_data:
        included_form_types.append("rr_other_info")

    # ✅ Template context
    context = {
        "project": project,
        "org_id": org_id,
        "project_id": project_id,
        "opportunities": paginated_opportunities,
        "search_query": search_query,
        "submissions": submissions,
        "drafts": drafts,
        "user_draft": user_draft,
        "users": users,
        "routing_users": routing_users,
        "latest_submission": latest_submission,
        "included_form_types": included_form_types,
    }
    return render(request, "admin/specific_project_home.html", context)

@login_required
def get_project_users(request, org_id, project_id):
    project = get_object_or_404(Project, id=project_id)
    users = project.users.all()

    user_data = [
        {
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
        }
        for user in users
    ]

    return JsonResponse({'users': user_data})
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
    task = get_object_or_404(ProjectTask, project_id=project_id, task_id=str(task_id))

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
                'file_url': attachment.file.url,
                'uploaded_by': attachment.uploaded_by.username,
                'uploaded_at': attachment.uploaded_at.strftime("%Y-%m-%d %H:%M:%S"),
            })
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid file upload.'})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})

@login_required
@csrf_exempt
def add_task_comment(request, project_id, task_id):
    task = get_object_or_404(ProjectTask, project_id=project_id, task_id=task_id)
    if request.method == "POST":
        form = TaskCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.task = task
            comment.author = request.user
            comment.save()
            return JsonResponse({
                'status': 'success',
                'message': 'Comment added successfully!',
                'author': comment.author.username,
                'content': comment.content,
                'created_at': comment.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            })
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid comment data.'})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})


@login_required
def mark_task_completed(request, project_id, task_id):
    task = get_object_or_404(ProjectTask, project_id=project_id, task_id=task_id)
    if request.user == task.assigned_by or request.user in task.assignees.all():
        task.mark_completed(request.user)
        return JsonResponse({
            'status': 'success', 
            'message': 'Task marked as completed.',
            'completed_by': task.task_completed_by.username if task.task_completed_by else 'N/A',
            'completed_at': task.completed_at.strftime("%Y-%m-%d %H:%M:%S") if task.completed_at else 'N/A',
        })
    return JsonResponse({'status': 'error', 'message': 'Permission denied.'})


@login_required
def update_task_status(request, project_id):
    data = json.loads(request.body)
    tasks = ProjectTask.objects.filter(project_id=project_id, task_id=str(data.get('task_id')))
    if not tasks.exists():
        return JsonResponse({'status': 'error', 'message': 'Task not found'}, status=404)
    if tasks.count() > 1:
        return JsonResponse({'status': 'error', 'message': 'Multiple tasks found with the same ID'}, status=400)
    task = tasks.first()
    task.status = data.get('status', 'in_progress')
    task.save()
    return JsonResponse({'status': 'success', 'message': 'Task status updated successfully.'})


@csrf_exempt
def update_sf424_status(request, org_id, package_id, project_id):
    try:
        if request.method == "POST":
            print("✅ Update endpoint hit!")
            data = json.loads(request.body)
            field_name = data.get("fieldName")
            field_value = data.get("fieldValue")
            print(f"Received field name: {field_name}, field value: {field_value}")

            draft = SubmittedPackage.objects.filter(
                org_id=org_id,
                package_id=package_id,
                project_id=project_id,
                is_draft=True
            ).last()

            if draft:
                sf424_data = json.loads(draft.sf424_data) if isinstance(draft.sf424_data, str) else draft.sf424_data
                sf424_data[field_name] = field_value
                draft.sf424_data = json.dumps(sf424_data)
                draft.save()

                # Check if the field is considered "answered"
                is_answered = bool(field_value.strip() and field_value != "Not Provided")

                print(f"✅ Field {field_name} updated successfully with value {field_value}")
                return JsonResponse({
                    "status": "success",
                    "message": f"Updated {field_name} with {field_value}",
                    "field_name": field_name,
                    "field_status": is_answered
                })
            else:
                print("❌ Draft not found")
                return JsonResponse({"status": "error", "message": "Draft not found"}, status=404)
    except Exception as e:
        print(f"❌ Error updating SF-424 status: {str(e)}")
        return JsonResponse({"status": "error", "message": str(e)}, status=500)
    

def compute_file_hash_from_path(path):
    sha256 = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()

def maybe_attach_pdf_to_project(project, user, path, label):
    if not os.path.exists(path):
        print(f"❌ Skipping: {path} not found.")
        return

    file_hash = compute_file_hash_from_path(path)
    if ProjectAttachment.objects.filter(project=project, file_hash=file_hash).exists():
        print(f"⚠️ Already attached (hash matched): {label}")
        return

    with open(path, 'rb') as f:
        django_file = File(f)
        filename = os.path.basename(path)
        attachment = ProjectAttachment(
            project=project,
            uploaded_by=user,
            label=label,
            file_hash=file_hash
        )
        attachment.file.save(filename, django_file, save=True)
        print(f"📎 Attached PDF to project: {filename}")

@login_required
@user_passes_test(is_admin_or_principal)
def update_project_status(request, org_id, project_id):
    project = get_object_or_404(Project, id=project_id)
    new_status = request.POST.get('status')

    if new_status in ['Development', 'Under Review', 'Approved']:
        project.status = new_status
        project.save()

        ProjectHistory.objects.create(
            project=project,
            event_type="Status Update",
            description=f"Project status changed to '{new_status}' by {request.user.username}."
        )

        # ✅ Add routing users if status is 'Under Review'
        if new_status == 'Under Review':
            routing_users = project.routing_users.all()
            for user in routing_users:
                if user not in project.users.all():
                    project.users.add(user)
                    ProjectHistory.objects.create(
                        project=project,
                        event_type="Routing User Addition",
                        description=f"Routing user '{user.username}' was added to project {project.name}."
                    )

        # ✅ Attach finalized PDFs if status is 'Approved'
        if new_status == 'Approved':
            base_path = os.path.join(settings.MEDIA_ROOT, 'generated_pdfs')

            def compute_file_hash_from_path(path):
                sha256 = hashlib.sha256()
                with open(path, 'rb') as f:
                    for chunk in iter(lambda: f.read(8192), b''):
                        sha256.update(chunk)
                return sha256.hexdigest()

            def maybe_attach_pdf_to_project(project, uploaded_by, path, label):
                if not os.path.exists(path):
                    print(f"❌ Skipping: {path} not found.")
                    return

                file_hash = compute_file_hash_from_path(path)
                if ProjectAttachment.objects.filter(project=project, file_hash=file_hash).exists():
                    print(f"⚠️ Already attached (hash matched): {label}")
                    return

                with open(path, 'rb') as f:
                    django_file = File(f)
                    filename = os.path.basename(path)
                    attachment = ProjectAttachment(
                        project=project,
                        uploaded_by=uploaded_by,
                        label=label,
                        file_hash=file_hash
                    )
                    attachment.file.save(filename, django_file, save=True)
                    print(f"📎 Attached PDF to project: {filename}")

            for submission in project.submittedpackage_set.filter(is_draft=False):
                pdf_map = {
                    "SF-424 PDF": f"{base_path}/sf424_{submission.id}.pdf",
                    "RR Budget PDF": f"{base_path}/rr_budget_{submission.id}.pdf",
                    "PHS Human Subjects PDF": f"{base_path}/phs_subjects_{submission.id}.pdf",
                    "PHS Research Plan PDF": f"{base_path}/phs_plan_{submission.id}.pdf",
                    "Project Performance PDF": f"{base_path}/project_sites_{submission.id}.pdf",
                    "Senior/Key Personnel PDF": f"{base_path}/skp_{submission.id}.pdf",
                    "RR Other Info PDF": f"{base_path}/rr_other_info_{submission.id}.pdf",
                    "Combined Forms PDF": f"{base_path}/combined_{submission.id}.pdf",
                }

                for label, pdf_path in pdf_map.items():
                    maybe_attach_pdf_to_project(project, submission.user, pdf_path, label)

        return JsonResponse({'status': 'success', 'new_status': project.status})

    return JsonResponse({'status': 'error', 'message': 'Invalid status'})

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
@login_required
def add_other_personnel(request, org_id):
    if request.method == "POST":
        fund = get_object_or_404(Fund, id=request.POST.get("fund_id"))
        organization = fund.organization

        description = request.POST.get("description")
        subcategory = request.POST.get("subcategory")
        start_date = datetime.strptime(request.POST.get("start_date"), "%Y-%m-%d").date()
        end_date = datetime.strptime(request.POST.get("end_date"), "%Y-%m-%d").date()
        monthly_amount = Decimal(request.POST.get("monthly_amount") or 0)

        duration_months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1
        total_amount = monthly_amount * duration_months

        cost_type, _ = CostType.objects.get_or_create(
            fund=fund,
            name=subcategory,
            is_idc=False,
            category="non_personnel"
        )

        CostEntry.objects.create(
            cost_type=cost_type,
            description=description,
            budget=total_amount,
            encumbrance=Decimal("0.00"),
            projected=Decimal("0.00"),
            expense=total_amount,
            balance=Decimal("0.00"),
            transaction_date=start_date,
            fund=fund,
            organization=organization,
            program=request.POST.get("program"),
            flex1=request.POST.get("flex1"),
            flex2=request.POST.get("flex2"),
            cost_center=request.POST.get("cost_center"),
            object_set=request.POST.get("object_set"),
            object_code=request.POST.get("object_code"),
            accounting_period=request.POST.get("accounting_period"),
            check_number=request.POST.get("check_number"),
            invoice_number=request.POST.get("invoice_number"),
            account2=request.POST.get("account2"),

            # 🆕 Reference fields
            ref_num1=request.POST.get("ref_num1"),
            ref_num2=request.POST.get("ref_num2"),
            code=request.POST.get("code"),
            vendor=request.POST.get("vendor"),
        )
    return redirect("fund_report", org_id=org_id)

@login_required
def add_opportunity(request, org_id, project_id, opportunity_number):
    project = get_object_or_404(Project, id=project_id)
    opportunity = Opportunity.objects.filter(number=opportunity_number).first()
    organization = get_object_or_404(Organization, id=org_id)  # Add this near the top
    if not opportunity:
        return HttpResponse("Opportunity not found", status=404)

    form_package = opportunity.form_package

    # Ensure it's only added once per project
    project_opportunity, created = ProjectOpportunity.objects.get_or_create(
        opportunity=opportunity,
        project=project
    )

    # 🔄 Add attached users from opportunity
    for user in opportunity.attached_users.all():
        if user not in project.routing_users.all():
            project.routing_users.add(user)
            ProjectHistory.objects.create(
                project=project,
                event_type="Routing User Auto-Added",
                description=f"User '{user.username}' was auto-added to routing from Opportunity '{opportunity.number}'."
            )

    # 🔄 Auto-add department editor/viewer if request user has a department
    if request.user.department:
        department = request.user.department
        dept_users = User.objects.filter(
            department=department,
            position_type__in=['dept_app_editor', 'dept_app_viewer']
        )

        for user in dept_users:
            if user not in project.routing_users.all():
                project.routing_users.add(user)
                ProjectHistory.objects.create(
                    project=project,
                    event_type="Routing User Auto-Added",
                    description=f"Department user '{user.username}' ({user.position_type}) was auto-added to routing."
                )

    # ✅ Auto-add Application Editors/Viewers (Org-wide and Dept-specific)
    all_possible_users = User.objects.filter(
        Q(position_type__in=['app_editor', 'app_viewer'], organization=organization) |
        Q(position_type__in=['dept_app_editor', 'dept_app_viewer'], department__name=project.admin_unit, organization=organization)
    )

    for user in all_possible_users:
        if not ProjectAccess.objects.filter(user=user, project=project).exists():
            can_edit = user.position_type in ['app_editor', 'dept_app_editor']
            permission = 'edit' if can_edit else 'view'

            ProjectAccess.objects.create(
                project=project,
                user=user,
                can_edit=can_edit,
                permission=permission
            )
            project.users.add(user)

            ProjectHistory.objects.create(
                project=project,
                event_type="Access Auto-Added",
                description=f"User '{user.username}' ({user.position_type}) was auto-added to project access with '{permission}' access."
            )

        if user not in project.routing_users.all():
            project.routing_users.add(user)
            ProjectHistory.objects.create(
                project=project,
                event_type="Routing User Auto-Added",
                description=f"User '{user.username}' ({user.position_type}) was auto-added to routing due to their application access role."
            )
    if request.method == 'POST':
        form = OpportunityForm(request.POST)
        if form.is_valid():
            submission = SubmittedPackage.objects.create(
                user=request.user,
                org_id=org_id,
                project=project,
                opportunity=opportunity,
                package_id=form_package.id,
                submission_name=form.cleaned_data.get("proposal_name", f"Opportunity {opportunity.number}"),
                is_draft=True,
                approval_status='draft',  # ✅ Add this line
                sf424_data={},
                rr_budget_data={},
                budget_periods=[],
                cumulative_totals={},
            )

            ProjectHistory.objects.create(
                project=project,
                event_type="Opportunity Added",
                description=f"Opportunity '{opportunity.title}' (#{opportunity.number}) was added to the project.",
            )

            request.session["project_id"] = project_id

            return redirect('package_display', org_id=org_id, package_id=form_package.id, project_id=project.id)
    else:
        form = OpportunityForm()

    return render(request, 'admin/add_opportunity.html', {
        'org_id': org_id,
        'project_id': project_id,

        'opportunity_number': opportunity_number,
        'form': form,
        'form_package': form_package,
    })


@login_required
@user_passes_test(lambda u: u.position_type in ['agency_user', 'nih_sro', 'nih_chair', 'nih_board_member'] and u.agency is not None)
def mark_funded_project(request, opportunity_id):
    opportunity = get_object_or_404(Opportunity, id=opportunity_id, agency_ref=request.user.agency)

    if request.method == "POST":
        funded_project_id = request.POST.get("funded_project_id")
        start_date = request.POST.get("start_date")
        end_date = request.POST.get("end_date")
        award_total = request.POST.get("award_total")

        if not funded_project_id:
            messages.error(request, "No project selected.")
            return redirect("opportunity_submissions_view", opportunity_id=opportunity_id)

        try:
            funded_project = Project.objects.get(id=funded_project_id)
        except Project.DoesNotExist:
            messages.error(request, "Selected project does not exist.")
            return redirect("opportunity_submissions_view", opportunity_id=opportunity_id)

        submissions = SubmittedPackage.objects.filter(
            opportunity=opportunity,
            is_draft=False
        ).select_related("project")

        for sub in submissions:
            project = sub.project
            if project == funded_project:
                # ✅ Set basic project funding info
                project.status = "Funded"
                project.project_start_date = start_date
                project.project_end_date = end_date
                project.award_total = award_total

                # 🧮 Budget Periods
                try:
                    num_periods = int(request.POST.get("num_budget_periods", 0))
                except (TypeError, ValueError):
                    num_periods = 0

                budget_periods = []
                for i in range(1, num_periods + 1):
                    start = request.POST.get(f"period_{i}_start")
                    end = request.POST.get(f"period_{i}_end")
                    budget = request.POST.get(f"period_{i}_budget")
                    if start and end and budget:
                        budget_periods.append({
                            "start": start,
                            "end": end,
                            "budget": budget,
                        })

                # ❌ Clear old periods
                ProjectBudgetPeriod.objects.filter(project=project).delete()

                # ✅ Create new periods
                for period in budget_periods:
                    try:
                        start_obj = datetime.strptime(period["start"], "%Y-%m-%d").date()
                        end_obj = datetime.strptime(period["end"], "%Y-%m-%d").date()
                        budget_amount = Decimal(period["budget"])

                        ProjectBudgetPeriod.objects.create(
                            project=project,
                            start_date=start_obj,
                            end_date=end_obj,
                            budget_amount=budget_amount
                        )
                    except (ValueError, InvalidOperation):
                        continue

                # ✅ Create or update ProjectFinancials with only budget from first period
                if budget_periods:
                    total_direct_budget = sum(Decimal(p["budget"]) for p in budget_periods)
                    financials, _ = ProjectFinancials.objects.get_or_create(project=project)
                    financials.budget_direct_cost = total_direct_budget
                    financials.budget_fa = Decimal("0.00")
                    financials.budget_total = total_direct_budget  # ✅ Fix
                    financials.save()

                project.save()

                ProjectHistory.objects.create(
                    project=project,
                    event_type="Marked as Funded",
                    description=f"Marked as Funded by {request.user.username}."
                )
            else:
                project.status = "Closed"
                project.save()

                ProjectHistory.objects.create(
                    project=project,
                    event_type="Closed After Funding Decision",
                    description=f"Closed after {funded_project.name} was marked as Funded."
                )

        messages.success(request, f"{funded_project.name} marked as Funded. Others marked as Closed.")
        return redirect("opportunity_submissions_view", opportunity_id=opportunity_id)
@login_required
@require_POST
def add_reference(request, fund_id, subcategory_name):
    fund = get_object_or_404(Fund, fund_id=fund_id)
    cost_type = fund.cost_types.filter(name=subcategory_name).first()

    if not cost_type:
        return HttpResponseNotFound("Subcategory not found.")

    ref_num1 = request.POST.get("ref_num1")
    ref_num2 = request.POST.get("ref_num2")
    vendor = request.POST.get("vendor")
    code = request.POST.get("code")
    description = request.POST.get("description")

    # Create reference entry with is_reference flag set to True
    CostEntry.objects.create(
        cost_type=cost_type,
        description=description,
        budget=Decimal("0.00"),
        encumbrance=Decimal("0.00"),
        projected=Decimal("0.00"),
        expense=Decimal("0.00"),
        balance=Decimal("0.00"),
        fund=fund,
        organization=fund.organization,
        ref_num1=ref_num1,
        ref_num2=ref_num2,
        vendor=vendor,
        code=code,
        is_reference=True  # Mark this as a reference
    )

    return redirect("reference_summary", fund_id=fund.fund_id, subcategory_name=subcategory_name)
@login_required
@require_POST
def add_reference_for_fund(request, fund_id):
    fund = get_object_or_404(Fund, fund_id=fund_id)
    subcategory_name = request.POST.get("subcategory_name")

    if not subcategory_name:
        return HttpResponse("Subcategory not provided", status=400)

    cost_type = fund.cost_types.filter(name=subcategory_name).first()
    if not cost_type:
        return HttpResponseNotFound("Subcategory not found.")

    # Get form data
    ref_num1 = request.POST.get("ref_num1")
    ref_num2 = request.POST.get("ref_num2")
    vendor = request.POST.get("vendor")
    code = request.POST.get("code")
    description = request.POST.get("description")

    # Create a new reference CostEntry
    CostEntry.objects.create(
        cost_type=cost_type,
        description=description,
        is_reference=True,
        budget=Decimal("0.00"),
        encumbrance=Decimal("0.00"),
        projected=Decimal("0.00"),
        expense=Decimal("0.00"),
        balance=Decimal("0.00"),
        fund=fund,
        organization=fund.organization,
        ref_num1=ref_num1,
        ref_num2=ref_num2,
        vendor=vendor,
        code=code,
    )

    # 🔥 Only assign existing entries that:
    # - are not references (is_reference=False)
    # - AND currently have no ref_num1
    cost_type.entries.filter(ref_num1__isnull=True, is_reference=False).update(ref_num1=ref_num1)

    return redirect('reference_summary', fund_id=fund.fund_id, subcategory_name=subcategory_name)

@login_required
@user_passes_test(is_admin_or_principal)
def add_routing_users(request, org_id, project_id):
    project = get_object_or_404(Project, id=project_id)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            selected_users = data.get('selected_users', [])
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)

        if not selected_users:
            return JsonResponse({'status': 'success', 'message': 'No routing users added.'})

        users = User.objects.filter(username__in=selected_users)

        if users.exists():
            project.routing_users.add(*users)
            project.save()

            # Log the addition of each routing user
            for user in users:
                ProjectHistory.objects.create(
                    project=project,
                    event_type="Routing User Addition",
                    description=f"Routing user '{user.username}' was added by {request.user.username}."
                )
            print(f"✅ Routing users added to project {project.name} without adding to project users list.")
            return JsonResponse({'status': 'success', 'message': 'Routing users added successfully.'})

        return JsonResponse({'status': 'error', 'message': 'No valid users found.'})

    users = User.objects.exclude(id=request.user.id)
    return render(request, 'admin/add_routing_users.html', {'users': users, 'project': project, 'org_id': org_id})

@login_required
def get_routing_users(request, org_id, project_id):
    try:
        project = Project.objects.get(id=project_id)
        routing_users = project.routing_users.all()
        users_data = [
            {
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
            }
            for user in routing_users
        ]
        return JsonResponse({'status': 'success', 'users': users_data})
    except Project.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Project not found'}, status=404)
@login_required
def make_routing_decision(request, org_id, project_id):
    project = get_object_or_404(Project, id=project_id)

    if request.method == 'POST':
        data = json.loads(request.body)
        decision = data.get('decision', '')
        comments = data.get('comments', '')

        if decision not in ['approve', 'reject']:
            return JsonResponse({'status': 'error', 'message': 'Invalid decision'}, status=400)

        # Create or update the routing decision
        routing_decision, created = RoutingDecision.objects.get_or_create(
            project=project,
            user=request.user,
            defaults={
                'decision': decision,
                'comments': comments,
                'decision_date': timezone.now(),
                'status': 'approved' if decision == 'approve' else 'declined'
            }
        )

        if not created:
            routing_decision.decision = decision
            routing_decision.comments = comments
            routing_decision.decision_date = timezone.now()
            routing_decision.status = 'approved' if decision == 'approve' else 'declined'
            routing_decision.save()

        # Log the routing decision in the project history
        decision_text = "Approved" if decision == "approve" else "Rejected"
        ProjectHistory.objects.create(
            project=project,
            event_type="Routing Decision",
            description=f"{request.user.username} {decision_text} the proposal with comments: '{comments}'"
        )
        print(f"📝 History Logged: {request.user.username} {decision_text} the proposal")

        # Get all routing users and decisions
        routing_users = set(project.routing_users.all())
        all_decisions = RoutingDecision.objects.filter(project=project)
        decision_users = set(dec.user for dec in all_decisions)

        any_rejected = any(dec.decision == 'reject' for dec in all_decisions)
        all_approved = (
            routing_users.issubset(decision_users) and
            all(dec.decision == 'approve' for dec in all_decisions)
        )

        # Set status based on approvals/rejections
        if any_rejected:
            project.status = 'Development'
            ProjectHistory.objects.create(
                project=project,
                event_type="Proposal Sent Back to Development",
                description=f"Proposal sent back to Development due to rejection by {request.user.username}."
            )
            print(f"📝 History Logged: Proposal sent back to Development due to rejection by {request.user.username}")

        elif all_approved:
            SubmittedPackage.objects.filter(project=project, is_draft=False).update(
                approval_status='approved'
            )    
            project.status = 'Approved'  # <--- This line was missing
            project.save()  # <--- This ensures the change is saved
            linked_opportunity = Opportunity.objects.filter(project=project).first()
            agency_name = linked_opportunity.agency_ref.name if linked_opportunity and linked_opportunity.agency_ref else "agency"

            # 📝 Log the routing to agency
            ProjectHistory.objects.create(
                project=project,
                event_type="Proposal Routed for Agency",
                description=f"Approved submission has been marked ready to route to {agency_name}."
            )
            print(f"📝 History Logged: Proposal Approved")

            # ✅ Get the agency from the linked opportunity
            agency = None
            if project.opportunity_set.exists():
                agency = project.opportunity_set.first().agency_ref

            if agency:
                agency_users = User.objects.filter(position_type='agency_user', agency=agency)

                for user in agency_users:
                    if user not in project.routing_users.all():
                        project.routing_users.add(user)
                        ProjectHistory.objects.create(
                            project=project,
                            event_type="Agency User Assigned",
                            description=f"Agency user '{user.username}' was auto-assigned for agency '{agency.name}'."
                        )

                    if not ProjectAccess.objects.filter(user=user, project=project).exists():
                        ProjectAccess.objects.create(
                            user=user,
                            project=project,
                            permission='view',
                            can_edit=False
                        )
                        project.users.add(user)
            else:
                ProjectHistory.objects.create(
                    project=project,
                    event_type="Agency Routing Failed",
                    description="Could not route because agency not found for opportunity."
                )

            # ✅ Finalize submitted package(s)
            SubmittedPackage.objects.filter(project=project, is_draft=True).update(
                is_draft=False,
                finalized_at=timezone.now()
            )
        else:
            project.status = 'Under Review'

        project.save()

        return JsonResponse({'status': 'success', 'message': f'Project {decision}d successfully.'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})

def get_routing_status(request, org_id, project_id):
    try:
        project = Project.objects.get(id=project_id)
        routing_users = project.routing_users.all()  # Get all routing users associated with the project
        
        # Include the project creator in routing users
        if request.user not in routing_users:
            routing_users = list(routing_users) + [request.user]

        decisions = []

        for user in routing_users:
            try:
                decision = RoutingDecision.objects.get(project=project, user=user)
                status = decision.status.capitalize()
                comments = decision.comments or "No comments"
                decision_date = decision.decision_date.strftime("%Y-%m-%d %H:%M:%S") if decision.decision_date else "Not yet decided"
            except RoutingDecision.DoesNotExist:
                status = "Pending"
                comments = "No comments"
                decision_date = "Not yet decided"

            decisions.append({
                "full_name": f"{user.first_name} {user.last_name}",
                "username": user.username,
                "status": status,
                "comments": comments,
                "decision_date": decision_date,
            })

        return JsonResponse({"status": "success", "routing_decisions": decisions})
    except Project.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Project not found"}, status=404)



@login_required
def project_history(request, org_id, project_id):
    history = ProjectHistory.objects.filter(project_id=project_id).order_by('-created_at')
    data = [
        {
            "event_type": record.event_type,
            "description": record.description,
            "created_at": record.created_at.strftime("%B %d, %Y %I:%M %p")
        }
        for record in history
    ]
    return JsonResponse({"status": "success", "history": data})
@login_required
@user_passes_test(is_admin_or_principal)
def submit_to_sponsor(request, org_id, project_id):
    project = get_object_or_404(Project, id=project_id)

    if request.method == "POST":
        project.status = "Submitted to Sponsor"
        project.save()
        finalized_packages = project.submittedpackage_set.filter(is_draft=False)
        for pkg in finalized_packages:
            if pkg.approval_status != "approved":
                pkg.approval_status = "approved"
                pkg.save()
                ProjectHistory.objects.create(
                    project=project,
                    event_type="Auto-Approval on Submit",
                    description=f"Package '{pkg.submission_name}' auto-marked as approved during submission."
                )
        # 📝 Log history
        ProjectHistory.objects.create(
            project=project,
            event_type="Submitted to Sponsor",
            description=f"{request.user.username} submitted the project to the sponsor."
        )

        # ✅ Finalize any existing draft package
        SubmittedPackage.objects.filter(project=project, is_draft=True).update(
            is_draft=False,
            finalized_at=timezone.now(),
            approval_status='approved'
        )

        # ✅ Assign agency users for visibility
        opportunity = project.opportunity_set.first()
        if opportunity and opportunity.agency_ref:
            agency = opportunity.agency_ref
            agency_users = User.objects.filter(position_type='agency_user', agency=agency)

            for user in agency_users:
                if not ProjectAccess.objects.filter(user=user, project=project).exists():
                    ProjectAccess.objects.create(
                        user=user,
                        project=project,
                        permission='view',
                        can_edit=False
                    )
                    project.users.add(user)

                if user not in project.routing_users.all():
                    project.routing_users.add(user)

                ProjectHistory.objects.create(
                    project=project,
                    event_type="Agency User Auto-Assigned",
                    description=f"Agency user '{user.username}' was granted view access on submit."
                )
        else:
            ProjectHistory.objects.create(
                project=project,
                event_type="Agency Assignment Failed",
                description="No agency was found for the linked opportunity during submission."
            )

        messages.success(request, "Project successfully submitted to sponsor!")
        return redirect("specific_project_home", org_id=org_id, project_id=project.id)

    return redirect("specific_project_home", org_id=org_id, project_id=project.id)

@login_required
def add_note(request, org_id, project_id):
    if request.method == "POST":
        project = get_object_or_404(Project, id=project_id)
        content = request.POST.get('content', '').strip()

        if not content:
            return JsonResponse({"status": "error", "message": "Content cannot be empty."}, status=400)

        note = Note.objects.create(
            project=project,
            content=content,
            author=request.user
        )
        return JsonResponse({"status": "success", "message": "Note added successfully!"})

    return JsonResponse({"status": "error", "message": "Invalid request method."}, status=400)

@login_required
def get_notes(request, org_id, project_id):
    project = get_object_or_404(Project, id=project_id)
    notes = project.notes.order_by('-created_at')

    data = [
        {
            "content": note.preview(),
            "full_content": note.content,
            "author": note.author.username,
            "created_at": note.created_at.strftime("%B %d, %Y %I:%M %p")
        }
        for note in notes
    ]
    return JsonResponse({"status": "success", "notes": data})

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