import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser, User
from django.contrib.postgres.fields import ArrayField  # or use JSONField if on older Django versions
from django.contrib.auth import get_user_model
from django.utils.text import slugify
import base64
from django.conf import settings
from django.core.cache import cache
from dashboard.generate_key import encrypt_message, decrypt_message, get_conversation_key
from dashboard.generate_key import encrypt_content
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Max, JSONField, Q
import os
from django.core.exceptions import ValidationError
from cryptography.fernet import Fernet
from pytz import common_timezones 
import random
import string
import datetime
from datetime import timedelta
import logging
logger = logging.getLogger(__name__)
class Organization(models.Model):
    name = models.CharField(max_length=255, unique=True)
    address = models.TextField(blank=True, null=True)
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
        ('admin', 'Admin'),
        ('officer', 'Officer'),
        ('researcher', 'Researcher'),
        ('viewer', 'Viewer'),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='viewer')
    profile_banner = models.ImageField(upload_to='profile_banners/', blank=True, null=True)
    institution = models.CharField(max_length=255, blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    timezone = models.CharField(max_length=50, default='EST')
    is_organization_admin = models.BooleanField(default=False)

    def __str__(self):
        return self.username

    def save(self, *args, **kwargs):
        if self.first_name and self.last_name and not self.profile_picture:
            initials = f"{self.first_name[0]}{self.last_name[0]}".upper()
            self.profile_picture = self.generate_initials_profile_picture(initials)
        super().save(*args, **kwargs)

    def save(self, *args, **kwargs):
        if self.first_name and self.last_name and not self.profile_picture:
            initials = f"{self.first_name[0]}{self.last_name[0]}".upper()
            self.profile_picture = self.generate_initials_profile_picture(initials)
        super().save(*args, **kwargs)

    def generate_initials_profile_picture(self, initials):
        img_width = 25  # Width of the portrait
        img_height = 250  # Height of the portrait (taller for a "portrait")
        background_color = (0, 0, 0)  # Black background
        text_color = (255, 255, 255)  # White text for initials

    # Create a blank image
        img = Image.new('RGB', (img_width, img_height), color=background_color)
        d = ImageDraw.Draw(img)

    # Load the font
        font_path = os.path.join('static', 'fonts', 'LiberationSans-Regular.ttf')
        try:
            font_size = int(img_height * 0.15)  # Adjust font size to 30% of image height
            fnt = ImageFont.truetype(font_path, font_size)
        except IOError:
            fnt = ImageFont.load_default()

    # Calculate the size and position of the initials for centering
        text_bbox = d.textbbox((0, 0), initials, font=fnt)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        position = ((img_width - text_width) // 2, (img_height - text_height) // 2)

    # Draw the initials
        d.text(position, initials, font=fnt, fill=text_color)

    # Save the image
        image_path = f"profile_pictures/{slugify(initials)}_portrait.png"
        img.save(os.path.join('media/', image_path))

        return image_path
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
    tumor_volume_warning = models.FloatField(null=True, blank=True, help_text="Warning threshold for tumor volume in mm³")
    tumor_volume_removal = models.FloatField(null=True, blank=True, help_text="Removal threshold for tumor volume in mm³")
    

    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    number_of_animals = models.IntegerField(null=True, blank=True)
    number_of_groups = models.PositiveIntegerField(default=1)
    max_per_cage = models.PositiveIntegerField(default=1)
    investigators = models.CharField(max_length=255, blank=True, null=True)
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
    
class UserAction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)  # Add this line
    action = models.CharField(max_length=255)  # e.g., "Signed Document"
    timestamp = models.DateTimeField(auto_now_add=True)
    additional_info = models.TextField(blank=True, null=True)
    typed_signature = models.CharField(max_length=255, blank=True, null=True)  # User's typed signature
    unique_signature = models.CharField(max_length=255, blank=True, null=True)  # System-generated unique signature

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

    # New field to link to Experiment
    experiment = models.ForeignKey('Experiment', on_delete=models.CASCADE, null=True, blank=True, related_name="calendar_events")

    # Recurrence fields
    is_recurring = models.BooleanField(default=False)
    recurrence_interval = models.IntegerField(null=True, blank=True)
    recurrence_frequency = models.CharField(max_length=10, choices=[('week', 'Week'), ('month', 'Month')], null=True, blank=True)
    recurrence_days = models.JSONField(default=list, blank=True)
    recurrence_end_type = models.CharField(max_length=10, choices=[('never', 'Never'), ('on', 'On Date'), ('after', 'After Occurrences')], null=True, blank=True)
    recurrence_end_date = models.DateTimeField(null=True, blank=True)
    recurrence_occurrences = models.IntegerField(null=True, blank=True)

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
    animal = models.ForeignKey(Animal, related_name='attachments', on_delete=models.CASCADE)
    file = models.FileField(upload_to='attachments/')
    description = models.CharField(max_length=255, blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.file.name} ({self.animal.animal_index})"
    
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
    user1 = models.ForeignKey(User, related_name='conversations_user1', on_delete=models.CASCADE, null=True, blank=True)
    user2 = models.ForeignKey(User, related_name='conversations_user2', on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=255, blank=True, null=True)  # Group chat name
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)

    profile_picture = models.ImageField(upload_to='group_profile_pictures/', null=True, blank=True)

    def __str__(self):
        return self.name if self.type == 'group' else f'{self.user1} and {self.user2}'


