from django.views import View
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib import messages
from django.core import serializers
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.utils.timezone import now, timezone
from django.utils.dateformat import format as django_format
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
import base64
from django.core.mail import send_mail
from myapp.utils.notifications import notify_user_ws
from myapp.utils.messages import create_message_user_entries
import time
from myapp.utils.image_tools import generate_group_photo
from myapp.utils.image_helpers import generate_group_profile_picture, generate_group_initials_picture
from django.db.models.functions import Replace
from django.urls import reverse
from django.core.serializers.json import DjangoJSONEncoder
from dashboard.generate_key import encrypt_message, get_conversation_key
from django.db.models import Q, F, Avg, Max, Min, Count, Case, When, IntegerField, BooleanField, ExpressionWrapper, OuterRef, Subquery, F
from django.utils import timezone
from django.utils.timezone import localtime, now
from django.utils.html import escape
from myapp.utils.get_base_template import get_base_template

from .models import (Conversation, Message, User, Notification, MessageUser, ConversationUser, Organization, InboxNotification, GroupMember, EventInvitation, Experiment, RFIDAssignment, WeightMeasurement, Collaborator, CalendarEvent, Comment, Friend, Cage, Animal, Sample, Dose, Observation, Comment)
from django.contrib.auth.forms import UserCreationForm, PasswordResetForm
from django.contrib.auth import login, authenticate
from django.contrib.auth.models import User
from django.contrib.messages import error  # Import specifically if needed
import pandas as pd
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.core.paginator import Paginator
import mimetypes
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import random
from django.contrib.auth import logout
from django.db import IntegrityError
from django.contrib.auth import get_user_model
from .forms import CustomUserCreationForm, UpdateProfileForm, ExperimentForm, UpdateGroupInfoForm
import json
from django.http import HttpResponseRedirect
from django.utils.safestring import mark_safe
from .forms import UserProfileForm
from .forms import ProfilePictureForm, MessageForm
from .forms import UpdateProfileForm, OverviewForm, ObservationForm, SampleForm, DoseForm
from django.views.decorators.http import require_http_methods
from django.utils.dateparse import parse_datetime
import csv
from .models import Invitation
from django.templatetags.static import static
from django.template.loader import render_to_string
from datetime import date, datetime
from django.utils import timezone
import pytz
from django.db.models import Prefetch

channel_layer = get_channel_layer()

import logging
# Assuming you have access to request.user and the last_message_time is in UTC.

logger = logging.getLogger('performance')
# Set up logging

from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.contrib.staticfiles.storage import staticfiles_storage
UserModel = get_user_model()
def mask_email(email):
        """
        Mask the email for display like: j****e@example.com
        """
        parts = email.split('@')
        if len(parts) != 2:
            return email  # fallback if invalid

        name, domain = parts
        if len(name) < 3:
            masked_name = name[0] + "*" * (len(name) - 1)
        else:
            masked_name = name[0] + "*" * (len(name) - 2) + name[-1]

        return f"{masked_name}@{domain}"
class UsernameEntryView(View):
    def get(self, request):
        return render(request, 'username_entry.html')

    def post(self, request):
        username = request.POST.get('username')
        user = UserModel.objects.filter(username=username).first()
        if user:
            request.session['login_username'] = username
            return redirect('role_selection')
        else:
            messages.error(request, 'No account found with that username.')
            return render(request, 'username_entry.html')
            
class RoleSelectionView(View):
    def get(self, request):
        username = request.session.get('login_username')
        if not username:
            return redirect('username_entry')

        user = UserModel.objects.filter(username=username).first()
        if not user:
            return redirect('username_entry')

        role = (user.role or "").lower()
        roles = []

        # ✅ IT Admin only (superuser without an organization)
        if user.is_superuser and not getattr(user, 'organization', None):
            return render(request, 'role_selection.html', {
                'username': username,
                'roles': [('IT Admin', 'it_admin_login')],
            })

        # ✅ Org IT Admin
        if role == 'org_it_admin':
            roles.append(('Org IT Admin', 'org_it_admin_login'))
            roles.append(('Researcher', 'login'))  # They also need research access

        # ✅ Internal support teams
        if user.is_superuser or role in [
            'product_support', 'sales_rep', 'customer_success', 'implementation_rep'
        ]:
            roles.append(('IT Admin', 'it_admin_login'))

        # ✅ Admins also get Researcher access
        if role in ['admin', 'principal_admin']:
            roles.append(('Admin', 'admin_login'))
            roles.append(('Researcher', 'login'))

        # ✅ Everyone else just gets Researcher
        if not roles:
            roles.append(('Researcher', 'login'))

        return render(request, 'role_selection.html', {
            'username': username,
            'roles': roles
        })

class ConfirmEmailView(View):
    
    def get(self, request):
        username = request.session.get('login_username')
        if not username:
            return redirect('username_entry')

        user = UserModel.objects.filter(username=username).first()
        if not user:
            return redirect('username_entry')

        masked = mask_email(user.email)
        return render(request, 'confirm_email.html', {
            'masked_email': masked,
        })

    def post(self, request):
        username = request.session.get('login_username')
        entered_email = request.POST.get('email', '').strip()
        user = UserModel.objects.filter(username=username).first()

        if not user or entered_email.lower() != user.email.lower():
            messages.error(request, 'Email does not match the one on file.')
            return redirect('confirm_email')

        form = PasswordResetForm({'email': entered_email})
        if form.is_valid():
            form.save(
                request=request,
                use_https=False,
                email_template_name='password_reset_email.txt',
                subject_template_name='password_reset_subject.txt',
                from_email='Sports1026@gmail.com',
            )
            return redirect('password_reset_done')
        else:
            messages.error(request, 'Error sending password reset email.')
            return redirect('confirm_email')
        