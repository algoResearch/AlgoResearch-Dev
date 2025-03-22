import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser, User
from django.contrib.postgres.fields import ArrayField  # or use JSONField if on older Django versions
from django.contrib.auth import get_user_model
from django.utils.text import slugify
import base64
from django.conf import settings
from django.core.cache import cache
import json
from django.http import JsonResponse
import re
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils.timezone import now
from dashboard.generate_key import encrypt_message, decrypt_message, get_conversation_key
from dashboard.generate_key import encrypt_content
from dashboard.Tasks import generate_video_thumbnail
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont
from django.contrib.contenttypes.fields import GenericForeignKey
import io
from django.contrib.contenttypes.models import ContentType
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from django.db.models.signals import post_save
from cryptography.hazmat.primitives import hashes
import mimetypes
from django.dispatch import receiver
from django.db.models import Max, JSONField, Q
import os
from django.core.exceptions import ValidationError
from cryptography.fernet import Fernet
from pytz import common_timezones 
import random
import string
import datetime
from datetime import timedelta, date
import moviepy
from moviepy import VideoFileClip
import logging
logger = logging.getLogger(__name__)

class Organization(models.Model):
    name = models.CharField(max_length=255, unique=True)
    address = models.TextField(blank=True, null=True)
    logo = models.ImageField(upload_to='organization_logos/', blank=True, null=True)
    sidebar_color = models.CharField(max_length=7, default='#115600')  # Default green for sidebar
    hover_color = models.CharField(max_length=7, default='#e1cd10')    # Default yellow for hover
    primary_color = models.CharField(max_length=7, default='#000000')
    secondary_color = models.CharField(max_length=7, default='#FFFFFF') 
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    organization = models.ForeignKey(
        'Organization',
        on_delete=models.CASCADE,
        related_name="users",
        blank=True,
        null=True
    )
    ROLE_CHOICES = [
        ('principal_admin', 'Principal Admin'),
         ('org_it_admin', 'Organization IT Admin'),
        ('admin', 'Admin'),
        ('officer', 'Officer'),
        ('researcher', 'Researcher'),
        ('viewer', 'Viewer'),
        ('approval_member', 'Approval Member'),
    ]
    PROFILE_VISIBILITY_CHOICES = [
        ('public', 'Public'),
        ('private', 'Private'),
    ]
    profile_visibility = models.CharField(
        max_length=10,
        choices=PROFILE_VISIBILITY_CHOICES,
        default='public'
    )

    prefix = models.CharField(max_length=10, blank=True, null=True)
    middle_name = models.CharField(max_length=50, blank=True, null=True)
    suffix = models.CharField(max_length=10, blank=True, null=True)
    position = models.CharField(max_length=255, blank=True, null=True)
    street1 = models.CharField(max_length=255, blank=True, null=True)
    street2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    county = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    province = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    zip_code = models.CharField(max_length=20, blank=True, null=True)
    fax = models.CharField(max_length=20, blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='viewer')
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    net_id = models.CharField(max_length=50, blank=True, null=True, unique=True)
    department = models.CharField(max_length=255, blank=True, null=True)
    mail_code = models.CharField(max_length=10, blank=True, null=True)
    is_public = models.BooleanField(default=True)
    is_published = models.BooleanField(default=False)
    mute_all_notifications = models.BooleanField(default=False, help_text="Mute all incoming notifications for this user")
    profile_banner = models.ImageField(upload_to='profile_banners/', blank=True, null=True)
    institution = models.CharField(max_length=255, blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    timezone = models.CharField(max_length=50, default='EST')
    is_organization_admin = models.BooleanField(default=False)
    dashboard_layout = models.JSONField(default=list, blank=True)
    blocked_users = models.ManyToManyField(
        'self',
        symmetrical=False,
        related_name='blocked_by',
        blank=True
    )

    def __str__(self):
        return self.username

    def block_user(self, user):
        """
        Block another user.
        """
        if user != self:
            self.blocked_users.add(user)

    def unblock_user(self, user):
        """
        Unblock another user.
        """
        if user != self:
            self.blocked_users.remove(user)

    def is_blocked(self, user):
        """
        Check if the user is blocked by this user.
        """
        return self.blocked_users.filter(id=user.id).exists()
    @staticmethod
    def generate_default_profile_picture(initial: str, size: int = 200, background_color: str = "#115600") -> ContentFile:
        """
        Generate a default profile picture with the user's initial.
    
        :param initial: The initial to display.
        :param size: The size of the square image.
        :param background_color: The background color of the image.
        :return: ContentFile of the generated image.
        """
        # Create a square image with the specified background color
        img = Image.new("RGB", (size, size), color=background_color)

        # Initialize drawing context
        draw = ImageDraw.Draw(img)

        # Define font
        try:
            font = ImageFont.truetype("arial.ttf", size=int(size * 0.75))
        except IOError:
            font = ImageFont.load_default()

        # Calculate text size and position using textbbox
        text_bbox = draw.textbbox((0, 0), initial, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        text_x = (size - text_width) // 2
        text_y = (size - text_height) // 2 - int(size * 0.1)  # Adjust to center the text

        # Draw the initial in white
        draw.text((text_x, text_y), initial, font=font, fill="white")

        # Save image to a BytesIO buffer
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        return ContentFile(buffer.read(), name=f"default_{initial}.png")


    def save(self, *args, **kwargs):
        # Generate a default profile picture if none is set
        if not self.profile_picture:
            initial = self.first_name[0].upper() if self.first_name else "U"
            background_color = (
                self.organization.sidebar_color
                if self.organization and self.organization.sidebar_color
                else "#115600"
            )
            self.profile_picture = self.generate_default_profile_picture(initial, background_color=background_color)

        super().save(*args, **kwargs)

class Building(models.Model):
    name = models.CharField(max_length=255)
    organization = models.ForeignKey('Organization', on_delete=models.CASCADE, related_name='buildings')

    def __str__(self):
        return self.name

class Room(models.Model):
    name = models.CharField(max_length=255)
    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name='rooms')

    def __str__(self):
        return f"{self.name} (Building: {self.building.name})"

class Rack(models.Model):
    name = models.CharField(max_length=255)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='racks')

    def __str__(self):
        return f"{self.name} (Room: {self.room.name})"
    
class ProtocolDesign(models.Model):
    organization = models.OneToOneField(Organization, on_delete=models.CASCADE)
    fields = models.JSONField(default=list)  # Stores the dynamic questions as JSON

class ProtocolTemplate(models.Model):
    organization = models.ForeignKey(
        'Organization',
        on_delete=models.CASCADE,
        related_name="protocol_templates"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_protocol_templates",
        null=True,  # Keep it nullable for now to avoid migration issues
        blank=True
    )
    custom_fields = models.JSONField(default=list)  # Stores dynamic fields
    template_name = models.CharField(max_length=255, default="Default Template")
    roles_required = models.JSONField(default=dict)
    attributes_selected = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank = True)


    def __str__(self):
        return f"{self.template_name} - {self.organization.name}"