class ConversationUser(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="conversations")
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="participants")
    last_deleted_at = models.DateTimeField(null=True, blank=True)  # Track when the user deleted the chat
    
class GroupMember(models.Model):
    conversation = models.ForeignKey(Conversation, related_name='groupmember', on_delete=models.CASCADE)
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    def __str__(self):
        return f'{self.user.username} in {self.conversation.name}'
class Message(models.Model):
    conversation = models.ForeignKey(Conversation, related_name='messages', on_delete=models.CASCADE)
    sender = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)  # Allow null for system messages
    content = models.TextField(blank=True, null=True)
    iv = models.BinaryField(null=True, blank=True)  # Initialization vector (optional for non-text messages)
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    attachment = models.FileField(upload_to='attachments/', null=True, blank=True)  # File attachments
    attachment_mime_type = models.CharField(max_length=255, null=True, blank=True)  # New field
    event_id = models.IntegerField(null=True, blank=True)
    user_id = models.IntegerField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.content:  # Encrypt only if content exists
            if isinstance(self.content, str):  # Only encrypt plaintext
                key = self._get_key()
                iv, encrypted_content = self._encrypt_content(self.content, key)
                self.content = encrypted_content
                self.iv = iv  # Save IV separately
        else:
            self.iv = None  # Clear IV if no content exists

        super(Message, self).save(*args, **kwargs)

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
        iv = os.urandom(16)
        cipher = Cipher(algorithms.AES(key), modes.CFB(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(plaintext.encode()) + encryptor.finalize()
        return iv, base64.b64encode(ciphertext).decode('utf-8')


    
    def _decrypt_content(self, encrypted_data, iv, key):
        cipher = Cipher(algorithms.AES(key), modes.CFB(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        plaintext = decryptor.update(base64.b64decode(encrypted_data)) + decryptor.finalize()
        return plaintext.decode('utf-8')

    def get_decrypted_content(self):
        try:
            if not self.content:  # No text content to decrypt
                return None
            if not self.iv:
                raise ValueError("Missing IV for decryption.")
            key = self._get_key()
            return self._decrypt_content(self.content, self.iv, key)
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
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    event_invitation = models.ForeignKey(EventInvitation, on_delete=models.SET_NULL, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    from_admin = models.BooleanField(default=False)
    experiment = models.ForeignKey('Experiment', on_delete=models.CASCADE, null=True, blank=True)
    sender_name = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"Notification for {self.user.username}"

    def mark_as_read(self):
        self.is_read = True
        self.save()

    def respond_to_invitation(self, response):
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
    description = models.TextField()
    uploaded_pdf = models.FileField(upload_to='pdf_templates/')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    # Add this field to store the editable fields as JSON
    editable_fields = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.name
# Ensure FormField is defined before PDFFieldMapping

class AdminCreatedForm(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(default='', blank=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, default=1)  # Use a valid Organization ID here
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
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
    frequency = models.IntegerField(default=1)  # Ensure this exists
    duration = models.IntegerField(default=1)   # Ensure this exists
    description = models.TextField(null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    assigned_by = models.ForeignKey(User, related_name='assigned_tasks', on_delete=models.CASCADE)
    assignees = models.ManyToManyField(User, related_name='tasks')
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    in_progress = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # You could add a status field to track task progress

    def __str__(self):
        return f"{self.title} - Assigned by {self.assigned_by}"

    def mark_in_progress(self):
        self.in_progress = True
        self.save()

    def mark_completed(self):
        self.is_completed = True
        self.completed_at = timezone.now()
        self.save()


    def __str__(self):
        return f"{self.title} ({'Completed' if self.is_completed else 'Pending'})"
    

class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    from_admin = models.BooleanField(default=False)

    def __str__(self):
        return f"Notification to {self.user.username} - {self.message[:50]}"
