from django.contrib import messages
from django.contrib import messages as django_messages
from django.contrib.auth.forms import AuthenticationForm
from django.core import serializers
from django.utils.timezone import now
from dashboard.forms import DemoRequestForm
import hashlib
from django.http import HttpResponseServerError
from myapp.utils.get_base_template import get_base_template
from django.urls import reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.http import JsonResponse, FileResponse, Http404, HttpResponseNotFound, HttpResponse,HttpRequest, HttpResponseRedirect, HttpResponseNotAllowed, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test  # To res
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q, F, Avg, Max, Min, Count
from django.utils import timezone, translation
from dashboard.models import *
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, authenticate
import pandas as pd
from docx import Document
from django.utils.decorators import method_decorator

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
from dashboard.forms import CustomUserCreationForm, UpdateProfileForm, ExperimentForm, BannerUploadForm
import json
from django.http import HttpResponseRedirect
from django.utils.safestring import mark_safe
from dashboard.forms import UserProfileForm
from dashboard.forms import *
from dashboard.forms import UpdateProfileForm, OverviewForm, ObservationForm, SampleForm, DoseForm
from django.views.decorators.http import require_http_methods
from django.utils.dateparse import parse_datetime
import csv
from dashboard.models import Invitation
from django.core.mail import send_mail
import os
import datetime
from io import BytesIO
from datetime import date



logger = logging.getLogger(__name__)

def home(request):
    try:
        # Your existing logic here
        return render(request, 'marketing/home.html')
    except Exception as e:
        logger.error(f"Error in home view: {e}")
        return HttpResponseServerError("Something went wrong")

def fund_finder(request):
    return render(request, 'features/fund_finder.html')
def system_to_system(request):
    return render(request, 'features/system_to_system.html')
def sponsored_programs(request):
    return render(request, 'features/sponsored_programs.html')

def fund_manager(request):
    return render(request, 'features/fund_manager.html')
def effort_report(request):
    return render(request, 'features/effort_report.html')
def human_safety(request):
    return render(request, 'features/human_safety.html')
def animal_safety(request):
    return render(request, 'features/animal_safety.html')
def research_safety(request):
    return render(request, 'features/research_safety.html')
def bio_safety(request):
    return render(request, 'features/bio_safety.html')

def conflict_of_int(request):
    return render(request, 'features/disclosures.html')

def radiation_safety(request):
    return render(request, 'features/radiation_safety.html')
def in_vivo(request):
    return render(request, 'features/in_vivo.html')

def stem_safety(request):
    return render(request, 'features/stem_safety.html')
def chemical_safety(request):
    return render(request, 'features/chemical_safety.html')
def vivarium_front(request):
    return render(request, 'features/vivarium_front.html')
def vivarium_front(request):
    return render(request, 'features/vivarium_front.html')
def scheduler(request):
    return render(request, 'features/scheduler.html')
def insight(request):
    return render(request, 'features/insight.html')
def ecosystem_view(request):
    return render(request, 'marketing/ecosystem.html')

def ficcs_view(request):
    return render(request, 'marketing/ficcs.html')
def pre_award_view(request):
    return render(request, 'marketing/pre-award.html')
def post_award_view(request):
    return render(request, 'marketing/post-award.html')
def compliance_view(request):
    return render(request, 'marketing/compliance.html')
def research_view(request):
    return render(request, 'marketing/Research.html')
def platform_view(request):
    return render(request, 'marketing/platform.html')
def streamline_view(request):
    return render(request, 'features/streamline.html')
def collab_view(request):
    return render(request, 'features/collaborate.html')
def scale_view(request):
    return render(request, 'features/scale.html')
def administrator_view(request):
    return render(request, 'features/administrators.html')
def researcher_view(request):
    return render(request, 'features/for_researchers.html')
def action_insight_view(request):
    return render(request, 'features/action_insight.html')
def improve_compliance_view(request):
    return render(request, 'features/improve_compliance.html')
def leadership_view(request):
    return render(request, 'features/leadership.html')
def platform_user_view(request):
    return render(request, 'platform/user_core.html')
def platform_org_view(request):
    return render(request, 'platform/org_core.html')
def platform_calendar_view(request):
    return render(request, 'platform/calendar_core.html')
def contracts(request):
    return render(request, 'features/contracts.html')
def export_controls(request):
    return render(request, 'features/export_control.html')
def platform_message_view(request):
    return render(request, 'platform/message_core.html')
def platform_task_view(request):
    return render(request, 'platform/task_core.html')
def platform_audit_view(request):
    return render(request, 'platform/audit_core.html')
def platform_auto_view(request):
    return render(request, 'platform/auto_core.html')

def request_demo(request):
    submission_success = False
    form = DemoRequestForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        full_message = (
            f"Name: {data['first_name']} {data['last_name']}\n"
            f"Email: {data['email']}\n"
            f"Phone: {data['phone']}\n"
            f"Job Title: {data['job_title'] or 'N/A'}\n"
            f"Company: {data['company']}\n"
            f"Interest Area: {data['interest']}\n\n"
            f"Message:\n{data['message']}"
        )

        for user in User.objects.filter(role='product_support', is_active=True):
            InboxNotification.objects.create(
                user=user,
                title=f"New Demo Request from {data['first_name']} {data['last_name']}",
                sender_name=f"{data['first_name']} {data['last_name']}",
                message=full_message,
                from_admin=True,
                is_read=False,
                timestamp=timezone.now()
            )

        submission_success = True
        form = DemoRequestForm()  # Reset form

    return render(request, 'marketing/request_demo.html', {
        'form': form,
        'submission_success': submission_success
    })