class Protocol(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    title = models.CharField(max_length=255)

    principal_investigator = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="protocols_as_pi"
    )
    co_principal_investigator = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="protocols_as_co_pi", blank=True
    )
    
    administrative_contact = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="protocols_as_admin"
    )
    additional_submitters = models.ManyToManyField(
        User, related_name="protocols_as_submitter", blank=True
    )
    emergency_contacts = models.ManyToManyField(User, related_name="protocol_emergency_contacts", blank=True)
    description = models.TextField()
    file = models.FileField(upload_to='protocols/', blank=True, null=True)
    submitted_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="submitted_protocols")
    approval_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_protocols")
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    is_draft = models.BooleanField(default=True)  #
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)
    personnel = models.TextField(blank=True, null=True)
    responsible_person = models.CharField(max_length=255, blank=True, null=True)
    contact_email = models.EmailField(blank=True, null=True)
    contact_phone = models.CharField(max_length=20, blank=True, null=True)
    steps_completed = JSONField(default=dict)  # Track completed steps
    rationale = models.JSONField(default=dict, blank=True)  # For Django 3.1+
    procedures = models.JSONField(default=dict, blank=True)  # For Django 3.1+
    answers = models.JSONField(default=dict, blank=True)

    alternative_search = models.JSONField(default=dict, blank=True)  # For Django 3.1+
    procedure_relationships = models.JSONField(default=dict, blank=True)  # For Django 3.1+
    husbandry = models.JSONField(default=dict, blank=True)  # For Django 3.1+
    euthanasia = models.JSONField(default=dict, blank=True)  # For Django 3.1+

    mini_steps_completed = models.JSONField(default=dict, blank=True)  # Ensures it's always a dictionary
    triggered_sub_steps = models.JSONField(default=list)  # ✅ Store triggered sub-steps
    species_name = models.CharField(max_length=255, blank=True, null=True)
    number_of_animals = models.PositiveIntegerField(blank=True, null=True)
    age_range = models.CharField(max_length=255, blank=True, null=True)
    weight_range = models.CharField(max_length=255, blank=True, null=True)
    species_notes = models.TextField(blank=True, null=True)

    protocol_purpose = models.TextField(blank=True, null=True)
    research_areas = models.CharField(max_length=255, blank=True, null=True)
    expected_outcomes = models.TextField(blank=True, null=True)
    methodology_overview = models.TextField(blank=True, null=True)
    funding_source = models.CharField(max_length=255, blank=True, null=True)
    grant_number = models.CharField(max_length=100, blank=True, null=True)
    funding_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    funding_duration = models.PositiveIntegerField(blank=True, null=True)  # Years
    ethical_restrictions = models.TextField(blank=True, null=True)
    compliance_guidelines = models.TextField(blank=True, null=True)  # Required
    safety_measures = models.TextField(blank=True, null=True)
    ethical_considerations = models.TextField(blank=True, null=True)
    special_approvals = models.CharField(max_length=255, blank=True, null=True)
    required_certifications = models.TextField(blank=True, null=True)  # Required
    certification_documents = models.TextField(blank=True, null=True)  # Stores file URLs (comma-separated)
    certification_body = models.CharField(max_length=255, blank=True, null=True)
    certification_expiry = models.DateField(blank=True, null=True)
    additional_notes = models.TextField(blank=True, null=True)
    submitted_at = models.DateTimeField(blank=True, null=True)

    collaboration = models.CharField(max_length=3, choices=[("Yes", "Yes"), ("No", "No")], default="No")
    institution_name = models.CharField(max_length=255, blank=True, null=True)

    # Biological Material
    biological_material = models.CharField(max_length=3, choices=[("Yes", "Yes"), ("No", "No")], default="No")
    biological_material_data = models.JSONField(default=list, blank=True)

    # Hazardous Agents
    recombinant_dna = models.CharField(max_length=3, choices=[("Yes", "Yes"), ("No", "No")], default="No")
    ibc_rdna_protocol_number = models.CharField(max_length=255, blank=True, null=True)

    infectious_agents = models.CharField(max_length=3, choices=[("Yes", "Yes"), ("No", "No")], default="No")
    ibc_biosafety_protocol_number = models.CharField(max_length=255, blank=True, null=True)

    protocol_needed = models.CharField(max_length=3, choices=[("Yes", "Yes"), ("No", "No")], default="No")
    protocol_verification_id = models.CharField(max_length=255, blank=True, null=True)
    protocol_user_id = models.CharField(max_length=255, blank=True, null=True)

    toxic_agents = models.CharField(max_length=3, choices=[("Yes", "Yes"), ("No", "No")], default="No")
    toxic_agents_data = models.JSONField(default=list, blank=True)

    # Radiological Agents
    radiological_agents = models.CharField(max_length=3, choices=[("Yes", "Yes"), ("No", "No")], default="No")
    isotope = models.CharField(max_length=255, blank=True, null=True)
    radiation_device = models.CharField(max_length=255, blank=True, null=True)
    uses_data = models.JSONField(default=dict, blank=True)  # ✅ Add this field to store responses


    # Field Study
    field_study = models.CharField(max_length=3, choices=[("Yes", "Yes"), ("No", "No")], default="No")
    field_study_description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Draft')

    def __str__(self):
        return self.title
    def save(self, *args, **kwargs):
        # ✅ Ensure rationale is initialized as a dictionary
        if not isinstance(self.rationale, dict):
            self.rationale = {}
        if not isinstance(self.procedures, dict):
            self.procedures = {}
        if not isinstance(self.alternative_search, dict):
            self.alternative_search = {}
        if not isinstance(self.procedure_relationships, dict):
            self.procedure_relationships = {}
        if not isinstance(self.husbandry, dict):
            self.husbandry = {}
        if not isinstance(self.euthanasia, dict):
            self.euthanasia = {}
        if not isinstance(self.steps_completed, dict):
            self.steps_completed = {}
        super().save(*args, **kwargs)

class ApprovalComment(models.Model):
    protocol = models.ForeignKey(Protocol, on_delete=models.CASCADE, related_name="approval_comments")
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE)
    section = models.CharField(max_length=50, choices=[
        ("rationale", "Rationale"),
        ("procedures", "Procedures"),
        ("alternative_search", "Alternative Search"),
        ("procedure_relationships", "Procedure Relationships"),
        ("husbandry", "Husbandry"),
        ("euthanasia", "Euthanasia"),
        ("funding", "Funding"),
        ("guidelines", "Guidelines"),
        ("certifications", "Certifications"),
        ("additional_notes", "Additional Notes"),
        ("general", "General"),
    ])
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Comment by {self.reviewer.username} on {self.protocol.title}"



class SpeciesEntry(models.Model):
    protocol = models.ForeignKey(Protocol, related_name="species_entries", on_delete=models.CASCADE)
    species = models.CharField(max_length=255)
    method = models.CharField(max_length=255)
    route = models.CharField(max_length=255)
    dosage = models.CharField(max_length=255)
    secondary_method = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
class OrganizationManager(models.Manager):
    def for_user(self, user):
        return self.filter(organization=user.organization)
class ExperimentManager(models.Manager):
    def for_user(self, user):
        """
        Returns experiments that the user is allowed to access.
        """
        if user.is_superuser:
            return self.all()
        return self.filter(
            Q(owner=user) | Q(collaborators__user=user)
        ).distinct()

    
class Experiment(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('completed', 'Completed'),
    ]
    name = models.CharField(max_length=255)
    organization = models.ForeignKey(
        'Organization',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='experiments'
    )
    bulk_upload_id = models.UUIDField(
        default=None, null=True, blank=True, help_text="ID for tracking bulk uploads"
    )
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='draft')  # New field
    archived = models.BooleanField(default=False)
    monitor_weight = models.BooleanField(default=False)
    monitor_tumor = models.BooleanField(default=False)
    duration = models.PositiveIntegerField(blank=True, null=True)
    warning_weight_percentage = models.FloatField(null=True, blank=True)
    removal_weight_percentage = models.FloatField(null=True, blank=True)
    create_group_chat = models.BooleanField(default=False)  # New field
    tumor_volume_warning = models.FloatField(null=True, blank=True, help_text="Warning threshold for tumor volume in mm³")
    tumor_volume_removal = models.FloatField(null=True, blank=True, help_text="Removal threshold for tumor volume in mm³")
    

    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    number_of_animals = models.IntegerField(null=True, blank=True)
    number_of_groups = models.PositiveIntegerField(default=1)
    max_per_cage = models.PositiveIntegerField(default=1)
    investigators = models.ManyToManyField(
        User,
        related_name='experiments',
        blank=True,
        help_text="Investigators assigned to this experiment"
    )
    drug_list = models.ManyToManyField('Drug', related_name='experiments', blank=True)
    strain_list = models.ManyToManyField('Strain', related_name='experiments', blank=True)
    ended = models.BooleanField(default=False)
    end_date = models.DateField(null=True, blank=True)
    step_basic_info_completed = models.BooleanField(default=False)
    step_investigators_completed = models.BooleanField(default=False)
    step_metrics_completed = models.BooleanField(default=False)
    step_tasks_completed = models.BooleanField(default=False)
    objects = ExperimentManager()
    step_groups_completed = models.BooleanField(default=False)
    step_summary_completed = models.BooleanField(default=False)
    steps_completed = JSONField(default=dict, blank=True)  # Tracks completed steps
    rfid_required = models.BooleanField(default=False)
    weight_schedule = models.BooleanField(default=False)
    number_of_animals = models.IntegerField(null=True, blank=True)  
    weigh_in_interval = models.PositiveIntegerField(blank=True, null=True)
    is_draft = models.BooleanField(default=False)  # Indicates if the experiment is a draft

    experiment_duration = models.PositiveIntegerField(blank=True, null=True)
    tumor_measurement_interval = models.PositiveIntegerField(blank=True, null=True)
    tumor_size_method = models.CharField(
        max_length=50,
        choices=[
            ('area_approximation', '2D Area Approximation'),
            ('ellipsoid_with_height', 'Ellipsoid with Height'),
            ('cylinder', 'Cylinder Volume Approximation'),
            ('rectangular', 'Rectangular Volume Approximation'),
        ],
        default='ellipsoid_with_height',
        blank=True,
        null=True
    )
    weight_frequency = models.CharField(
        max_length=20,
        choices=[
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('biweekly', 'Bi-Weekly'),
            ('monthly', 'Monthly'),
            ('custom', 'Custom Interval'),
            ('', 'None')
        ],
        blank=True,
        null=True
    )
    tumor_frequency = models.CharField(
        max_length=20,
        choices=[
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('biweekly', 'Bi-Weekly'),
            ('monthly', 'Monthly'),
            ('custom', 'Custom Interval'),
            ('', 'None')
        ],
        blank=True,
        null=True
    )
    custom_interval_days = models.PositiveIntegerField(blank=True, null=True)
    tumor_custom_interval_days = models.PositiveIntegerField(blank=True, null=True)
    weight_end_date = models.DateField(blank=True, null=True)
    tumor_end_date = models.DateField(blank=True, null=True)
    owner = models.ForeignKey('User', on_delete=models.CASCADE, related_name='owned_experiments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    session_active = models.BooleanField(default=False)
    session_id = models.UUIDField(null=True, blank=True)
    session_start_time = models.DateTimeField(null=True, blank=True)
    session_end_time = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['organization']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return self.name

    @property
    def is_active(self):
        return not self.ended and (self.start_date <= timezone.now().date() if self.start_date else True)


class MiniStep(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)  # Name of the mini-step
    order = models.PositiveIntegerField(default=1)  # Order in nav
    is_required = models.BooleanField(default=False)  # Mark as required

    def __str__(self):
        return f"{self.organization.name} - {self.name}"
class MiniStepField(models.Model):
    FIELD_TYPES = [
        ('text', 'Text'),
        ('textarea', 'Textarea'),
        ('number', 'Number'),
        ('dropdown', 'Dropdown'),
        ('file', 'File Upload'),
        ('table', 'Table'),  # ✅ Add Table Field Type
    ]

    mini_step = models.ForeignKey(MiniStep, on_delete=models.CASCADE, related_name="fields")
    label = models.CharField(max_length=255)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES)
    options = models.TextField(blank=True, null=True)  # For dropdowns (comma-separated)
    is_required = models.BooleanField(default=False)

    # ✅ Fields for Table
    column_names = models.TextField(blank=True, null=True)  # Comma-separated column headers
    fixed_rows = models.PositiveIntegerField(blank=True, null=True)  # Set row count (if fixed)
    allow_dynamic_rows = models.BooleanField(default=False)  # Allow user to add rows

    parent_field = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
    trigger_option = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.mini_step.name} - {self.label}"


