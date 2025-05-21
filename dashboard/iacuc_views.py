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

def is_admin_or_principal(user):
    return user.role in ['admin', 'principal_admin']


@login_required
def iacuc_submission_home(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id)
    organization = submission.user.organization
    committee = getattr(organization, 'iacuc_committee', None)

    is_office_member = IACUCMember.objects.filter(
        user=request.user,
        role='office_member',
        is_active=True,
        committee__organization=organization
    ).exists()
    is_chair = False
    if committee:
        is_chair = IACUCMember.objects.filter(
            user=request.user,
            is_active=True,
            role='chair',
            committee=committee
        ).exists()
    is_iacuc_member = False
    if committee:
        is_iacuc_member = IACUCMember.objects.filter(
            user=request.user,
            is_active=True,
            committee=submission.user.organization.iacuc_committee
        ).exclude(role='office_member').exists()
    iacuc_vets = IACUCMember.objects.filter(
        role='veterinarian',
        is_active=True,
        committee__organization=organization.id
    ).select_related('user')
    has_approved = submission.iacuc_approvals.filter(id=request.user.id).exists()
    iacuc_non_vets = IACUCMember.objects.filter(
        is_active=True,
        committee__organization=organization.id
    ).exclude(role__in=['veterinarian', 'office_member']).select_related('user')
    is_renewal_view = request.GET.get("renewal") == "true"

    return render(request, "admin/iacuc_submission_home.html", {
        "submission": submission,
        "is_office_member": is_office_member,
        "is_iacuc_member": is_iacuc_member,
        "is_chair": is_chair,  # ✅ NEW
        "iacuc_vets": iacuc_vets,
        "iacuc_non_vets": iacuc_non_vets,
        "revision_stages": submission.revision_stages or {},
        "has_approved": has_approved,
        "today": date.today(),  # ✅ Add this line
        "is_renewal_view": is_renewal_view,
    })
@login_required
@require_POST
def iacuc_save_renewal_progress(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id)

    if request.user != submission.principal_investigator:
        return JsonResponse({"status": "error", "message": "Unauthorized"}, status=403)

    submission.renewal_status = request.POST.get("renewal_status")
    submission.progress_report = request.POST.get("progress_report")
    submission.save()

    return redirect("iacuc_submission_home", submission_id=submission.id)

