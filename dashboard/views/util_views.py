from django.contrib import messages
from django.contrib import messages as django_messages
from django.contrib.auth.forms import AuthenticationForm
from django.core import serializers
from django.utils.timezone import now
from django.core.paginator import Paginator
import hashlib
from myapp.utils.get_base_template import get_base_template
from django.urls import reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden, HttpResponseRedirect, FileResponse, Http404
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test  # To res
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q, F, Avg, Max, Min, Count
from django.utils import timezone, translation
from ..models import *
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, authenticate
import pandas as pd
from docx import Document
from PIL import Image as PILImage, ImageDraw, ImageFont
from django.core.files.storage import FileSystemStorage  # For file handling and storage if needed
from django.core.files.uploadedfile import InMemoryUploadedFile
from dashboard.views.experiments.data_collection_views import generate_unique_signature

from django.views.decorators.csrf import csrf_exempt
import random
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from random import sample, shuffle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from django.core.files.base import ContentFile
from django.contrib.auth import logout
from django.db import IntegrityError
import logging
from ..forms import *
import json
from django.http import HttpResponseRedirect
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_http_methods
from django.utils.dateparse import parse_datetime
import csv
from ..models import Invitation
from django.core.mail import send_mail
import os
import datetime
from io import BytesIO
from datetime import date

def is_admin_or_principal(user):
    return user.role in ['admin', 'principal_admin']

def is_principal_admin(user):
    return user.role == 'principal_admin'

def get_included_form_types(package):
    return list(package.package_forms.values_list('form_type', flat=True))

@login_required
def task_manager(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    tasks = ProjectTask.objects.filter(assignees=request.user).select_related('assigned_by', 'project')
    user_projects = Project.objects.filter(users=request.user)

    return render(request, 'admin/task_manager.html', {
        'tasks': tasks,
        'org_id': org_id,
        'user_projects': user_projects,
    })
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
def search_submission_users(request, submission_id):
    query = request.GET.get("query", "").strip()
    if not query:
        return JsonResponse({"users": []})

    users = User.objects.filter(
        Q(username__icontains=query) |
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query)
    ).values("username", "first_name", "last_name")[:10]

    return JsonResponse({"users": list(users)})


def search_opportunities(request, org_id, project_id):
    project = get_object_or_404(Project, id=project_id)
    query = request.GET.get("q", "")

    added_ids = ProjectOpportunity.objects.filter(project=project).values_list("opportunity_id", flat=True)
    opportunities = Opportunity.objects.exclude(id__in=added_ids)

    if query:
        opportunities = opportunities.filter(
            Q(title__icontains=query) |
            Q(number__icontains=query) |
            Q(agency_ref__name__icontains=query)
        )

    # Only return the <tbody> as HTML
    return render(request, "partials/opportunity_rows.html", {"opportunities": opportunities})

from django.shortcuts import render, get_object_or_404
from django.db.models import Q
from django.core.paginator import Paginator
from ..models import Project, Opportunity, ProjectOpportunity