class ProtocolMiniStepData(models.Model):
    protocol = models.ForeignKey(Protocol, on_delete=models.CASCADE)
    mini_step = models.ForeignKey(MiniStep, on_delete=models.CASCADE)
    field = models.ForeignKey(MiniStepField, on_delete=models.CASCADE)
    value = models.TextField(blank=True, null=True)  # Store text, JSON for dropdown, file path

    def __str__(self):
        return f"{self.protocol.title} - {self.mini_step.name} - {self.field.label}"


class SubMiniStep(models.Model):
    parent_mini_step = models.ForeignKey(MiniStep, on_delete=models.CASCADE, related_name="sub_mini_steps")
    name = models.CharField(max_length=255)
    order = models.IntegerField(default=0)
    trigger_field = models.ForeignKey(MiniStepField, on_delete=models.CASCADE, related_name="triggered_sub_steps", null=True, blank=True)
    trigger_value = models.CharField(max_length=255, help_text="Dropdown option that triggers this sub-step")
    is_required = models.BooleanField(default=False)
    

    def __str__(self):
        return f"{self.name} (Triggered by {self.trigger_field.label} = {self.trigger_value})"

class SubMiniStepField(models.Model):
    sub_mini_step = models.ForeignKey(SubMiniStep, on_delete=models.CASCADE, related_name="fields")
    label = models.CharField(max_length=255)
    field_type = models.CharField(
        max_length=50,
        choices=[("text", "Text"), ("textarea", "Textarea"), ("number", "Number"),
                 ("dropdown", "Dropdown"), ("file", "File Upload"), ("table", "Table")]
    )
    options = models.TextField(blank=True, null=True)  # For dropdown
    column_names = models.TextField(blank=True, null=True)  # For table columns
    fixed_rows = models.PositiveIntegerField(blank=True, null=True)
    allow_dynamic_rows = models.BooleanField(default=False)
    is_required = models.BooleanField(default=False)
    parent_field = models.ForeignKey('self', on_delete=models.SET_NULL, blank=True, null=True, related_name="dependent_fields")
    trigger_option = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.sub_mini_step.name} - {self.label}"

class TrainingFolder(models.Model):
    name = models.CharField(max_length=255)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # ✅ Fix: Track users assigned to this folder
    assigned_users = models.ManyToManyField(User, related_name="training_folders", blank=True)

    def __str__(self):
        return self.name


class Certification(models.Model):
    course_id = models.CharField(max_length=100)
    course_title = models.CharField(max_length=255)
    folder = models.ForeignKey(TrainingFolder, on_delete=models.CASCADE, related_name="certifications")

    # ✅ Fix: Change related_name to avoid conflict
    assigned_users = models.ManyToManyField(User, related_name="certification_assignments", blank=True)

    def __str__(self):
        return f"{self.course_title} ({self.course_id})"


class UserCertification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    certification = models.ForeignKey('Certification', on_delete=models.CASCADE)
    assigned_at = models.DateTimeField(auto_now_add=True)

    # ✅ Fix: Unique related_name for assigned_by to avoid conflict
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="certifications_assigned")

    def __str__(self):
        return f"{self.user.username} - {self.certification.course_title}"


class UserAction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)  # Add this line
    action = models.CharField(max_length=255)  # e.g., "Signed Document"
    timestamp = models.DateTimeField(auto_now_add=True)
    additional_info = models.TextField(blank=True, null=True)
    typed_signature = models.CharField(max_length=255, blank=True, null=True)  # User's typed signature
    unique_signature = models.CharField(max_length=255, blank=True, null=True)  # System-generated unique signature
    session_id = models.UUIDField(null=True, blank=True)  # Add this field

    def __str__(self):
        return f'{self.user.username} - {self.action} - {self.timestamp}'

    
class Drug(models.Model):
    name = models.CharField(max_length=255)
    experiment = models.ForeignKey('Experiment', related_name='drug_set', on_delete=models.CASCADE, null=True)  # Allow null values
    def __str__(self):
        return self.name

class Strain(models.Model):
    name = models.CharField(max_length=255)
    experiment = models.ForeignKey('Experiment', related_name='strain_set', on_delete=models.CASCADE, null=True)  # Allow null values

    def __str__(self):
        return self.name

class CalendarEvent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    organization = models.ForeignKey('Organization', on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    all_day = models.BooleanField(default=False)
    color = models.CharField(max_length=10, default='#1E90FF')
    is_shared = models.BooleanField(default=False)

    # Link to Experiment and Task
    experiment = models.ForeignKey('Experiment', on_delete=models.CASCADE, null=True, blank=True, related_name="calendar_events")
    task = models.ForeignKey('Task', on_delete=models.CASCADE, null=True, blank=True, related_name="calendar_events")
    
    # Recurrence fields
    is_recurring = models.BooleanField(default=False)
    recurrence_interval = models.IntegerField(null=True, blank=True)
    recurrence_frequency = models.CharField(max_length=10, choices=[('week', 'Week'), ('month', 'Month')], null=True, blank=True)
    recurrence_days = models.JSONField(default=list, blank=True)
    recurrence_end_type = models.CharField(max_length=10, choices=[('never', 'Never'), ('on', 'On Date'), ('after', 'After Occurrences')], null=True, blank=True)
    recurrence_end_date = models.DateTimeField(null=True, blank=True)
    recurrence_occurrences = models.IntegerField(null=True, blank=True)

    # New Field: Completed status
    completed = models.BooleanField(default=False)

    def __str__(self):
        return self.title

class EventInvitation(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    event = models.ForeignKey(CalendarEvent, on_delete=models.CASCADE, related_name="invitations")
    invited_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="event_invitations")
    decision_date = models.DateTimeField(auto_now=True)
    status = models.CharField(
        max_length=10,
        choices=[("pending", "Pending"), ("accepted", "Accepted"), ("declined", "Declined")],
        default="pending"
    )
    notification_sent = models.BooleanField(default=False)

    def accept(self):
        self.status = "accepted"
        self.save()
        # Add the event to the user's calendar if accepted
        CalendarEvent.objects.create(
            user=self.invited_user,
            organization=self.event.organization,
            title=self.event.title,
            description=self.event.description,
            start_date=self.event.start_date,
            end_date=self.event.end_date,
            all_day=self.event.all_day,
            color=self.event.color,
            is_shared=True
        )

    def decline(self):
        self.status = "declined"
        self.save()


class Cage(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE, null=True)
    cage_number = models.PositiveIntegerField(default=1)
    rack = models.ForeignKey(Rack, on_delete=models.SET_NULL, null=True, blank=True, related_name="cages")  # ✅ Temporarily allow null
    name = models.CharField(max_length=100)
    assigned_users = models.ManyToManyField(User, blank=True, related_name="assigned_cages")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='cages', null=True, blank=True)
    capacity = models.IntegerField()
    allowed_users = models.ManyToManyField(
        User, 
        related_name="allowed_cages", 
        blank=True, 
        help_text="Users allowed to view this cage"
    )

    def save(self, *args, **kwargs):
        # Set cage_number to the next available number within the organization
        if not self.pk and not self.cage_number:  # Check if it's a new Cage without a cage_number
            last_cage = Cage.objects.filter(organization=self.organization).aggregate(Max('cage_number'))
            self.cage_number = (last_cage['cage_number__max'] or 0) + 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} (Capacity: {self.capacity})"
    