@login_required
@require_POST
def iacuc_status_transition(request, submission_id):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    submission = get_object_or_404(IACUCSubmission, id=submission_id)
    user = request.user
    action = request.POST.get("action")
    note_content = request.POST.get("note", "").strip()

    organization = submission.user.organization
    committee = IACUCCommittee.objects.get(organization=organization)
    is_chair = IACUCMember.objects.filter(
        user=user,
        is_active=True,
        role='chair',
        committee=committee
    ).exists()
    # Restrict to office members
    if action in ["send_back", "send_to_pre_review"]:
        if not IACUCMember.objects.filter(
            user=user,
            role='office_member',
            is_active=True,
            committee=committee
        ).exists():
            return HttpResponseForbidden("Not authorized.")

    if action == "send_back":
        if not note_content:
            return JsonResponse({"status": "error", "message": "Revision note required."}, status=400)
        current_stage = submission.status
        submission.status = "pre_submission"
        revisions = submission.revision_stages or {}
        revisions[current_stage] = "revisions_requested"
        submission.revision_stages = revisions
        submission.save()

        IACUCNote.objects.create(submission=submission, author=user, content=note_content)
        messages.success(request, "Protocol sent back for revisions.")

    elif action == "send_to_pre_review":
        vet_id = request.POST.get("pre_review_veterinarian")
        member_id = request.POST.get("pre_review_member")

        try:
            vet = User.objects.get(id=vet_id)
            member = User.objects.get(id=member_id)
        
        except User.DoesNotExist:
            return JsonResponse({"status": "error", "message": "Reviewer(s) not found."}, status=400)

        if not IACUCMember.objects.filter(user=vet, role='veterinarian', is_active=True, committee=committee).exists():
            return JsonResponse({"status": "error", "message": "Selected veterinarian is not valid."}, status=400)

        if not IACUCMember.objects.filter(user=member, is_active=True, committee=committee).exclude(role='veterinarian').exists():
            return JsonResponse({"status": "error", "message": "Selected member is not valid."}, status=400)

        submission.pre_review_veterinarian = vet
        submission.pre_review_member = member
        submission.status = "pre_review"
        submission.save()

        messages.success(request, "Assigned reviewers and moved to Pre-Review.")

    elif action == "pre_review_revisions":
        if user not in [submission.pre_review_veterinarian, submission.pre_review_member]:
            return HttpResponseForbidden("Not authorized.")

        submission.status = "pre_submission"
        revisions = submission.revision_stages or {}
        revisions["pre_review"] = "revisions_requested"
        submission.revision_stages = revisions
        submission.save()

        IACUCNote.objects.create(submission=submission, author=user, content=f"Pre-reviewer requested revisions: {note_content}")
        messages.success(request, "Sent back for revisions from pre-review.")

    elif action == "pre_review_to_committee":
        if user not in [submission.pre_review_veterinarian, submission.pre_review_member]:
            return HttpResponseForbidden("Not authorized.")

        submission.status = "iacuc_review"
        submission.save()

        IACUCNote.objects.create(submission=submission, author=user, content="Pre-review complete. Sent to full committee review.")
        messages.success(request, "Sent to IACUC Full Committee Review.")

    elif action == "pre_review_approve":
        if user not in [submission.pre_review_veterinarian, submission.pre_review_member]:
            return HttpResponseForbidden("Not authorized.")

        if user == submission.pre_review_veterinarian:
            submission.pre_review_vet_approved = True
        if user == submission.pre_review_member:
            submission.pre_review_member_approved = True

        IACUCNote.objects.create(submission=submission, author=user, content="Pre-reviewer approved protocol.")

        if submission.pre_review_vet_approved and submission.pre_review_member_approved:
            submission.status = "chair_review"  # 🆕 Send to chair designation instead
            IACUCNote.objects.create(
                submission=submission,
                author=user,
                content="Both pre-reviewers approved. Sent to Chair for review designation (DMR or FCR)."
            )
            messages.success(request, "Sent to Chair for review designation.")
        else:
            messages.success(request, "Approval recorded. Awaiting second reviewer.")

        submission.save()
    elif action == "chair_assign_review":
        if not IACUCMember.objects.filter(user=user, role='chair', is_active=True, committee=committee).exists():
            return HttpResponseForbidden("Only the IACUC Chair may assign review type.")

        review_type = request.POST.get("review_type")
        if review_type not in ["dmr", "fcr"]:
            return JsonResponse({"status": "error", "message": "Invalid review type."}, status=400)

        submission.review_type = review_type

        if review_type == "fcr":
            submission.status = "iacuc_review"
            IACUCNote.objects.create(submission=submission, author=user, content="Chair assigned Full Committee Review (FCR).")
            messages.success(request, "Assigned FCR. Sent to IACUC Review.")
        else:  # DMR
            submission.status = "chair_review"  # ⬅️ keep in chair_review while voting
            submission.dmr_approvals.clear()
            submission.dmr_rejected = False
            IACUCNote.objects.create(submission=submission, author=user, content="Chair proposed DMR. Awaiting member confirmation.")
            messages.success(request, "Proposed DMR. Awaiting IACUC member approvals.")
        submission.save()
    elif action == "dmr_decision":
        if not IACUCMember.objects.filter(user=user, is_active=True, committee=committee).exclude(role='office_member').exists():
            return HttpResponseForbidden("Not authorized.")
        if submission.status != "chair_review" or submission.review_type != "dmr":

            return JsonResponse({"status": "error", "message": "DMR decision not allowed at this stage."}, status=400)
        decision = request.POST.get("decision")
        if decision == "approve":
            submission.dmr_approvals.add(user)
            IACUCNote.objects.create(submission=submission, author=user, content="Member approved DMR.")
        elif decision == "reject":
            submission.dmr_rejected = True
            IACUCNote.objects.create(submission=submission, author=user, content="Member rejected DMR.")
        else:
            return JsonResponse({"status": "error", "message": "Invalid decision."}, status=400)

        submission.save()

        # Transition to FCR if any rejection
        if submission.dmr_rejected:
            submission.review_type = "fcr"
            submission.status = "iacuc_review"
            submission.save()
            IACUCNote.objects.create(submission=submission, author=user, content="DMR rejected. Transitioned to Full Committee Review.")    
        else:
            member_ids = IACUCMember.objects.filter(
                is_active=True,
                committee=committee
            ).exclude(role='office_member').values_list("user_id", flat=True)
    
            approved_ids = submission.dmr_approvals.values_list("id", flat=True)

            if set(approved_ids) == set(member_ids):
                submission.status = "dmr_review"
                submission.save()
                IACUCNote.objects.create(submission=submission, author=user, content="All members approved DMR. Moved to Designated Member Review.")

    elif action == "assign_dmr_reviewers":
        if not is_chair:
            return HttpResponseForbidden("Only the chair can assign DMR reviewers.")

        reviewer_ids = request.POST.getlist("reviewers")  # Use checkboxes in the form

        if len(reviewer_ids) != 3:
            return JsonResponse({"status": "error", "message": "Please assign exactly 3 reviewers."}, status=400)

        users = User.objects.filter(id__in=reviewer_ids)

        submission.dmr_reviewers.set(users)
        submission.dmr_reviewer_approvals.clear()  # Just in case
        submission.status = "dmr_review"
        submission.save()

        IACUCNote.objects.create(
            submission=submission,
            author=user,
            content="Chair assigned DMR reviewers: " + ", ".join(u.get_full_name() for u in users)
        )
        messages.success(request, "DMR reviewers assigned. Awaiting their approval.")
    elif action == "dmr_reviewer_approve":
        if user not in submission.dmr_reviewers.all():
            return HttpResponseForbidden("You are not a designated reviewer.")

        submission.dmr_reviewer_approvals.add(user)
        submission.save()

        IACUCNote.objects.create(
            submission=submission,
            author=user,
            content="DMR reviewer approved protocol."
        )

        if set(submission.dmr_reviewers.all()) == set(submission.dmr_reviewer_approvals.all()):
            submission.status = "post_review"
            submission.save()
            IACUCNote.objects.create(
                submission=submission,
                author=user,
                content="All DMR reviewers approved. Moved to Post Review."
            )

        messages.success(request, "Your DMR review has been recorded.")
    elif action == "dmr_reviewer_reject":
        if user not in submission.dmr_reviewers.all():
            return HttpResponseForbidden("You are not a designated reviewer.")

        # Send back for revisions
        submission.status = "pre_submission"
        submission.revision_stages = submission.revision_stages or {}
        submission.revision_stages["dmr_review"] = "revisions_requested"
        submission.save()

        IACUCNote.objects.create(
            submission=submission,
            author=user,
            content="DMR reviewer rejected the protocol. Sent back for revisions."
        )

        messages.success(request, "You rejected the protocol. It has been returned for revisions.")
    elif action == "iacuc_member_approve":
        if not IACUCMember.objects.filter(
            user=user,
            is_active=True,
            committee=committee
        ).exclude(role='office_member').exists():
            return HttpResponseForbidden("Not authorized.")

        if not submission.iacuc_approvals.filter(id=user.id).exists():
            submission.iacuc_approvals.add(user)
            IACUCNote.objects.create(submission=submission, author=user, content="IACUC member approved protocol.")
            submission.save()

        messages.success(request, "Approval recorded.")

    elif action == "move_to_post_review":
        committee = IACUCCommittee.objects.get(organization=submission.user.organization)

        # Chair only
        is_chair = IACUCMember.objects.filter(
            user=user,
            is_active=True,
            role='chair',
            committee=committee
        ).exists()

        if not is_chair:
            return JsonResponse({"status": "error", "message": "Only the IACUC Chair may perform this action."}, status=403)

        required_members = IACUCMember.objects.filter(
            is_active=True,
            committee=committee
        ).exclude(role='office_member').values_list('user_id', flat=True)

        approved_member_ids = submission.iacuc_approvals.values_list('id', flat=True)

        missing_ids = set(required_members) - set(approved_member_ids)

        if missing_ids:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            pending_users = User.objects.filter(id__in=missing_ids)
            pending_names = [u.get_full_name() or u.username for u in pending_users]
            return JsonResponse({
                "status": "error",
                "message": f"Not all required IACUC members have approved. Pending: {', '.join(pending_names)}"
            }, status=400)

        submission.status = "post_review"
        submission.save()

        IACUCNote.objects.create(
            submission=submission,
            author=user,
            content="Chair confirmed all members approved. Protocol moved to Post Review."
        )

        messages.success(request, "Protocol moved to Post Review.")
        return redirect("iacuc_submission_home", submission_id=submission.id)
    elif action == "post_review_approve":
        if not IACUCMember.objects.filter(
            user=user,
            role='office_member',
            is_active=True,
            committee=committee
        ).exists():
            return HttpResponseForbidden("Not authorized.")

        # Parse dates
        try:
            annual_review_date = request.POST.get("annual_review_date")
            triennial_review_date = request.POST.get("triennial_review_date")

            submission.annual_review_date = annual_review_date
            submission.triennial_review_date = triennial_review_date
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)

        submission.status = "approved"
        submission.save()
        members = IACUCMember.objects.filter(
            committee=committee,
            is_active=True
        ).values_list('user', flat=True)

        annual_review_dt = datetime.strptime(annual_review_date, "%Y-%m-%d")
        triennial_review_dt = datetime.strptime(triennial_review_date, "%Y-%m-%d")

        title_base = f"IACUC Review for Protocol #{submission.id}"
        description = f"Review reminder for IACUC Protocol #{submission.id}: {submission.protocol_title}"
        participants = list(IACUCMember.objects.filter(
            committee=committee,
            is_active=True
        ).values_list('user', flat=True)) + [submission.principal_investigator.id]

        users = User.objects.filter(id__in=participants)

        for user_obj in users:
            if annual_review_date:
                CalendarEvent.objects.create(
                    title=f"{title_base} – Annual Review",
                    description=description,
                    user=user_obj,
                    organization=submission.user.organization,
                    start_date=annual_review_dt,
                    end_date=annual_review_dt,
                    all_day=True,
                    color="#FFD700",
                    is_shared=False,
                )
            if triennial_review_date:
                CalendarEvent.objects.create(
                    title=f"{title_base} – Triennial Review",
                    description=description,
                    user=user_obj,
                    organization=submission.user.organization,
                    start_date=triennial_review_dt,
                    end_date=triennial_review_dt,
                    all_day=True,
                    color="#FF6347",
                    is_shared=False,
                )
        IACUCNote.objects.create(submission=submission, author=user, content="Finalized. Annual/Triennial dates added.")
        messages.success(request, "Protocol finalized. Review dates saved and added to calendar.")
    else:
        return JsonResponse({"status": "error", "message": "Invalid action."}, status=400)

    return redirect("iacuc_submission_home", submission_id=submission.id)

@require_POST
@login_required
def add_submission_users(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id)

    try:
        data = json.loads(request.body)
        selected_users = data.get("selected_users", [])
        user_ids = []

        for entry in selected_users:
            username = entry["username"]
            user = User.objects.get(username=username)
            submission.shared_with.add(user)
            user_ids.append(user.id)

        return JsonResponse({"status": "success", "user_ids": user_ids})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)