def ajax_search_opportunities(request, org_id, project_id):
    project = get_object_or_404(Project, id=project_id)
    search_query = request.GET.get("q", "")
    page_number = request.GET.get("page", 1)

    # Exclude already added opportunities
    added_ids = ProjectOpportunity.objects.filter(project=project).values_list("opportunity_id", flat=True)
    opportunities = Opportunity.objects.exclude(id__in=added_ids)

    if search_query:
        opportunities = opportunities.filter(
            Q(title__icontains=search_query) |
            Q(number__icontains=search_query) |
            Q(agency_ref__name__icontains=search_query)
        )

    opportunities = opportunities.order_by("-close_date")
    paginator = Paginator(opportunities, 10)
    paginated = paginator.get_page(page_number)

    context = {
        "opportunities": paginated,
        "org_id": org_id,
        "project_id": project_id,
        "search_query": search_query,
        "in_modal": True,  # <-- tells template to anchor pagination to modal
    }

    return render(request, "partials/opportunity_table.html", context)

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

        # Add routing users if moving to review
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

        # ✅ Promote draft(s) to submitted when approved
        if new_status == 'Approved':
            # If you only want the latest draft, use .first()
            # latest_draft = project.submittedpackage_set.filter(is_draft=True).order_by('-submission_date').first()
            # drafts_to_promote = [latest_draft] if latest_draft else []

            # If you want to promote ALL drafts for the project, use:
            drafts_to_promote = list(project.submittedpackage_set.filter(is_draft=True))

            for sp in drafts_to_promote:
                sp.is_draft = False
                if not getattr(sp, 'submission_date', None):
                    sp.submission_date = timezone.now()
                if not getattr(sp, 'submission_name', None) or not sp.submission_name.strip():
                    # Fallback naming
                    sp.submission_name = f"{project.name} – {timezone.now().strftime('%Y-%m-%d %H:%M')}"
                sp.save()

            # Now that they are no longer drafts, attach finalized PDFs against them
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

            # iterate over submitted (non-draft) packages
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
        subcategory = request.POST.get("subcategory")

        # Calculate totals
        start_date = datetime.strptime(request.POST.get("start_date"), "%Y-%m-%d").date()
        end_date = datetime.strptime(request.POST.get("end_date"), "%Y-%m-%d").date()
        monthly_amount = Decimal(request.POST.get("monthly_amount") or 0)
        duration_months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1
        total_amount = monthly_amount * duration_months

        # Find or create CostType
        cost_type, _ = CostType.objects.get_or_create(
            fund=fund,
            name=subcategory,
            is_idc=False,
            category="non_personnel"
        )

        # 🧠 Automatically assign ref_num1 if a reference exists
        reference = CostEntry.objects.filter(
            fund=fund,
            cost_type=cost_type,
            is_reference=True
        ).first()

        ref_num1 = reference.ref_num1 if reference else None

        # Create the transaction
        CostEntry.objects.create(
            cost_type=cost_type,
            description=request.POST.get("description"),
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

            ref_num1=ref_num1,
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
                    # 🧠 Get the org's IDC rate
                    submission = SubmittedPackage.objects.filter(project=funded_project, is_draft=False).first()
                    if not submission:
                        messages.error(request, "No finalized submission found for this project.")
                        return redirect("opportunity_submissions_view", opportunity_id=opportunity_id)

                    try:
                        org = Organization.objects.get(id=submission.org_id)
                    except Organization.DoesNotExist:
                        messages.error(request, "Submitting organization not found.")
                        return redirect("opportunity_submissions_view", opportunity_id=opportunity_id)
                    idc_rate = (Decimal(org.idc_rate or 0) / Decimal("100.00")).quantize(Decimal("0.0001"))
                    # 🧮 Calculate IDC per period
                    total_fa = Decimal("0.00")
                    for p in budget_periods:
                        direct = Decimal(p["budget"])
                        fa = (direct * idc_rate).quantize(Decimal("0.01"))
                        total_fa += fa

                    # 💰 Save to financials
                    financials, _ = ProjectFinancials.objects.get_or_create(project=project)
                    financials.budget_direct_cost = total_direct_budget
                    financials.budget_fa = total_fa
                    financials.budget_total = total_direct_budget + total_fa
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
        return HttpResponseBadRequest("Subcategory not provided.")

    # Normalize subcategory name
    subcategory_clean = subcategory_name.strip()

    # Attempt to fetch existing cost type
    cost_type = fund.cost_types.filter(name=subcategory_clean).first()

    # If it doesn't exist yet, create it
    if not cost_type:
        # Determine category based on known mappings (adjust as needed)
        if subcategory_clean in ["Standing Faculty", "Professional Staff", "Employee Benefits"]:
            category = "personnel"
        else:
            category = "non_personnel"

        cost_type = CostType.objects.create(
            fund=fund,
            name=subcategory_clean,
            is_idc=False,
            category=category,
            cost_center_type="direct"  # Or infer if needed
        )

    # Create the reference entry
    CostEntry.objects.create(
        cost_type=cost_type,
        description=request.POST.get("description"),
        is_reference=True,
        budget=Decimal("0.00"),
        encumbrance=Decimal("0.00"),
        projected=Decimal("0.00"),
        expense=Decimal("0.00"),
        balance=Decimal("0.00"),
        fund=fund,
        organization=fund.organization,
        ref_num1=request.POST.get("ref_num1"),
        ref_num2=request.POST.get("ref_num2"),
        vendor=request.POST.get("vendor"),
        code=request.POST.get("code"),
    )

    # Assign unlinked entries to the reference
    cost_type.entries.filter(ref_num1__isnull=True, is_reference=False).update(
        ref_num1=request.POST.get("ref_num1")
    )

    return redirect('reference_summary', fund_id=fund.fund_id, subcategory_name=subcategory_clean)

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