class Group(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    color = models.CharField(max_length=7, default='#FFFFFF')
    number_of_animals = models.IntegerField()
    treatment = models.ForeignKey('Treatment', on_delete=models.SET_NULL, null=True, blank=True)  # Use string reference for Treatment

    def __str__(self):
        return self.name

class Treatment(models.Model):
    experiment = models.ForeignKey('Experiment', on_delete=models.CASCADE, related_name='treatments')
    drug_name = models.CharField(max_length=255)
    dose = models.DecimalField(max_digits=10, decimal_places=2)
    stock_concentration = models.DecimalField(max_digits=10, decimal_places=2)
    dose_volume = models.DecimalField(max_digits=10, decimal_places=2)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.drug_name} - {self.dose}"

class RFIDAssignmentManager(models.Manager):
    def for_user(self, user):
        # Handle case where user has no organization
        if user.organization is None:
            return self.none()  # No results if no organization is associated with user
        # Otherwise, filter assignments based on the user's organization
        return self.filter(experiment__organization=user.organization)


class RFIDAssignment(models.Model):
    experiment = models.ForeignKey('Experiment', on_delete=models.CASCADE, null=True, blank=True)
    animal = models.ForeignKey('Animal', on_delete=models.CASCADE, related_name='rfid_assignments')
    rfid = models.CharField(max_length=100)
    objects = RFIDAssignmentManager()  # Use the custom manager
    weight = models.FloatField(null=True, blank=True)
    initial_weight = models.FloatField(null=True, blank=True)
    tumor_size = models.FloatField(null=True, blank=True)
    removed = models.BooleanField(default=False)
    cage_number = models.IntegerField(null=True, blank=True)
    initial_weight_date = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ('experiment', 'animal')  # Each (experiment, animal) pair is unique

    def __str__(self):
        return f"RFID Assignment for Animal {self.animal.id} in Experiment {self.experiment.name if self.experiment else 'No Experiment'}"


class RFID(models.Model):
    rfid = models.CharField(max_length=100, unique=True)
    assigned = models.BooleanField(default=False)

    def __str__(self):
        return self.rfid



class Animal(models.Model):
    # Globally unique identifier
    uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    assigned_users = models.ManyToManyField(User, related_name='assigned_animals', blank=True)
    # ForeignKey to Experiment, Group, and Organization
    experiment = models.ForeignKey(
        'Experiment',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='animals'  # Add this related_name
    )
    group = models.ForeignKey('Group', null=True, blank=True, on_delete=models.SET_NULL)
    organization = models.ForeignKey('Organization', on_delete=models.CASCADE, null=True, blank=True)
    cage = models.ForeignKey('Cage', on_delete=models.SET_NULL, null=True, related_name='animals')
    
    # RFID tag (non-unique globally)
    rfid_tag = models.CharField(max_length=100, blank=True, null=True)
    
    # Unique animal_index within an organization
    animal_index = models.PositiveIntegerField(null=True, blank=True)
    housing_location = models.CharField(max_length=255, blank=True, null=True)
    room_number = models.CharField(max_length=50, blank=True, null=True)
    rack_number = models.CharField(max_length=50, blank=True, null=True)
    # Other fields
    treatments = models.ManyToManyField('Treatment', related_name="animals", blank=True)
    tail = models.CharField(max_length=255, blank=True, null=True)
    ear = models.CharField(max_length=255, blank=True, null=True)
    tag = models.CharField(max_length=255, blank=True, null=True)
    donor = models.CharField(max_length=255, blank=True, null=True)
    tracking_date = models.DateField(null=True, blank=True)
    fur_color = models.CharField(max_length=7, default='')
    date_of_birth = models.DateField(null=True, blank=True)
    age = models.IntegerField(null=True, blank=True)
    sex = models.CharField(max_length=10, choices=[('Male', 'Male'), ('Female', 'Female')], blank=True, null=True)
    species = models.CharField(max_length=100, blank=True, null=True)
    strain = models.CharField(max_length=100, blank=True, null=True)
    strains = models.ManyToManyField('Strain', blank=True, related_name='animals')
    drugs = models.ManyToManyField('Drug', blank=True, related_name='animals')
    at_risk = models.BooleanField(default=False)
    is_removed = models.BooleanField(default=False)
    is_available = models.BooleanField(default=True)
    removed = models.BooleanField(default=False)
    removal_signature = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=False, help_text="True if assigned to an experiment, otherwise False")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['organization', 'rfid_tag'], name='unique_rfid_per_organization'),
            models.UniqueConstraint(fields=['organization', 'animal_index'], name='unique_animal_index_per_organization')
        ]
        ordering = ['animal_index']

    def save(self, *args, **kwargs):
        if self.animal_index is None:
            last_index = Animal.objects.filter(organization=self.organization).aggregate(
                models.Max('animal_index')
            )['animal_index__max'] or 0
            self.animal_index = last_index + 1
        self.is_active = bool(self.experiment)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Animal {self.animal_index} (Org: {self.organization}) - RFID: {self.rfid_tag}"
    @property
    def age_in_days(self):
        if self.date_of_birth:
            try:
                age = (date.today() - self.date_of_birth).days
                print(f"Debug: Calculated Age in Days: {age}")
                return age
            except Exception as e:
                print(f"Error calculating age: {e}")
                return None
        print("Debug: Date of Birth is None")
        return None

    @classmethod
    def create_from_csv(cls, experiment, animal_index, rfid, organization):
        animal, created = cls.objects.get_or_create(
            experiment=experiment,
            animal_index=animal_index,
            organization=organization,
            defaults={'rfid_tag': rfid}
        )
        return animal

class Observation(models.Model):
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name="observations")
    category = models.CharField(max_length=100)
    score = models.PositiveIntegerField()
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    recorded_at = models.DateTimeField(default=timezone.now)  # Timestamp when created

    def __str__(self):
        return f"{self.category} for Animal {self.animal.animal_index} - Score: {self.score}"
    

class Sample(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE, null=True, blank=True)  # Allow null
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name='samples')
    sample_id = models.CharField(max_length=100)
    sample_type = models.CharField(max_length=100)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    timestamp = models.DateTimeField(default=timezone.now)  # Default to the current time

    def __str__(self):
        return f"Sample {self.sample_id} ({self.sample_type}) for Animal {self.animal.animal_index}"


class Dose(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE, null=True, blank=True)  # Allow null
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name='doses')
    drug_name = models.CharField(max_length=100, default='Unknown Drug') 
    dose = models.DecimalField(max_digits=10, decimal_places=2)
    stock_concentration = models.DecimalField(max_digits=10, decimal_places=2)
    dose_volume = models.DecimalField(max_digits=10, decimal_places=2)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    timestamp = models.DateTimeField(default=timezone.now)  # Default to the current time

    def __str__(self):
        return f"Dose for Animal {self.animal.animal_index} - Amount: {self.dose} mg"

class Comment(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE)
    animal_index = models.PositiveIntegerField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Comment by {self.user.username} on Animal {self.animal_index}"
class Attachment(models.Model):
    protocol = models.ForeignKey(Protocol, related_name="attachments", on_delete=models.CASCADE, blank=True, null=True)  # ✅ Added
    animal = models.ForeignKey(Animal, related_name='attachments', on_delete=models.CASCADE, blank=True, null=True)  # ✅ Made optional
    file = models.FileField(upload_to='attachments/')
    name = models.CharField(max_length=255, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.file.name} ({self.protocol.title if self.protocol else 'No Protocol'})"

    @property
    def file_size(self):
        if self.file:
            return self.file.size  # Size in bytes
        return 0