@login_required
def get_submission_users(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id)
    users = submission.shared_with.all()

    return JsonResponse({
        "users": [
            {
                "username": u.username,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "permission": "edit"  # You can expand this later
            } for u in users
        ]
    })


@require_POST
@login_required
def iacuc_save_personnel_updates(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id)

    user_ids = request.POST.getlist("carry_forward_users")
    selected_users = User.objects.filter(id__in=user_ids)

    # Here you would store selected_users in your database
    # For now we just log and show confirmation
    submission.renewal_personnel.set(selected_users)  # If you add a ManyToMany field like this
    submission.save()

    messages.success(request, "Personnel selections saved.")
    return redirect("iacuc_submission_home", submission_id=submission.id)

@login_required
def meetings_dashboard(request, org_id):
    user = request.user

    # Check if user is IACUC Chair
    is_chair = IACUCMember.objects.filter(
        user=user,
        committee__organization_id=org_id,
        role='chair',
        is_active=True
    ).exists()

    meetings = Meeting.objects.filter(organization_id=org_id, type='iacuc').order_by('-date')


    if not is_chair:
        return render(request, "admin/meetings_dashboard.html", {
            "form": None,
            "meetings": meetings,
            "org_id": org_id,
            "is_chair": False
        })

    iacuc_member_ids = IACUCMember.objects.filter(
        committee__organization_id=org_id,
        is_active=True
    ).values_list('user_id', flat=True)

    if request.method == "POST":
        form = MeetingForm(request.POST)

        if form.is_valid():
            meeting = form.save(commit=False)
            meeting.organization_id = org_id
            meeting.created_by = request.user
            meeting.save()

            # ✅ Manually handle attendees
            attendee_ids = [int(id.strip()) for id in request.POST.get('attendees', '').split(',') if id.strip().isdigit()]
            if not attendee_ids:
                messages.error(request, "Please select at least one attendee.")
                return redirect('meetings_dashboard', org_id=org_id)

            attendees = User.objects.filter(id__in=attendee_ids)
            meeting.attendees.set(attendees)

            submissions = IACUCSubmission.objects.filter(
                user__organization_id=org_id,
                status="iacuc_review"
            )
            for submission in submissions:
                MeetingItem.objects.create(meeting=meeting, submission=submission)

            return redirect('meetings_dashboard', org_id=org_id)
    else:
        form = MeetingForm()

    return render(request, "admin/meetings_dashboard.html", {
        "form": form,
        "meetings": meetings,
        "org_id": org_id,
        "is_chair": True
    })

@login_required
def search_iacuc_members(request):
    query = request.GET.get("query", "")
    org_id = request.user.organization_id
    members = IACUCMember.objects.filter(
        committee__organization__id=org_id,
        is_active=True,
        user__first_name__icontains=query
    ).select_related("user")

    results = [{
        "id": member.user.id,
        "name": member.user.get_full_name() or member.user.username,
        "role": member.get_role_display()
    } for member in members]

    return JsonResponse({"users": results})
@login_required
def meeting_detail(request, meeting_id):
    meeting = get_object_or_404(Meeting, id=meeting_id)
    items = meeting.items.select_related('submission_iacuc')
    committee = getattr(meeting.organization, "iacuc_committee", None)
    user_is_chair = False
    if committee:
        user_is_chair = IACUCMember.objects.filter(
            user=request.user,
            committee=committee,
            is_active=True,
            role='chair'
        ).exists()
    if request.method == "POST":
        form = MeetingItemForm(request.POST)
        if user_is_chair and form.is_valid():
            item = form.save(commit=False)
            item.meeting = meeting
            item.save()
            return redirect('meeting_detail', meeting_id=meeting.id)
    else:
        form = MeetingItemForm()
    return render(request, "admin/meeting_detail.html", {
        "meeting": meeting,
        "items": items,
        "form": form,
        "user_is_chair": user_is_chair,
    })
@require_POST
@login_required
def iacuc_save_adverse_events(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id)
    submission.adverse_events = request.POST.get("adverse_events", "").strip()
    submission.save()
    messages.success(request, "Adverse events updated.")
    return redirect("iacuc_submission_home", submission_id=submission.id)

@require_POST
@login_required
def iacuc_save_alt_animal_use(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id)
    submission.alternative_to_animal_use = request.POST.get("alternative_to_animal_use", "").strip()
    submission.save()
    messages.success(request, "Alternative to Animal Use response saved.")
    return redirect("iacuc_submission_home", submission_id=submission.id)

@require_POST
@login_required
def iacuc_save_alt_procedures(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id)
    submission.alt_to_procedures = request.POST.get("alt_to_procedures", "").strip()
    submission.save()
    messages.success(request, "Alternatives to Procedures response saved.")
    return redirect("iacuc_submission_home", submission_id=submission.id)
@require_POST
@login_required
def iacuc_save_duplication(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id)
    submission.duplication_prevention = request.POST.get("duplication_prevention", "").strip()
    submission.save()
    messages.success(request, "Duplication prevention response saved.")
    return redirect("iacuc_submission_home", submission_id=submission.id)
@require_POST
@login_required
def iacuc_save_future_use(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id)
    submission.future_use_plan = request.POST.get("future_use_plan", "").strip()
    submission.future_use_description = request.POST.get("future_use_description", "").strip()
    submission.save()
    messages.success(request, "Future Use information saved.")
    return redirect("iacuc_submission_home", submission.id)

def evaluate_meeting_item(item):
    submission = item.submission
    votes = MeetingVote.objects.filter(item=item)

    approve_count = votes.filter(vote="approve").count()
    reject_count = votes.filter(vote="reject").count()
    abstain_count = votes.filter(vote="abstain").count()

    total_non_abstain = approve_count + reject_count

    if total_non_abstain == 0:
        return  # Cannot decide without any valid votes

    # Majority approval check (more than half of non-abstain votes)
    if approve_count > total_non_abstain / 2:
        submission.status = "post_review"
        submission.save()
        IACUCNote.objects.create(
            submission=submission,
            author=item.meeting.created_by,
            content="Protocol approved by majority vote in meeting. Moved to Post Review."
        )
    elif reject_count >= total_non_abstain / 2:
        submission.status = "pre_submission"
        submission.revision_stages = submission.revision_stages or {}
        submission.revision_stages["iacuc_review"] = "revisions_requested"
        submission.save()
        IACUCNote.objects.create(
            submission=submission,
            author=item.meeting.created_by,
            content="Protocol rejected by majority vote. Sent back for revisions."
        )

@login_required
@require_http_methods(["GET", "POST"])
def iacuc_section_notes(request, submission_id, section_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id)
    
    if request.method == "POST":
        content = request.POST.get("content", "").strip()
        if content:
            IACUCSectionNote.objects.create(
                submission=submission,
                author=request.user,
                section_id=section_id,
                content=content
            )
            return JsonResponse({"status": "success"})
        return JsonResponse({"status": "error", "message": "Content required"}, status=400)

    notes = submission.section_notes.filter(section_id=section_id).select_related("author").order_by("-created_at")
    return JsonResponse({
        "notes": [
            {
                "author": note.author.get_full_name() or note.author.username,
                "created_at": note.created_at.strftime("%Y-%m-%d %H:%M"),
                "content": note.content
            }
            for note in notes
        ]
    })
@login_required
def iacuc_dashboard(request, org_id):
    user = request.user
    # Status mappings
    STATUS_CATEGORIES = {
        'draft_protocols': ['draft'],
        'pre_submission_protocols': ['pre_submission'],
        'in_review_protocols': [
            'admin_review', 'pre_review', 'chair_review', 'dmr_review',
            'iacuc_review', 'post_review'
        ],
        'approved_protocols': ['approved'],
    }

    # Role checks
    is_office_member = IACUCMember.objects.filter(
        user=user,
        role='office_member',
        is_active=True,
        committee__organization_id=org_id
    ).exists()

    is_iacuc_member = IACUCMember.objects.filter(
        user=user,
        is_active=True,
        committee__organization_id=org_id
    ).exclude(role='office_member').exists()

    is_chair = IACUCMember.objects.filter(
        user=user,
        role='chair',
        is_active=True,
        committee__organization_id=org_id
    ).exists()

    protocols_by_status = {}

    for key, status_list in STATUS_CATEGORIES.items():
        base_queryset = IACUCSubmission.objects.filter(
            user__organization_id=org_id,
            status__in=status_list
        )

        if is_office_member:
            protocols_by_status[key] = base_queryset.distinct()
        else:
            filters = (
                Q(user=user) |
                Q(shared_with=user) |
                Q(pre_review_veterinarian=user) |
                Q(pre_review_member=user)
            )

            if 'iacuc_review' in status_list and is_iacuc_member:
                filters |= Q(status="iacuc_review") | Q(status="iacuc_review", review_type="dmr")

            if 'chair_review' in status_list and (is_chair or is_iacuc_member):
                filters |= Q(status="chair_review")
            if 'dmr_review' in status_list and is_iacuc_member:
                filters |= Q(dmr_reviewers=user)

            protocols_by_status[key] = base_queryset.filter(filters).distinct()

    # Handle new protocol submission
    if request.method == 'POST':
        form = IACUCProtocolForm(request.POST, request.FILES)
        if form.is_valid():
            protocol = form.save(commit=False)
            protocol.user = user
            protocol.status = 'draft'
            protocol.save()
            return redirect('iacuc_question', protocol_id=protocol.id)
    else:
        form = IACUCProtocolForm()

    # Define simplified tabs
    tabs = [
        ("Draft", "draft_protocols"),
        ("Pre-Submission", "pre_submission_protocols"),
        ("In Review", "in_review_protocols"),
        ("Approved", "approved_protocols"),
    ]

    context = {
        'form': form,
        'org_id': org_id,
        'protocols_by_status': protocols_by_status,
        'tabs': tabs,
    }

    return render(request, 'admin/iacuc_dashboard.html', context)

def evaluate_irb_meeting_item(item):
    submission = item.submission_irb
    if not submission or submission.status != "IRB Review":
        return

    votes = item.meetingvote_set.all()
    total_votes = votes.count()
    approvals = votes.filter(vote="approve").count()
    rejections = votes.filter(vote="reject").count()

    quorum_required = item.meeting.attendees.filter(
        irb_roles__committee__organization=item.meeting.organization,
        irb_roles__is_active=True,
    ).distinct().count()

    if total_votes < quorum_required:
        # Not enough for quorum
        return

    if approvals > rejections:
        submission.status = "Post IRB Review"
        IRBNote.objects.create(
            submission=submission,
            author=None,
            content="Board approved protocol by majority vote.",
        )
    else:
        submission.status = "IRB Review Revision"
        IRBNote.objects.create(
            submission=submission,
            author=None,
            content="Board rejected protocol. Revisions required.",
        )
    submission.save()

@login_required
@require_POST
def submit_vote(request, item_id):
    item = get_object_or_404(MeetingItem, id=item_id)

    if request.user not in item.meeting.attendees.all():
        return HttpResponseForbidden("Not an attendee")

    vote_value = request.POST.get("vote")
    if vote_value not in ["approve", "reject", "abstain"]:
        return JsonResponse({"status": "error", "message": "Invalid vote"}, status=400)

    MeetingVote.objects.update_or_create(
        user=request.user,
        item=item,
        defaults={"vote": vote_value}
    )

    if item.submission_irb:
        evaluate_irb_meeting_item(item)
    elif item.submission_iacuc:
        evaluate_meeting_item(item)

    messages.success(request, "Your vote has been recorded.")

    # ✅ Safer redirect using meeting type
    if item.meeting.type == "irb":
        return redirect("irb_meeting_detail", meeting_id=item.meeting.id)
    else:
        return redirect("meeting_detail", meeting_id=item.meeting.id)

@login_required
def iacuc_question(request, protocol_id):
    protocol = get_object_or_404(IACUCSubmission, id=protocol_id, user=request.user)

    if request.method == 'POST':
        answer = request.POST.get('involves_vertebrate_animals')
        if answer in ['yes', 'no']:
            protocol.involves_vertebrate_animals = (answer == 'yes')
            protocol.save()
            return redirect('iacuc_submission_details', submission_id=protocol.id)
    return render(request, 'admin/iacuc_question.html', {'protocol': protocol})
@login_required
def iacuc_submission_details(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id, user=request.user)
    SpeciesFormSet = modelformset_factory(IACUCProtocolSpecies, form=IACUCProtocolSpeciesForm, extra=0, can_delete=True)

    if request.method == 'POST':
        form = IACUCSubmissionDetailsForm(request.POST, request.FILES, instance=submission)
        species_formset = SpeciesFormSet(request.POST, queryset=submission.species_entries.all(), prefix='species')

        if form.is_valid() and species_formset.is_valid():
            form.save()

            species_forms = species_formset.save(commit=False)
            for species in species_forms:
                species.submission = submission
                species.save()

            for deleted in species_formset.deleted_objects:
                deleted.delete()

            # ⏩ Redirect to IACUC Fill Out page instead of dashboard
            return redirect('iacuc_fill_out', submission_id=submission.id)

    else:
        form = IACUCSubmissionDetailsForm(instance=submission)
        species_formset = SpeciesFormSet(
            queryset=submission.species_entries.all(),
            prefix='species'
        )

    return render(request, 'admin/iacuc_submission_details.html', {
        'form': form,
        'species_formset': species_formset,
        'submission': submission 
    })

@login_required
def iacuc_save_overview(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id, user=request.user)

    if request.method == 'POST':
        submission.protocol_title = request.POST.get('title')
        submission.lay_abstract = request.POST.get('lay_abstract')
        submission.benefits = request.POST.get('benefits')
        submission.experimental_summary = request.POST.get('summary')
        submission.save()
        messages.success(request, "Protocol Overview saved.")
    return redirect('iacuc_fill_out', submission_id=submission.id)

@login_required
def iacuc_update_field(request, submission_id, field_name):
    submission = get_object_or_404(IACUCSubmission, id=submission_id, user=request.user)

    if request.method == 'POST' and field_name in ['protocol_title', 'lay_abstract', 'benefits', 'experimental_summary']:
        setattr(submission, field_name, request.POST.get('value', ''))
        submission.save()
        messages.success(request, f"{field_name.replace('_', ' ').capitalize()} updated.")
    
    return redirect('iacuc_fill_out', submission_id=submission.id)