class WeightMeasurement(models.Model):
    rfid_assignment = models.ForeignKey('RFIDAssignment', on_delete=models.CASCADE, null=True, blank=True)
    animal = models.ForeignKey('Animal', on_delete=models.CASCADE)
    weight = models.FloatField(null=True, blank=True)
    tumor_size = models.FloatField(null=True, blank=True)
    weight_change = models.FloatField(null=True, blank=True)
    tumor_size_change = models.FloatField(null=True, blank=True)
    recorder = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(default=timezone.now)
    session_timestamp = models.DateTimeField(default=timezone.now)
    session_id = models.UUIDField(default=uuid.uuid4)

    class Meta:
        unique_together = ('animal', 'weight', 'timestamp')  # Prevents duplicates for the same weight and timestamp

    def save(self, *args, **kwargs):
        # Check for recent duplicate entries to avoid rapid re-saving of the same data
        if WeightMeasurement.objects.filter(
            animal=self.animal,
            weight=self.weight,
            timestamp__gte=self.timestamp - timedelta(seconds=1)  # Checks if a similar entry exists within 1 second
        ).exists():
            logger.info(f"Duplicate measurement prevented for {self.animal} at {self.timestamp}")
            return  # Prevent duplicate entry if one already exists within 1 second

        # Reset change fields to avoid stale data on repeated saves
        self.weight_change = 0.0
        self.tumor_size_change = 0.0

        # Weight change calculation with validation
        if self.rfid_assignment and self.rfid_assignment.initial_weight is not None and self.weight is not None:
            try:
                initial_weight = float(self.rfid_assignment.initial_weight)
                self.weight_change = ((float(self.weight) - initial_weight) / initial_weight) * 100
            except (ValueError, TypeError) as e:
                logger.error(f"Error calculating weight change for {self.animal}: {e}")

        # Tumor size change calculation with validation
        if self.rfid_assignment and self.rfid_assignment.tumor_size is not None and self.tumor_size is not None:
            try:
                initial_tumor_size = float(self.rfid_assignment.tumor_size)
                self.tumor_size_change = ((float(self.tumor_size) - initial_tumor_size) / initial_tumor_size) * 100
            except (ValueError, TypeError) as e:
                logger.error(f"Error calculating tumor size change for {self.animal}: {e}")

        # Save the entry
        super().save(*args, **kwargs)
        logger.info(f"Saved WeightMeasurement: {self.animal} with weight {self.weight} and tumor size {self.tumor_size}")

# models.py
class Collaborator(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE, related_name='collaborators')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.user.username} in {self.experiment.name}"
@receiver(post_save, sender=Collaborator)
def add_collaborator_events(sender, instance, created, **kwargs):
    if created:
        experiment = instance.experiment
        current_date = timezone.now().date()

        if experiment.weigh_in_interval and experiment.duration:
            while current_date < timezone.now().date() + timezone.timedelta(days=experiment.duration):
                CalendarEvent.objects.create(
                    user=instance.user,
                    title=f"Weigh-In for {experiment.name} (Collaborator)",
                    start_date=current_date,
                    end_date=current_date,
                    experiment=experiment,
                    color='red'
                )
                current_date += timezone.timedelta(days=experiment.weigh_in_interval)

class FriendRequest(models.Model):
    from_user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='sent_requests', on_delete=models.CASCADE)
    to_user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='received_requests', on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=[('pending', 'Pending'), ('accepted', 'Accepted'), ('declined', 'Declined')])
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.from_user.username} sent a request to {self.to_user.username} - {self.status}"


class Conversation(models.Model):
    TYPE_CHOICES = [
        ('private', 'Private'),
        ('group', 'Group'),
        ('notification', 'Notification'),
    ]

    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='private')
    name = models.CharField(max_length=255, blank=True, null=True)  # Group name
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)
    profile_picture = models.ImageField(upload_to='group_profile_pictures/', null=True, blank=True)

    # Users who muted the conversation
    mute_notifications = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='muted_conversations',
        blank=True,
        help_text="Users who have muted this conversation"
    )

    # For private conversations
    user1 = models.ForeignKey(
        User, related_name='conversations_user1', on_delete=models.CASCADE, null=True, blank=True
    )
    user2 = models.ForeignKey(
        User, related_name='conversations_user2', on_delete=models.CASCADE, null=True, blank=True
    )

    # Group members are managed through GroupMember
    members_new = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through='GroupMember',
        related_name='conversation_members_new',
        blank=True
    )

    def is_user_part_of_conversation(self, user):
        if self.type == 'private':
            return user == self.user1 or user == self.user2
        elif self.type == 'group':
            return self.group_members.filter(user=user).exists()
        return False
    
    def is_muted_for_user(self, user):
        """Check if the conversation is muted for a specific user."""
        return self.mute_notifications.filter(id=user.id).exists()

    def get_key(self):
        """Generate a unique, cacheable encryption key for the conversation."""
        cache_key = f"conversation_key_{self.id}"
        cached_key = cache.get(cache_key)
        if cached_key:
            return cached_key

        salt = f"conversation_{self.id}".encode()
        kdf = PBKDF2HMAC(
            algorithm=SHA256(),
            length=32,
            salt=salt,
            iterations=50000,  # Adjust based on performance needs
            backend=default_backend()
        )
        derived_key = kdf.derive(settings.SECRET_KEY.encode())
        cache.set(cache_key, derived_key, timeout=3600)  # Cache for 1 hour
        return derived_key 

    def __str__(self):
        if self.type == 'private':
            return f'{self.user1} and {self.user2}'
        return self.name or "Unnamed Group"

    def is_user_in_group(self, user):
        """Check if the user is part of the group conversation."""
        return GroupMember.objects.filter(conversation=self, user=user).exists()

class ConversationUser(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="conversations")
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="participants", null = True, blank = True)
    last_deleted_at = models.DateTimeField(null=True, blank=True)  # Track when the user deleted the chat


class GroupMember(models.Model):
    ROLE_CHOICES = [
        ('member', 'Member'),
        ('admin', 'Admin'),
    ]

    conversation = models.ForeignKey(
        Conversation,
        related_name='group_members',
        on_delete=models.CASCADE
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='group_memberships',
        on_delete=models.CASCADE
    )
    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default='member'
    )

    def __str__(self):
        return f'{self.user.username} in {self.conversation.name} ({self.role})'
    