@login_required
def iacuc_fill_out(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id)
    # Authorization: user must be owner, assigned, shared, or IACUC member
    is_authorized = (
        submission.user == request.user or
        request.user in submission.shared_with.all() or
        request.user == submission.pre_review_veterinarian or
        request.user == submission.pre_review_member or
        submission.iacuc_approvals.filter(id=request.user.id).exists() or
        IACUCMember.objects.filter(
            user=request.user,
            is_active=True,
            committee__organization=submission.user.organization
        ).exists()
    )

    if not is_authorized:
        return HttpResponseForbidden("You do not have permission to access this submission.")
    # ✅ Move this right after fetching submission, before ANY other logic
    if request.method == "POST" and "submit_for_review" in request.POST:
        print("Submitting protocol for pre-review!")
        submission.status = "pre_submission"
        submission.save()
        return redirect("iacuc_dashboard", org_id=submission.user.organization_id)    
        # Federal
    funding_sources = IACUCFundingSource.objects.filter(submission=submission)
    funding_form = IACUCFundingSourceForm(request.POST or None)
    if request.method == "POST" and 'add_federal_funding' in request.POST:
        if funding_form.is_valid():
            instance = funding_form.save(commit=False)
            instance.submission = submission
            instance.save()
            return redirect(f"{request.path}?section=federal_funding")
            

    # Internal
    internal_sources = IACUCInternalFundingSource.objects.filter(submission=submission)
    internal_form = IACUCInternalFundingSourceForm(request.POST or None)
    if request.method == "POST" and 'add_internal_funding' in request.POST:
        if internal_form.is_valid():
            instance = internal_form.save(commit=False)
            instance.submission = submission
            instance.save()
  
            return redirect(f"{request.path}?section=internal_federal_funding")

           
    private_sources = IACUCPrivateFundingSource.objects.filter(submission=submission)
    private_form = IACUCPrivateFundingSourceForm(request.POST or None)
    if request.method == "POST" and 'add_private_funding' in request.POST:
        if private_form.is_valid():
            instance = private_form.save(commit=False)
            instance.submission = submission
            instance.save()
            return redirect(f"{request.path}?section=private_commercial_funding")
       
    tissue_form = TissueSourceForm(request.POST or None, instance=submission)
    if request.method == "POST" and 'save_tissue_info' in request.POST:
        if tissue_form.is_valid():
            tissue_form.save()
            return redirect(f"{request.path}?section=uses_outside_tissues")
    external_collab_form = ExternalCollaborationForm(request.POST or None)
    external_collaborations = ExternalCollaboration.objects.filter(submission=submission)
    if request.method == "POST" and 'add_external_collab' in request.POST:
        if external_collab_form.is_valid():
            instance = external_collab_form.save(commit=False)
        instance.submission = submission
        instance.save()
        return redirect(f"{request.path}?section=external_collaboration")
    off_campus_form = OffCampusWorkForm(request.POST or None)
    off_campus_entries = OffCampusWork.objects.filter(submission=submission)

    if request.method == "POST" and 'add_off_campus' in request.POST:
        if off_campus_form.is_valid():
            instance = off_campus_form.save(commit=False)
            instance.submission = submission
            instance.save()
            return redirect(f"{request.path}?section=off_campus_live_animal_work")
    housing_instance, _ = OutsideHousing.objects.get_or_create(submission=submission)
    housing_form = OutsideHousingForm(request.POST or None, instance=housing_instance)

    if request.method == "POST" and 'save_outside_housing' in request.POST:
        if housing_form.is_valid():
            housing_form.save()
            return redirect(f"{request.path}?section=housing_outside_facility_12hr")
    transport_instance, _ = PublicTransportUse.objects.get_or_create(submission=submission)
    transport_form = PublicTransportForm(request.POST or None, instance=transport_instance)

    if request.method == "POST" and 'save_public_transport' in request.POST:
        if transport_form.is_valid():
            transport_form.save()
            return redirect(f"{request.path}?section=public_area_transport")

    try:
        field_study_details = FieldStudyDetails.objects.get(submission=submission)
    except FieldStudyDetails.DoesNotExist:
        field_study_details = None

    field_study_form = FieldStudyDetailsForm(request.POST or None, instance=field_study_details)

    if request.method == "POST" and "field_study_submit" in request.POST:
        if field_study_form.is_valid():
            instance = field_study_form.save(commit=False)
            instance.submission = submission
            instance.save()
            return redirect(f"{request.path}?section=field_studies")
    try:
        wildlife_capture_instance = WildlifeCapture.objects.get(submission=submission)
    except WildlifeCapture.DoesNotExist:
        wildlife_capture_instance = None

    wildlife_capture_form = WildlifeCaptureForm(request.POST or None, instance=wildlife_capture_instance)

    if request.method == "POST" and "wildlife_capture_submit" in request.POST:
        if wildlife_capture_form.is_valid():
            instance = wildlife_capture_form.save(commit=False)
            instance.submission = submission
            instance.save()
            return redirect(f"{request.path}?section=field_studies")
    try:
        field_safety = FieldSafetyPrecautions.objects.get(submission=submission)
    except FieldSafetyPrecautions.DoesNotExist:
        field_safety = None

    safety_form = FieldSafetyPrecautionsForm(request.POST or None, instance=field_safety)

    if request.method == "POST" and "save_field_safety" in request.POST:
        if safety_form.is_valid():
            instance = safety_form.save(commit=False)
            instance.submission = submission
            instance.save()
            return redirect(f"{request.path}?section=field_studies")
    try:
        field_permits = FieldStudyPermit.objects.get(submission=submission)
    except FieldStudyPermit.DoesNotExist:
        field_permits = None

    permit_form = FieldStudyPermitForm(request.POST or None, instance=field_permits)

    if request.method == "POST" and "save_field_permits" in request.POST:
        if permit_form.is_valid():
            instance = permit_form.save(commit=False)
            instance.submission = submission
            instance.save()
            return redirect(f"{request.path}?section=field_studies")
    vetdrug_forms = {}
    vetdrug_lists = {}

    for species in submission.species_entries.all():
        if species.vet_drugs:
            vetdrug_forms[species.species_name] = VetDrugForm(request.POST or None, prefix=slugify(species.species_name))
            vetdrug_lists[species.species_name] = SpeciesVetDrug.objects.filter(submission=submission, species=species)
    for species_name, form in vetdrug_forms.items():
        if f"add_vetdrug_{slugify(species_name)}" in request.POST:
            if form.is_valid():
                instance = form.save(commit=False)
                instance.submission = submission
                instance.species = IACUCProtocolSpecies.objects.get(submission=submission, species_name=species_name)
                instance.save()
                return redirect(f"{request.path}?section={slugify(species_name)}_vet-drugs")
    hazard_forms = {}
    hazard_lists = {}
    
    for species in submission.species_entries.all():
        hazard_lists[species.species_name] = []

        if species.vet_drugs:
            form = HazardousAgentForm(request.POST or None, prefix=slugify(species.species_name))
            hazard_forms[species.species_name] = form
            hazard_lists[species.species_name] = HazardousAgent.objects.filter(submission=submission, species=species)

            if f"add_hazard_{slugify(species.species_name)}" in request.POST:
                if form.is_valid():
                    instance = form.save(commit=False)
                    instance.submission = submission
                    instance.species = species
                    instance.save()
                    return redirect(f"{request.path}?section={slugify(species.species_name)}_hazards")
    euthanasia_forms = {
        "method": {},
        "numbers": {},
        "pain": {},
        "reduce": {},
        "refine": {},
        "replace": {},
        "adverse": {},
        "exemptions": {}
    }

    for species in submission.species_entries.all():
        if not species.euthanize:
            continue

        instance, _ = SpeciesEuthanasia.objects.get_or_create(submission=submission, species=species)
        prefix = slugify(species.species_name)

        euthanasia_forms["method"][species.species_name] = EuthanasiaMethodForm(
            request.POST or None, instance=instance, prefix=f"{prefix}-method"
        )
        euthanasia_forms["numbers"][species.species_name] = EuthanasiaNumbersForm(
            request.POST or None, instance=instance, prefix=f"{prefix}-numbers"
        )
        euthanasia_forms["pain"][species.species_name] = EuthanasiaPainForm(
            request.POST or None, instance=instance, prefix=f"{prefix}-pain"
        )
        euthanasia_forms["reduce"][species.species_name] = ReduceForm(request.POST or None, instance=instance, prefix=f"{prefix}-reduce")
        euthanasia_forms["refine"][species.species_name] = RefineForm(request.POST or None, instance=instance, prefix=f"{prefix}-refine")
        euthanasia_forms["replace"][species.species_name] = ReplaceForm(request.POST or None, instance=instance, prefix=f"{prefix}-replace")
        euthanasia_forms["adverse"][species.species_name] = EuthanasiaAdverseForm(
            request.POST or None, instance=instance, prefix=f"{prefix}-adverse"
        )
        euthanasia_forms["exemptions"][species.species_name] = EuthanasiaExemptionsForm(
            request.POST or None, instance=instance, prefix=f"{prefix}-exempt"
        )
    for species_name in euthanasia_forms["method"]:
        prefix = slugify(species_name)

        if f"save_euthanasia_method_{prefix}" in request.POST:
            form = euthanasia_forms["method"][species_name]
            if form.is_valid():
                obj = form.save(commit=False)
                obj.submission = submission
                obj.species = IACUCProtocolSpecies.objects.get(submission=submission, species_name=species_name)
                obj.save()
                return redirect(f"{request.path}?section={prefix}_euthanasia_method")

        if f"save_euthanasia_numbers_{prefix}" in request.POST:
            form = euthanasia_forms["numbers"][species_name]
            if form.is_valid():
                obj = form.save(commit=False)
                obj.submission = submission
                obj.species = IACUCProtocolSpecies.objects.get(submission=submission, species_name=species_name)
                obj.save()
                return redirect(f"{request.path}?section={prefix}_euthanasia_numbers")

        if f"save_euthanasia_pain_{prefix}" in request.POST:
            form = euthanasia_forms["pain"][species_name]
            if form.is_valid():
                obj = form.save(commit=False)
                obj.submission = submission
                obj.species = IACUCProtocolSpecies.objects.get(submission=submission, species_name=species_name)
                obj.save()
                return redirect(f"{request.path}?section={prefix}_euthanasia_pain")

        if f"save_reduce_{prefix}" in request.POST:
            form = euthanasia_forms["reduce"][species_name]
            if form.is_valid():
                instance = form.save(commit=False)
                instance.submission = submission
                instance.species = IACUCProtocolSpecies.objects.get(submission=submission, species_name=species_name)
                instance.save()
                return redirect(f"{request.path}?section={prefix}_reduce")
        if f"save_refine_{prefix}" in request.POST:
            form = euthanasia_forms["refine"][species_name]
            if form.is_valid():
                instance = form.save(commit=False)
                instance.submission = submission
                instance.species = IACUCProtocolSpecies.objects.get(submission=submission, species_name=species_name)
                instance.save()
                return redirect(f"{request.path}?section={prefix}_refine")
        if f"save_replace_{prefix}" in request.POST:
            form = euthanasia_forms["replace"][species_name]
            if form.is_valid():
                instance = form.save(commit=False)
                instance.submission = submission
                instance.species = IACUCProtocolSpecies.objects.get(submission=submission, species_name=species_name)
                instance.save()
                return redirect(f"{request.path}?section={prefix}_replace")
        if f"save_euthanasia_adverse_{prefix}" in request.POST:
            form = euthanasia_forms["adverse"][species_name]
            if form.is_valid():
                obj = form.save(commit=False)
                obj.submission = submission
                obj.species = IACUCProtocolSpecies.objects.get(submission=submission, species_name=species_name)
                obj.save()
                return redirect(f"{request.path}?section={prefix}_adverse")

        if f"save_euthanasia_exemptions_{prefix}" in request.POST:
            form = euthanasia_forms["exemptions"][species_name]
            if form.is_valid():
                obj = form.save(commit=False)
                obj.submission = submission
                obj.species = IACUCProtocolSpecies.objects.get(submission=submission, species_name=species_name)
                obj.save()
                return redirect(f"{request.path}?section={prefix}_exemptions")
    species_sidebar = {}
    breeding_forms = {}
    for species in submission.species_entries.all():
        if species.breeding:
            form_instance, _ = SpeciesBreeding.objects.get_or_create(submission=submission, species=species)
            breeding_forms[species.species_name] = BreedingForm(request.POST or None, instance=form_instance)
    for entry in submission.species_entries.all():

        if entry.breeding:
            form_instance, _ = SpeciesBreeding.objects.get_or_create(submission=submission, species=entry)
            breeding_forms[entry.species_name] = BreedingForm(request.POST or None, instance=form_instance)
        activities = []
        activities.extend(["Species Info", "Justification", "Use Location", "Strains"])
        if entry.breeding:
            activities.append("Breeding")
        if entry.procedures:
            activities.append("Procedures")
        if entry.restraint:
            activities.append("Restraint")
        if entry.surgery:
            activities.append("Surgery")
            activities.append("MSS") 
        if entry.vet_drugs:
            activities.append("Vet Drugs")
            activities.append("Hazards")
        if entry.test_agents:
            activities.append("Test Agents")
        if entry.euthanize:
            activities.append("Euthanize")
        if activities:
            species_sidebar[entry.species_name] = activities
    species_activity_templates = {}
    for species, activities in species_sidebar.items():
        species_activity_templates[species] = {}
        for activity in activities:
            slug = slugify(activity)
            species_activity_templates[species][activity] = f"partials/iacuc_species_sections/{slug}.html"
    for species_name, form in breeding_forms.items():
        if f"save_breeding_{slugify(species_name)}" in request.POST:
            if form.is_valid():
                instance = form.save(commit=False)  # ✅ Save first
                instance.submission = submission
                instance.species = IACUCProtocolSpecies.objects.get(submission=submission, species_name=species_name)
                instance.save()
                return redirect(f"{request.path}?section={slugify(species_name)}_breeding")

    # Build species activity structure
    procedure_forms = {}
    for species in submission.species_entries.all():
        if species.procedures:
            form_instance, _ = SpeciesProcedure.objects.get_or_create(submission=submission, species=species)
            procedure_forms[species.species_name] = ProcedureForm(request.POST or None, instance=form_instance)
    for species_name, form in procedure_forms.items():
        if f"save_procedure_{slugify(species_name)}" in request.POST:
            if form.is_valid():
                instance = form.save(commit=False)
                instance.submission = submission
                instance.species = IACUCProtocolSpecies.objects.get(submission=submission, species_name=species_name)
                instance.save()
                return redirect(f"{request.path}?section={slugify(species_name)}_procedures")
    restraint_forms = {}
    for species in submission.species_entries.all():
        if species.restraint:
            form_instance, _ = SpeciesRestraint.objects.get_or_create(submission=submission, species=species)
            restraint_forms[species.species_name] = RestraintForm(request.POST or None, instance=form_instance)

    for species_name, form in restraint_forms.items():
        if f"save_restraint_{slugify(species_name)}" in request.POST:
            if form.is_valid():
                instance = form.save(commit=False)
                instance.submission = submission
                instance.species = IACUCProtocolSpecies.objects.get(submission=submission, species_name=species_name)
                instance.save()
                
                return redirect(f"{request.path}?section={slugify(species_name)}_restraint")
    surgery_forms = {}  # Holds all subforms for each species
    for species in submission.species_entries.all():
        if not species.surgery:
            continue

        form_instance, _ = SpeciesSurgery.objects.get_or_create(submission=submission, species=species)
        species_key = species.species_name

        # Prepare all 4 sub-forms (bound only if POST)
        info_form = SurgeryInfoForm(request.POST if f"save_surgery_info_{slugify(species_key)}" in request.POST else None, instance=form_instance)
        preop_form = SurgeryPreOpForm(request.POST if f"save_surgery_preop_{slugify(species_key)}" in request.POST else None, instance=form_instance)
        postop_form = SurgeryPostOpForm(request.POST if f"save_surgery_postop_{slugify(species_key)}" in request.POST else None, instance=form_instance)
        location_form = SurgeryLocationForm(request.POST if f"save_surgery_location_{slugify(species_key)}" in request.POST else None, instance=form_instance)

        # Save the appropriate form
        # Save the appropriate form
        if request.method == "POST":
            if f"save_surgery_info_{slugify(species_key)}" in request.POST and info_form.is_valid():
                info_form.save()
                return redirect(f"{request.path}?section={slugify(species_key)}_surgery")

            if f"save_surgery_preop_{slugify(species_key)}" in request.POST and preop_form.is_valid():
                preop_form.save()
                return redirect(f"{request.path}?section={slugify(species_key)}_surgery")

            if f"save_surgery_postop_{slugify(species_key)}" in request.POST and postop_form.is_valid():
                postop_form.save()
                return redirect(f"{request.path}?section={slugify(species_key)}_surgery")

            if f"save_surgery_location_{slugify(species_key)}" in request.POST and location_form.is_valid():
                location_form.save()
                return redirect(f"{request.path}?section={slugify(species_key)}_surgery")
        # Bundle all forms into one dict entry for the species
        surgery_forms[species_key] = {
            "info": info_form,
            "preop": preop_form,
            "postop": postop_form,
            "location": location_form
        }
    mss_forms = {}
    for species in submission.species_entries.all():
        if species.surgery:
            form_instance, _ = SpeciesMSS.objects.get_or_create(submission=submission, species=species)
            mss_forms[species.species_name] = MSSForm(request.POST or None, instance=form_instance)
    for species_name, form in mss_forms.items():
        if f"save_mss_{slugify(species_name)}" in request.POST:
            if form.is_valid():
                instance = form.save(commit=False)
                instance.submission = submission
                instance.species = IACUCProtocolSpecies.objects.get(submission=submission, species_name=species_name)
                instance.save()
                return redirect(f"{request.path}?section={slugify(species_name)}_mss")
    try:
        database_search_instance = DatabaseSearch.objects.get(submission=submission)
    except DatabaseSearch.DoesNotExist:
        database_search_instance = None

    database_search_form = DatabaseSearchForm(request.POST or None, instance=database_search_instance)
   

    if request.method == "POST" and "save_database_search" in request.POST:
        if database_search_form.is_valid():
            instance = database_search_form.save(commit=False)
            instance.submission = submission
            instance.save()
            return redirect("iacuc_fill_out", submission_id=submission.id)
    # Personnel List
    personnel_form = PersonnelForm(request.POST or None)
    personnel_entries = IACUCPersonnel.objects.filter(submission=submission)
    if request.method == "POST" and "add_personnel" in request.POST:
        if personnel_form.is_valid():
            instance = personnel_form.save(commit=False)
            instance.submission = submission
            instance.save()
            return redirect(f"{request.path}?section=personnel_list")
    species_info_forms = {}
    for species in submission.species_entries.all():
        form = SpeciesInfoForm(request.POST or None, instance=species, prefix=slugify(species.species_name))
        species_info_forms[species.species_name] = form

        if f"save_species_info_{slugify(species.species_name)}" in request.POST:
            if form.is_valid():
                form.save()
                return redirect(f"{request.path}?section={slugify(species.species_name)}_species-info")
    justification_forms = {}
    for species in submission.species_entries.all():
        form = SpeciesJustificationForm(request.POST or None, instance=species, prefix=slugify(species.species_name))
        justification_forms[species.species_name] = form

        if f"save_justification_{slugify(species.species_name)}" in request.POST:
            if form.is_valid():
                form.save()
                return redirect(f"{request.path}?section={slugify(species.species_name)}_justification")
    
    use_location_forms = {}
    use_location_entries = {}

    for species in submission.species_entries.all():
        form = SpeciesUseLocationForm(request.POST or None, prefix=slugify(species.species_name))
        use_location_forms[species.species_name] = form
        use_location_entries[species.species_name] = SpeciesUseLocation.objects.filter(submission=submission, species=species)

        if f"save_use_location_{slugify(species.species_name)}" in request.POST:
            if form.is_valid():
                new_instance = form.save(commit=False)
                new_instance.submission = submission
                new_instance.species = species
                new_instance.save()
                return redirect(f"{request.path}?section={slugify(species.species_name)}_use-location")
    strain_forms = {}   
    strain_entries = {}

    for species in submission.species_entries.all():
        key = species.species_name
        form = SpeciesStrainForm(request.POST or None, prefix=slugify(key))
        strain_forms[key] = form
        strain_entries[key] = SpeciesStrain.objects.filter(submission=submission, species=species)

        if f"save_strain_{slugify(key)}" in request.POST:
            if form.is_valid():
                instance = form.save(commit=False)
                instance.submission = submission
                instance.species = species
                instance.save()
                return redirect(f"{request.path}?section={slugify(key)}_strains")
    personnel_form = FullPersonnelForm(request.POST or None)
    if request.method == "POST" and "add_personnel" in request.POST:
        if personnel_form.is_valid():
            instance = personnel_form.save(commit=False)
            instance.submission = submission
            instance.save()
            return redirect(f"{request.path}?section=personnel_list")

    return render(request, "admin/iacuc_fill_out.html", {
        "submission": submission,
        "funding_form": funding_form,
        "funding_sources": funding_sources,
        "internal_form": internal_form,
        "internal_sources": internal_sources,
        "private_form": private_form,
        "tissue_form": tissue_form,
        "private_sources": private_sources,
        "external_collab_form": external_collab_form,
        "external_collaborations": external_collaborations,
        "off_campus_form": off_campus_form,
        "off_campus_entries": off_campus_entries,
        "surgery_forms": surgery_forms,
        "housing_form": housing_form,
        "permit_form": permit_form,
        "database_search_form": database_search_form,
        "transport_form": transport_form,
        "field_study_form": field_study_form,
        "wildlife_capture_form": wildlife_capture_form,
        "safety_form": safety_form,
        "species_sidebar": species_sidebar,  # ✅ Add this
        "breeding_forms": breeding_forms,
        "species_activity_templates": species_activity_templates,
        "procedure_forms": procedure_forms,
        "restraint_forms": restraint_forms,
        "mss_forms": mss_forms,
        "vetdrug_forms": vetdrug_forms,
        "vetdrug_lists": vetdrug_lists,
        "hazard_forms": hazard_forms,
        "hazard_lists": hazard_lists,
        "euthanasia_forms": euthanasia_forms,
        "personnel_form": personnel_form,
        "personnel_entries": personnel_entries,
        "species_info_forms": species_info_forms,
        "justification_forms": justification_forms,
        "use_location_forms": use_location_forms,
        "use_location_forms": use_location_forms,
        "use_location_entries": use_location_entries,
        "strain_forms": strain_forms,
        "strain_entries": strain_entries,
    })
@login_required
def add_personnel_entry(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id)

    if request.method == "POST":
        form = PersonnelForm(request.POST)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.submission = submission
            instance.save()
            messages.success(request, "Personnel entry added.")
            return redirect("iacuc_fill_out", submission_id=submission_id)
    else:
        form = PersonnelForm()

    return render(request, "admin/add_personnel_entry.html", {
        "form": form,
        "submission": submission
    })

@login_required
def add_personnel_info(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id)

    if request.method == 'POST':
        form = PersonnelInfoForm(request.POST)
        if form.is_valid():
            personnel = form.save(commit=False)
            personnel.submission = submission
            personnel.save()

            request.session['personnel_id'] = personnel.id  # ✅ REQUIRED
            return redirect('add_personnel_activities', submission_id=submission_id)
    else:
        form = PersonnelInfoForm()

    return render(request, 'admin/personnel/add_personnel_info.html', {
        'form': form,
        'submission': submission,
    })
@login_required
def add_personnel_activities(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id)
    personnel_id = request.session.get('personnel_id')

    if not personnel_id:
        messages.warning(request, "Start with personnel info before continuing.")
        return redirect('add_personnel_info', submission_id=submission_id)

    personnel = get_object_or_404(IACUCPersonnel, id=personnel_id)

    form = PersonnelActivitiesForm(request.POST or None, instance=personnel)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('add_personnel_training', submission_id=submission_id)

    return render(request, 'admin/personnel/add_personnel_activities.html', {
        'form': form,
        'submission': submission,  # ✅ this was missing
    })