class Message(models.Model):
    conversation = models.ForeignKey(Conversation, related_name='messages', on_delete=models.CASCADE)
    sender = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)  # Allow null for system messages
    content = models.TextField(blank=True, null=True)
    iv = models.BinaryField(null=True, blank=True)  # Initialization vector (optional for non-text messages)
    is_read = models.BooleanField(default=False)
    read_timestamp = models.DateTimeField(null=True, blank=True)  # When the message was read
    timestamp = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    attachment = models.FileField(upload_to='attachments/', null=True, blank=True)  # File attachments
    attachment_mime_type = models.CharField(max_length=255, null=True, blank=True)  # New field
    thumbnail = models.ImageField(upload_to='thumbnails/', blank=True, null=True)
    thumbnail_url = models.URLField(blank=True, null=True)
    event_id = models.IntegerField(null=True, blank=True)
    user_id = models.IntegerField(null=True, blank=True)
    is_system_message = models.BooleanField(default=False)  # Add a flag for system messages
    edited_at = models.DateTimeField(null=True, blank=True)  # Track the edit timestamp
    is_deleted = models.BooleanField(default=False)
    mentions = models.ManyToManyField(User, related_name='mentioned_messages', blank=True)

    def save(self, *args, **kwargs):
        if self.content:  # Encrypt only if content exists
            if isinstance(self.content, str):  # Encrypt plaintext messages
                key = self._get_key()
                iv, encrypted_content = self._encrypt_content(self.content, key)
                self.content = base64.b64encode(encrypted_content).decode('utf-8')  # Store Base64-encoded ciphertext
                self.iv = iv

        super().save(*args, **kwargs)

        # Extract and update mentions after saving the message
        mentioned_users = self.extract_mentions(self.content)
        self.mentions.set(mentioned_users)

        # Trigger thumbnail generation for video attachments
        if self.attachment and mimetypes.guess_type(self.attachment.path)[0].startswith('video/'):
            generate_video_thumbnail.delay(self.id)

    def extract_mentions(self, content):
        """Extract usernames mentioned in the message content."""
        if not content:
            return User.objects.none()
        mention_pattern = r'@(\w+)'  # Regex pattern to detect @username
        mentioned_usernames = re.findall(mention_pattern, content)
        return User.objects.filter(username__in=mentioned_usernames)
    
    def is_editable_by_user(self, user):
        """Check if the user is allowed to edit this message."""
        return self.sender == user and not self.is_deleted

    def generate_video_thumbnail(self):
        """Generate a thumbnail for video attachments."""
        if not self.attachment:
            return

        # Ensure the attachment is a video
        mime_type, _ = mimetypes.guess_type(self.attachment.path)
        if not mime_type or not mime_type.startswith('video/'):
            return

        # Create thumbnail directory if it doesn't exist
        thumbnail_dir = os.path.join(settings.MEDIA_ROOT, 'thumbnails')
        os.makedirs(thumbnail_dir, exist_ok=True)

        # Generate the thumbnail
        thumbnail_name = f'{self.id}_thumbnail.jpg'
        thumbnail_path = os.path.join(thumbnail_dir, thumbnail_name)
        try:
            clip = VideoFileClip(self.attachment.path)
            clip.save_frame(thumbnail_path, t=0.5)  # Capture a frame at 0.5 seconds
            thumbnail_url = os.path.join(settings.MEDIA_URL, 'thumbnails', thumbnail_name)
            self.thumbnail.name = os.path.relpath(thumbnail_path, settings.MEDIA_ROOT)
            self.thumbnail_url = thumbnail_url  # Save the URL
            self.save(update_fields=['thumbnail', 'thumbnail_url'])
        except Exception as e:
            logger.error(f"Error generating thumbnail for message ID {self.id}: {e}")
    
    def mark_as_read(self):
        self.is_read = True
        self.read_timestamp = now()
        self.save(update_fields=["is_read", "read_timestamp"])
    @classmethod
    def mark_conversation_as_read(cls, conversation_id, user):
        """
        Mark all unread messages in a conversation as read for a specific user.
        """
        cls.objects.filter(
            conversation_id=conversation_id,
            is_read=False
        ).exclude(sender=user).update(
            is_read=True,
            read_at=timezone.now()
        )
    def _get_key(self):
        cache_key = f"conversation_key_{self.conversation.id}"
        cached_key = cache.get(cache_key)
        if cached_key:
            return cached_key
        salt = f"conversation_{self.conversation.id}".encode()
        kdf = PBKDF2HMAC(
            algorithm=SHA256(),
            length=32,
            salt=salt,
            iterations=50000,  # Reduced iterations for better performance
            backend=default_backend()
        )
        derived_key = kdf.derive(settings.SECRET_KEY.encode())
        cache.set(cache_key, derived_key, timeout=3600)  # Cache key for 1 hour
        return derived_key

    def _encrypt_content(self, plaintext, key):
        iv = os.urandom(16)  # Generate a random IV
        cipher = Cipher(algorithms.AES(key), modes.CFB(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(plaintext.encode()) + encryptor.finalize()
        return iv, ciphertext
    
    def _decrypt_content(self, encrypted_data, iv, key):
        cipher = Cipher(algorithms.AES(key), modes.CFB(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        plaintext = decryptor.update(encrypted_data) + decryptor.finalize()
        return plaintext.decode('utf-8')

    def get_decrypted_content(self):
        try:
            if not self.content:  # No content to decrypt
                return None
            if not self.iv:
                raise ValueError("Missing IV for decryption.")
            key = self._get_key()
            ciphertext = base64.b64decode(self.content)  # Decode Base64-encoded ciphertext
            return self._decrypt_content(ciphertext, self.iv, key)
        except Exception as e:
            logger.error(f"Decryption failed for message ID {self.id}: {e}")
            return "[Decryption Error]"

    def has_attachment(self):
        return bool(self.attachment)

    def get_attachment_url(self):
        if self.attachment:
            return self.attachment.url
        return None

    def get_attachment_type(self):
        if self.attachment:
            return self.attachment.name.split('.')[-1].lower()  # Extract file extension
        return None

    def clean(self):
        if self.attachment:
            allowed_types = [
                'jpeg', 'jpg', 'png', 'gif', 'pdf', 'doc', 'docx',
                'csv', 'xls', 'xlsx', 'txt'
            ]
            file_type = self.attachment.name.split('.')[-1].lower()
            if file_type not in allowed_types:
                raise ValidationError(f"Unsupported file type: {file_type}")

            max_file_size = 10 * 1024 * 1024  # 10 MB
            if self.attachment.size > max_file_size:
                raise ValidationError("Attachment exceeds the maximum file size of 10MB.")

    def __str__(self):
        return f"Message from {self.sender.username} at {self.timestamp}"
class MessageUser(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="message_users")
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="message_users")
    deleted_at = models.DateTimeField(null=True, blank=True)  # Track when the message was deleted


class MutedConversation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)
    muted_at = models.DateTimeField(auto_now_add=True)

class Friend(models.Model):
    user1 = models.ForeignKey(User, related_name='friendship_creator_set', on_delete=models.CASCADE)
    user2 = models.ForeignKey(User, related_name='friend_set', on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=[('pending', 'Pending'), ('accepted', 'Accepted')], default='pending')

    def __str__(self):
        return f"{self.user1.username} is friends with {self.user2.username} - {self.status}"


class Invitation(models.Model):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_invitations')
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_invitations')
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE)
    role = models.CharField(max_length=50)
    status = models.CharField(max_length=50, default='pending')
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"Invitation for {self.receiver.username} to join {self.experiment.name} as {self.role}"


class InboxNotification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    organization = models.ForeignKey('Organization', on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=255, null=True, blank=True)
    sender_name = models.CharField(max_length=255, blank=True)  # Retain only one instance
    message = models.TextField()
    event_invitation = models.ForeignKey(EventInvitation, on_delete=models.SET_NULL, null=True, blank=True)
    experiment = models.ForeignKey('Experiment', on_delete=models.CASCADE, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    from_admin = models.BooleanField(default=False)

    # Generic relation to link notifications to any model
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    related_object = GenericForeignKey('content_type', 'object_id')

    # Priority or category for notifications
    PRIORITY_CHOICES = [
        ('info', 'Information'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ]
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='info')

    def __str__(self):
        return f"Notification for {self.user.username}: {self.title or 'No Title'}"

    def mark_as_read(self):
        """
        Mark the message as read and set the read_at timestamp.
        """
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()  # Use Django's timezone for consistency
            self.save(update_fields=['is_read', 'read_at'])

    def respond_to_invitation(self, response):
        """
        Handle responses to linked invitations (e.g., accept or decline).
        """
        if self.event_invitation:
            if response == 'accepted':
                self.event_invitation.accept()
            elif response == 'declined':
                self.event_invitation.decline()
            self.mark_as_read()
            
class UserSignature(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='signature')
    signature_image = models.ImageField(upload_to='signatures/', null=True, blank=True)
    signature_text = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.signature_text:  # Assign a random signature text if not provided
            self.signature_text = self.generate_random_signature()
        super().save(*args, **kwargs)

    def generate_random_signature(self):
        # Generate a random signature string
        return ''.join(random.choices(string.ascii_letters + string.digits, k=10))

    def __str__(self):
        return f"Signature of {self.user.username}"


class PDFTemplate(models.Model):
    name = models.CharField(max_length=255)
    organization = models.ForeignKey("Organization", on_delete=models.CASCADE)
    uploaded_pdf = models.FileField(upload_to="static/pdfs/")  # ✅ Save inside `static/pdfs/`
    uploaded_by = models.ForeignKey("User", on_delete=models.CASCADE, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def file_path(self):
        """Return the correct full file path."""
        return os.path.join(settings.BASE_DIR, self.uploaded_pdf.name)  # ✅ Correct static path



def get_default_user():
    """Returns the first available user or creates a new admin user."""
    return User.objects.order_by("id").first().id  # ✅ Picks first user



class FormPackage(models.Model):
    PACKAGE_TYPE_CHOICES = [
        ('rr_budget', 'RR Budget Only'),
        ('sf424', 'SF-424 Only'),
        ('combined', 'Combined (RR Budget + SF-424)'),
    ]

    name = models.CharField(max_length=255)
    package_type = models.CharField(max_length=20, choices=PACKAGE_TYPE_CHOICES)
    
    
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)


    def __str__(self):
        return f"{self.name} ({self.get_package_type_display()})"

class PackageForm(models.Model):
    package = models.ForeignKey(FormPackage, on_delete=models.CASCADE, related_name="package_forms")
    pdf_template = models.ForeignKey("PDFTemplate", on_delete=models.CASCADE, null=True, blank=True)
    html_template_name = models.CharField(max_length=255, null=True, blank=True)  # Allow HTML templates
    order = models.PositiveIntegerField(default=0)  # Order within the package

    class Meta:
        ordering = ["order"]

    def __str__(self):
        if self.pdf_template:
            return f"{self.package.name} - {self.pdf_template.name} (PDF)"
        elif self.html_template_name:
            return f"{self.package.name} - {self.html_template_name} (HTML Form)"
        return f"{self.package.name} - Unknown Form"

class AdminCreatedForm(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(default='', blank=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, default=1)  # Use a valid Organization ID here
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(default=now)
    template = models.ForeignKey(PDFTemplate, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name

class FormField(models.Model):
    TEXT = 'text'
    TEXTAREA = 'textarea'
    DATE = 'date'
    YES_NO = 'yes_no'
    MULTIPLE_CHOICE = 'multiple_choice'

    FIELD_TYPES = [
        (TEXT, 'Text Input'),
        (TEXTAREA, 'Text Area'),
        (DATE, 'Date'),
        (YES_NO, 'Yes/No Question'),
        (MULTIPLE_CHOICE, 'Multiple Choice')
    ]

    form = models.ForeignKey(AdminCreatedForm, related_name='fields', on_delete=models.CASCADE)
    template = models.ForeignKey(PDFTemplate, related_name='form_fields', on_delete=models.CASCADE, null=True, blank=True)  # Adding this relation to PDFTemplate
    field_label = models.CharField(max_length=255)
    field_type = models.CharField(max_length=50, choices=FIELD_TYPES)
    choices = models.TextField(blank=True, null=True)  # Store comma-separated multiple choice options
    is_required = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.field_label} ({self.get_field_type_display()})"


class UploadedPDF(models.Model):
    name = models.CharField(max_length=255)
    pdf_file = models.FileField(upload_to="uploaded_pdfs/")
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
class PDFField(models.Model):
    pdf_template = models.ForeignKey(PDFTemplate, on_delete=models.CASCADE, related_name="fields")
    field_name = models.CharField(max_length=255)
    field_type = models.CharField(
        max_length=20,
        choices=[("text", "Text"), ("checkbox", "Checkbox"), ("radio", "Radio")]
    )
    options = models.TextField(blank=True, null=True)  # Stores choices for radio buttons
    required = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.field_name} ({self.field_type})"
class PDFFieldMapping(models.Model):
    pdf_template = models.ForeignKey(PDFTemplate, on_delete=models.CASCADE, related_name='field_mappings')
    form_field = models.ForeignKey(FormField, on_delete=models.CASCADE)  
    x = models.FloatField(default=0.0)  # X-coordinate of the top-left corner
    y = models.FloatField(default=0.0)  # Y-coordinate of the top-left corner
    width = models.FloatField(default=0.0)  # Width of the editable area
    height = models.FloatField(default=0.0) 
    field_name = models.CharField(max_length=255)  # This corresponds to the PDF field name
    is_editable = models.BooleanField(default=False)  # Whether the field is editable
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.field_name} ({'Editable' if self.is_editable else 'Non-editable'})"


class UserFilledForm(models.Model):
    """Model representing a form that a user has filled out."""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    form = models.ForeignKey(AdminCreatedForm, on_delete=models.CASCADE)
    signed_date = models.DateTimeField(auto_now_add=True)
    file_path = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.form.name} signed by {self.user.username}"