@login_required
def add_personnel_training(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id)
    personnel_id = request.session.get('personnel_id')

    if not personnel_id:
        messages.warning(request, "Start with personnel info before continuing.")
        return redirect('add_personnel_info', submission_id=submission_id)

    personnel = get_object_or_404(IACUCPersonnel, id=personnel_id)

    form = PersonnelTrainingForm(request.POST or None, instance=personnel)
    if request.method == 'POST' and form.is_valid():
        form.save()
        del request.session['personnel_id']
        messages.success(request, "Personnel entry saved.")
        return redirect('iacuc_fill_out', submission_id=submission_id)

    return render(request, 'admin/personnel/add_personnel_training.html', {
        'form': form,
        'submission': submission,  # ✅ also missing
    })


@require_POST
@login_required
def iacuc_submit_for_admin_review(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id, user=request.user)

    if submission.status != 'pre_submission':
        messages.warning(request, "This protocol cannot be submitted at its current stage.")
        return redirect('iacuc_submission_home', submission_id=submission.id)

    submission.status = 'admin_review'
    submission.revision_stages = submission.revision_stages or {
        "admin_review": "pending",
        "pre_review": "not_started",
        "iacuc_review": "not_started",
        "post_review": "not_started"
    }
    submission.save()

    messages.success(request, "Protocol submitted for administrative review.")
    return redirect('iacuc_submission_home', submission_id=submission.id)