class AdminForm(models.Model):
    """General forms created by the admin (can be customized in nature)."""
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    requires_signature = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class SignedAdminForm(models.Model):
    """Model for when a user signs an Admin-created form."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)  # Allow null for anonymous submissions
    admin_form = models.ForeignKey(AdminForm, on_delete=models.CASCADE)
    signed_at = models.DateTimeField(auto_now_add=True)
    file_path = models.CharField(max_length=500)
    reviewed = models.BooleanField(default=False)
    def __str__(self):
        return f"{self.admin_form.title} signed by {self.user.username if self.user else 'Anonymous'}"

class SignedForm(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)  # User can be null for anonymous submissions
    form = models.ForeignKey(AdminCreatedForm, on_delete=models.CASCADE)
    file_path = models.FileField(upload_to='signed_forms/')
    signed_date = models.DateTimeField(auto_now_add=True)
    is_anonymous = models.BooleanField(default=False)  # Field for anonymous submissions
    is_high_importance = models.BooleanField(default=False)  # Field for high importance submissions

    def __str__(self):
        # If the user is None, show "Anonymous" instead of the username
        return f"{self.form.name} signed by {'Anonymous' if self.is_anonymous else self.user.username}"

    def save(self, *args, **kwargs):
        # Automatically set is_anonymous to True if user is None
        if self.user is None:
            self.is_anonymous = True
        super(SignedForm, self).save(*args, **kwargs)


class AdminPDFTemplate(models.Model):
    name = models.CharField(max_length=255)
    pdf_file = models.FileField(upload_to='pdf_templates/')
    created_at = models.DateTimeField(auto_now_add=True)


class EventCompletion(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(CalendarEvent, on_delete=models.CASCADE)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

class Task(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)  # Start date of the task
    end_date = models.DateField(null=True, blank=True)  # End date of the task
    days_of_week = models.JSONField(default=list, blank=True)  # Selected days (e.g., ["Monday", "Wednesday"])
    recurrence_days = models.JSONField(default=list)  # Days of the week
    recurrence_interval = models.IntegerField(default=1)  # Interval for recurrence
    recurrence_frequency = models.CharField(max_length=10, choices=[('weeks', 'Weeks'), ('months', 'Months')], default='weeks')
    assigned_by = models.ForeignKey(User, related_name='assigned_tasks', on_delete=models.CASCADE)
    assignees = models.ManyToManyField(User, related_name='tasks')
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    in_progress = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    requires_individual_completion = models.BooleanField(default=False)  # New field to track task type
    completed_by = models.ManyToManyField(User, related_name='completed_tasks', blank=True)  # Track who completed

    def __str__(self):
        return f"{self.title} ({'Completed' if self.is_completed else 'Pending'})"

    def mark_in_progress(self):
        self.in_progress = True
        self.is_completed = False  # Reset completion status if marked in progress
        self.completed_at = None  # Clear completed timestamp
        self.save()

    def mark_completed(self):
        """Mark the task as fully completed (applies when no individual completion is required)."""
        self.is_completed = True
        self.completed_at = timezone.now()
        self.save()

    def mark_completed_by_user(self, user):
        """
        Mark task as completed by a specific user.
        Handles both individual and group completion requirements.
        """
        if user in self.assignees.all():
            self.completed_by.add(user)
            self.save()

        # Check if task should be marked as fully completed
        if not self.requires_individual_completion:
            self.is_completed = True
            self.completed_at = timezone.now()
        elif self.completed_by.count() == self.assignees.count():
            # All assignees have completed the task
            self.is_completed = True
            self.completed_at = timezone.now()

        self.save()

    def completion_progress(self):
        """
        Returns a tuple representing the completion progress:
        - Number of users who have completed the task.
        - Total number of assignees.
        """
        return (self.completed_by.count(), self.assignees.count())

    def is_fully_completed(self):
        """
        Helper method to check if a task is fully completed.
        """
        if self.requires_individual_completion:
            return self.completed_by.count() == self.assignees.count()
        return self.is_completed

class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    from_admin = models.BooleanField(default=False)

    def __str__(self):
        return f"Notification to {self.user.username} - {self.message[:50]}"


class SF424Field(models.Model):
    name = models.CharField(max_length=255)
    field_type = models.CharField(max_length=50, choices=[("string", "String"), ("date", "Date"), ("number", "Number")])
    options = models.JSONField(null=True, blank=True)  # Stores dropdown options


class SF424Form(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    organization = models.ForeignKey("Organization", on_delete=models.CASCADE)
    
    # Sample fields (add more based on SF-424 requirements)
    submission_type = models.CharField(max_length=100, choices=[
        ("preapplication", "Preapplication"),
        ("application", "Application"),
        ("correction", "Changed/Corrected Application")
    ])
    date_submitted = models.DateField()
    applicant_identifier = models.CharField(max_length=255, blank=True, null=True)
    state_application_identifier = models.CharField(max_length=255, blank=True, null=True)
    federal_identifier = models.CharField(max_length=255, blank=True, null=True)

    # Contact Person Information
    contact_first_name = models.CharField(max_length=100)
    contact_last_name = models.CharField(max_length=100)
    contact_email = models.EmailField()
    
    # Estimated Funding
    total_federal_funds_requested = models.DecimalField(max_digits=15, decimal_places=2)
    total_non_federal_funds = models.DecimalField(max_digits=15, decimal_places=2)

    date_created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"SF-424 Submission ({self.user.username} - {self.date_submitted})"

class SF424Submission(models.Model):
    submission_type = models.CharField(max_length=100)
    federal_entity_identifier = models.CharField(max_length=100, blank=True, null=True)
    agency_routing_number = models.CharField(max_length=100, blank=True, null=True)
    previous_tracking_id = models.CharField(max_length=100, blank=True, null=True)
    consolidated_app = models.BooleanField(default=False)
    explanation = models.TextField(blank=True, null=True)
    date_submitted = models.DateField()
    applicant_identifier = models.CharField(max_length=100, blank=True, null=True)
    state_use_only = models.TextField(blank=True, null=True)
    legal_name = models.CharField(max_length=255)
    ein_tin = models.CharField(max_length=50, blank=True, null=True)
    duns_number = models.CharField(max_length=50, blank=True, null=True)
    address_street1 = models.CharField(max_length=255)
    address_street2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=20)
    contact_name = models.CharField(max_length=255, default = None)
    contact_email = models.EmailField(default = None)
    contact_phone = models.CharField(max_length=50)
    date_created = models.DateTimeField(default=now, editable=False)

    def __str__(self):
        return f"Submission by {self.legal_name} on {self.date_submitted}"


class PerformanceSiteLocation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)  # User filling the form
    form_package = models.ForeignKey(FormPackage, on_delete=models.CASCADE)  # Link to package
    identifier = models.PositiveIntegerField(default =1)  # "Project/Performance Site Location X"
    
    is_individual_submission = models.BooleanField(default=False)  # Checkbox
    organization_name = models.CharField(max_length=255, blank=True, null=True)
    uei = models.CharField(max_length=50, blank=True, null=True)
    
    street1 = models.CharField(max_length=255)
    street2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100)
    county = models.CharField(max_length=100, blank=True, null=True)
    
    state = models.CharField(max_length=100, blank=True, null=True)  # Required if country is US
    province = models.CharField(max_length=100, blank=True, null=True)  # If not US
    country = models.CharField(max_length=100)
    
    zip_code = models.CharField(max_length=20, blank=True, null=True)  # Required if in US
    congressional_district = models.CharField(max_length=20, blank=True, null=True)  # Required if in US

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Site {self.identifier}: {self.organization_name or 'Individual'}"

class RROtherInformation(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    proprietary_info = models.BooleanField(default=False)
    environmental_impact = models.BooleanField(default=False)
    historic_properties = models.BooleanField(default=False)
    human_subjects = models.CharField(max_length=10, choices=[("yes", "Yes"), ("no", "No")], blank=True)
    vertebrate_animals = models.CharField(max_length=10, choices=[("yes", "Yes"), ("no", "No")], blank=True)
    international_collaboration = models.CharField(
        max_length=20, choices=[("no", "No"), ("yes_country", "Yes, with a specific country"), ("yes_global", "Yes, globally")], blank=True
    )
    uploaded_file = models.FileField(upload_to="rr_other_info/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class BudgetForm(models.Model):
    pdf_file = models.FileField(upload_to="pdfs/")
    organization = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Budget Form - {self.organization}"
    
class BudgetPeriod(models.Model):
    BUDGET_TYPE_CHOICES = [
        ('project', 'Project'),
        ('subaward', 'Subaward / Consortium'),
    ]

    period_number = models.PositiveIntegerField(choices=[(i, f"Budget Period {i}") for i in range(1, 6)])
    organization = models.ForeignKey('Organization', on_delete=models.CASCADE, related_name='budget_periods')
    uei = models.CharField(max_length=50, verbose_name="Unique Entity Identifier (UEI)")
    budget_type = models.CharField(max_length=20, choices=BUDGET_TYPE_CHOICES, default='project')
    start_date = models.DateField(default=now)
    end_date = models.DateField()

    class Meta:
        unique_together = ('organization', 'period_number')  # Ensure one period per org

    def __str__(self):
        return f"RESEARCH & RELATED BUDGET - Budget Period {self.period_number} ({self.organization.name})"


class SeniorKeyPerson(models.Model):
    PREFIX_CHOICES = [
        ('Mr.', 'Mr.'), ('Ms.', 'Ms.'), ('Dr.', 'Dr.'),
        ('Prof.', 'Prof.'), ('Hon.', 'Hon.')
    ]
    
    SUFFIX_CHOICES = [
        ('Jr.', 'Jr.'), ('Sr.', 'Sr.'), ('III', 'III'), ('IV', 'IV')
    ]
    
    budget_period = models.ForeignKey('BudgetPeriod', on_delete=models.CASCADE, related_name="senior_key_persons")
    prefix = models.CharField(max_length=10, choices=PREFIX_CHOICES, blank=True, null=True)
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100)
    suffix = models.CharField(max_length=10, choices=SUFFIX_CHOICES, blank=True, null=True)

    base_salary = models.DecimalField(max_digits=12, decimal_places=2)
    calendar_months = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    academic_months = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    summer_months = models.DecimalField(max_digits=4, decimal_places=2, default=0)

    requested_salary = models.DecimalField(max_digits=12, decimal_places=2)
    fringe_benefits = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Auto-calculated field: Requested Salary + Fringe Benefits
    funds_requested = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    project_role = models.CharField(max_length=255)

    def save(self, *args, **kwargs):
        """Automatically calculate Funds Requested."""
        self.funds_requested = self.requested_salary + self.fringe_benefits
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.prefix} {self.first_name} {self.last_name} - {self.project_role} ({self.budget_period})"
class OtherPersonnel(models.Model):
    ROLE_CHOICES = [
        ('post_doc', 'Post Doctoral Associates'),
        ('grad_student', 'Graduate Students'),
        ('undergrad_student', 'Undergraduate Students'),
        ('clerical', 'Secretarial/Clerical'),
    ]

    budget_period = models.ForeignKey(BudgetPeriod, on_delete=models.CASCADE, related_name="other_personnel")
    role = models.CharField(max_length=50, choices=ROLE_CHOICES)
    num_personnel = models.PositiveIntegerField(default=1)
    calendar_months = models.FloatField(default=0.0)
    academic_months = models.FloatField(default=0.0)
    summer_months = models.FloatField(default=0.0)
    requested_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    fringe_benefits = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    @property
    def total_funds_requested(self):
        return self.requested_salary + self.fringe_benefits

    def __str__(self):
        return f"{self.get_role_display()} - {self.budget_period}"

class Project(models.Model):
    name = models.CharField(max_length=100)
    project_identifier = models.CharField(max_length=20, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    principal_investigator = models.CharField(max_length=100, null=True, blank=True)
    admin_unit = models.CharField(max_length=100, null=True, blank=True)
    sponsor = models.CharField(max_length=100, null=True, blank=True)
    prime_sponsor = models.CharField(max_length=100, null=True, blank=True)
    sponsor_deadline = models.DateField(null=True, blank=True)
    total_sponsor_costs = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    project_start_date = models.DateField(null=True, blank=True)
    project_end_date = models.DateField(null=True, blank=True)
    instrument_type = models.CharField(max_length=100, null=True, blank=True)


    def generate_unique_identifier(self, org_id):
        while True:
            random_number = random.randint(10000, 99999)
            identifier = f"{org_id}-{random_number}"
            if not Project.objects.filter(project_identifier=identifier).exists():
                return identifier

    def save(self, *args, **kwargs):
        if not self.project_identifier:
            # Directly access org_id from an instance attribute or some other source
            self.project_identifier = self.generate_unique_identifier(self.org_id)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.project_identifier})"
    
class Opportunity(models.Model):
    number = models.CharField(max_length=20)
    proposal_name = models.CharField(max_length=100)
    principal_investigator = models.CharField(max_length=100)
    organization = models.CharField(max_length=100)
    number_of_periods = models.IntegerField(choices=[(i, str(i)) for i in range(1, 6)])
    due_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    form_package = models.ForeignKey(FormPackage, on_delete=models.CASCADE, null=True, blank=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True)
    is_added = models.BooleanField(default=False)  # New field to mark if added
   


    def __str__(self):
        return f"{self.number} - {self.proposal_name}"


class SubmittedPackage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    org_id = models.IntegerField()
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True)  # New field
    package_id = models.IntegerField()
    submission_name = models.CharField(max_length=255)
    submission_date = models.DateTimeField(auto_now_add=True)
    # Store SF-424 and RR Budget data as JSON
    sf424_data = models.JSONField(default=dict)
    budget_periods = models.JSONField(default=list)
    cumulative_totals = models.JSONField(default=dict)
    sflll_attachment = models.FileField(upload_to='uploads/', null=True, blank=True)
    pre_application_attachment = models.FileField(upload_to='uploads/', null=True, blank=True)
    cover_letter_attachment = models.FileField(upload_to='uploads/', null=True, blank=True)
    is_draft = models.BooleanField(default=False)  # New field to track draft status

    def __str__(self):
        return f"{self.submission_name} - {self.submission_date}"