def manage_iacuc_committee(request, org_id):
    org = get_object_or_404(Organization, id=org_id)
    committee, _ = IACUCCommittee.objects.get_or_create(organization=org)
    members = IACUCMember.objects.filter(committee=committee).select_related('user')

    if request.method == 'POST':
        form = IACUCMemberForm(request.POST)
        if form.is_valid():
            member = form.save(commit=False)
            member.committee = committee
            member.save()
            messages.success(request, f"{member.user.get_full_name()} added as {member.get_role_display()}")
            return redirect('manage_iacuc_committee', org_id=org.id)
    else:
        form = IACUCMemberForm()

    context = {
        'organization': org,
        'committee': committee,
        'members': members,
        'form': form,
    }
    return render(request, 'admin/manage_committee.html', context)
def remove_iacuc_member(request, member_id):
    member = get_object_or_404(IACUCMember, id=member_id)
    org_id = member.committee.organization.id
    if request.method == 'POST':
        member.delete()
        messages.success(request, "Member removed from the committee.")
    return redirect('manage_iacuc_committee', org_id=org_id)

@login_required
def edit_external_collab(request, collab_id):
    collab = get_object_or_404(ExternalCollaboration, id=collab_id)
    if request.method == 'POST':
        form = ExternalCollaborationForm(request.POST, instance=collab)
        if form.is_valid():
            form.save()
            return redirect('iacuc_fill_out', submission_id=collab.submission.id)
    else:
        form = ExternalCollaborationForm(instance=collab)
    return render(request, 'admin/edit_external_collab.html', {'form': form})

@login_required
def delete_external_collab(request, collab_id):
    collab = get_object_or_404(ExternalCollaboration, id=collab_id)
    submission_id = collab.submission.id
    collab.delete()
    return redirect('iacuc_fill_out', submission_id=submission_id)

@login_required
def edit_funding_source(request, source_id):
    source = get_object_or_404(IACUCFundingSource, id=source_id)
    if request.method == 'POST':
        form = IACUCFundingSourceForm(request.POST, instance=source)
        if form.is_valid():
            form.save()
            return redirect('iacuc_fill_out', submission_id=source.submission.id)
    else:
        form = IACUCFundingSourceForm(instance=source)
    return render(request, 'admin/edit_funding_source.html', {'form': form})
@login_required
def edit_off_campus(request, entry_id):
    entry = get_object_or_404(OffCampusWork, id=entry_id)
    if request.method == 'POST':
        form = OffCampusWorkForm(request.POST, instance=entry)
        if form.is_valid():
            form.save()
            return redirect('iacuc_fill_out', submission_id=entry.submission.id)
    else:
        form = OffCampusWorkForm(instance=entry)
    return render(request, 'admin/edit_off_campus.html', {'form': form})
@login_required
def delete_off_campus(request, entry_id):
    entry = get_object_or_404(OffCampusWork, id=entry_id)
    submission_id = entry.submission.id
    entry.delete()
    return redirect('iacuc_fill_out', submission_id=submission_id)

@login_required
def delete_funding_source(request, source_id):
    source = get_object_or_404(IACUCFundingSource, id=source_id)
    submission_id = source.submission.id
    source.delete()
    return redirect('iacuc_fill_out', submission_id=submission_id)

# views.py
@require_POST
@login_required
def upload_iacuc_attachment(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id)
    uploaded_file = request.FILES.get('file')

    if not uploaded_file:
        return JsonResponse({'status': 'error', 'message': 'No file uploaded.'})

    attachment = IACUCSubmissionAttachment.objects.create(
        submission=submission,
        file=uploaded_file,
        uploaded_by=request.user
    )

    return JsonResponse({'status': 'success', 'message': 'File uploaded successfully.'})


@login_required
def get_iacuc_attachments(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id)
    attachments = submission.attachments.all().order_by('-uploaded_at')

    data = [{
        'file_url': attachment.file.url,
        'file_name': attachment.file.name.split('/')[-1],
        'uploaded_by': attachment.uploaded_by.get_full_name() or attachment.uploaded_by.username,
        'uploaded_at': attachment.uploaded_at.strftime('%B %d, %Y %I:%M %p')
    } for attachment in attachments]

    return JsonResponse({'status': 'success', 'attachments': data})

@require_POST
@login_required
def add_iacuc_note(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id)
    content = request.POST.get('content', '').strip()

    if not content:
        return JsonResponse({"status": "error", "message": "Content cannot be empty."}, status=400)

    IACUCNote.objects.create(
        submission=submission,
        content=content,
        author=request.user
    )
    return JsonResponse({"status": "success", "message": "Note added successfully!"})

@login_required
def get_iacuc_notes(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id)
    notes = submission.notes.order_by('-created_at')

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


@require_http_methods(["GET", "POST"])
@login_required
def section_notes(request, submission_id, section_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id)

    if request.method == "POST":
        content = request.POST.get("content", "").strip()
        if not content:
            return JsonResponse({"status": "error", "message": "Content cannot be empty."}, status=400)

        IACUCNote.objects.create(
            submission=submission,
            section_id=section_id,
            content=content,
            author=request.user
        )
        return JsonResponse({"status": "success", "message": "Note added successfully!"})

    # GET request – fetch notes for that section
    notes = IACUCNote.objects.filter(submission=submission, section_id=section_id).order_by('-created_at')

    data = [
        {
            "content": note.preview(),
            "full_content": note.content,
            "author": note.author.get_full_name(),
            "created_at": note.created_at.strftime("%B %d, %Y %I:%M %p")
        }
        for note in notes
    ]
    return JsonResponse({"status": "success", "notes": data})

# views.py
@require_POST
@login_required
def update_iacuc_status(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id)
    new_status = request.POST.get('status')
    if new_status in dict(IACUCSubmission.STATUS_CHOICES):
        submission.status = new_status
        submission.save()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error', 'message': 'Invalid status'}, status=400)

@login_required
@require_POST
def submit_for_admin_review(request, submission_id):
    submission = get_object_or_404(IACUCSubmission, id=submission_id)

    if submission.status == 'pre_submission':
        submission.status = 'admin_review'
        submission.save()
        messages.success(request, "Submission sent for Admin Review.")
    else:
        messages.warning(request, "Submission is not in a valid state to be submitted.")

    return redirect('iacuc_submission_detail', submission_id=submission.id)

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