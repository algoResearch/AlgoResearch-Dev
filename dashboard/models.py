from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.text import slugify
from django.conf import settings
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont
from django.db.models.signals import post_save
from django.dispatch import receiver
import os
import uuid

class User(AbstractUser):
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True)
    institution = models.CharField(max_length=100, blank=True, null=True)
    role = models.CharField(max_length=100, blank=True, null=True)
    location = models.CharField(max_length=100, blank=True, null=True)
    is_organization_admin = models.BooleanField(default=False)


    def save(self, *args, **kwargs):
        if self.first_name and self.last_name and not self.profile_picture:
            initials = f"{self.first_name[0]}{self.last_name[0]}".upper()
            self.profile_picture = self.generate_initials_profile_picture(initials)
        super().save(*args, **kwargs)


    def generate_initials_profile_picture(self, initials):
        img_size = 1000  # Set the size of the image
        img = Image.new('RGB', (img_size, img_size), color=(73, 109, 137))  # Background color
        d = ImageDraw.Draw(img)

    # Define the path to the font
        font_path = os.path.join('static', 'fonts', 'LiberationSans-Regular.ttf')

        try:
            # Use a large font size (e.g., 75% of the image size)
            font_size = int(img_size * 0.5)
            fnt = ImageFont.truetype(font_path, font_size)
        except IOError:
            # Fallback to a default font with a manually specified size
            fnt = ImageFont.load_default()

    # Calculate text size and position to center the initials
        text_bbox = d.textbbox((0, 0), initials, font=fnt)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

    # Center the initials
        position = ((img.size[0] - text_width) // 2, (img.size[1] - text_height) // 2)

    # Draw the initials in white
        d.text(position, initials, font=fnt, fill=(255, 255, 255))

    # Save the image
        image_path = f"profile_pictures/{slugify(initials)}.png"
        img.save(os.path.join('media/', image_path))

        return image_path

class Experiment(models.Model):
    name = models.CharField(max_length=255)
    number_of_animals = models.PositiveIntegerField()
    number_of_groups = models.PositiveIntegerField(default=1)
    max_per_cage = models.PositiveIntegerField(default=1)
    investigators = models.CharField(max_length=255)
    drug = models.CharField(max_length=255, blank=True, null=True)
    strain = models.CharField(max_length=255, blank=True, null=True)
    drug_list = models.ManyToManyField('Drug', related_name='experiments', blank=True)
    strain_list = models.ManyToManyField('Strain', related_name='experiments', blank=True)
    ended = models.BooleanField(default=False)
    rfid_required = models.BooleanField(default=False)
    weight_schedule = models.BooleanField(default=False)
    weigh_in_interval = models.PositiveIntegerField(blank=True, null=True)
    experiment_duration = models.PositiveIntegerField(blank=True, null=True)
    duration = models.PositiveIntegerField(blank=True, null=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    monitor_weight = models.BooleanField(default=False)
    monitor_tumor = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)  # Default to the current time

    @classmethod
    def from_dict(cls, data, user):
        """Create or update an Experiment instance from a dictionary."""
        experiment, created = cls.objects.update_or_create(
            name=data['name'],
            defaults={
                'number_of_animals': data.get('number_of_animals', 0),
                'number_of_groups': data.get('number_of_groups', 1),
                'max_per_cage': data.get('max_per_cage', 1),
                'rfid_required': data.get('rfid_required', False),
                'weight_schedule': data.get('weight_schedule', False),
                'weigh_in_interval': data.get('weigh_in_interval'),
                'experiment_duration': data.get('experiment_duration'),
                'duration': data.get('duration'),
                'owner': user
            }
        )
        return experiment
    def __str__(self):
        return self.name


    def __str__(self):
        return self.name
    
class UserAction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    action = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)
    additional_info = models.TextField(blank=True, null=True)  # To store any extra details (like experiment name)

    def __str__(self):
        return f'{self.user.username} - {self.action}'
    

class Drug(models.Model):
    name = models.CharField(max_length=255)
    experiment = models.ForeignKey('Experiment', related_name='drug_set', on_delete=models.CASCADE)

    def __str__(self):
        return self.name


class Strain(models.Model):
    name = models.CharField(max_length=255)
    experiment = models.ForeignKey('Experiment', related_name='strain_set', on_delete=models.CASCADE)

    def __str__(self):
        return self.name



class CalendarEvent(models.Model):
    title = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE, null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    color = models.CharField(max_length=10, default='blue')

    def __str__(self):
        return self.title


class Animal(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE)
    animal_index = models.PositiveIntegerField()  # Ensure unique within the experiment
    rfid_tag = models.CharField(max_length=100, blank=True, null=True)  # Allow RFID to be blank initially
    tail = models.CharField(max_length=255, blank=True, null=True)
    ear = models.CharField(max_length=255, blank=True, null=True)
    tag = models.CharField(max_length=255, blank=True, null=True)
    donor = models.CharField(max_length=255, blank=True, null=True)
    tracking_date = models.DateField(null=True, blank=True)
    age = models.IntegerField(null=True, blank=True)
    sex = models.CharField(max_length=10, blank=True, null=True)
    species = models.CharField(max_length=100, blank=True, null=True)
    strain = models.CharField(max_length=100, blank=True, null=True)
    drug = models.CharField(max_length=100, blank=True, null=True)
    strains = models.ManyToManyField(Strain, blank=True, related_name='animals')
    drugs = models.ManyToManyField(Drug, blank=True, related_name='animals')
    removed = models.BooleanField(default=False)

    class Meta:
        unique_together = ('experiment', 'animal_index')  # Ensure uniqueness

    def __str__(self):
        return f"Animal {self.rfid_tag} in Experiment {self.experiment.name}"

    @classmethod
    def create_from_csv(cls, experiment, animal_index, rfid):
        """
        Helper method to create an Animal from CSV data.
        """
        animal, created = cls.objects.get_or_create(
            experiment=experiment,
            animal_index=int(animal_index),
            defaults={'rfid_tag': rfid}
        )
        return animal

class Observation(models.Model):
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name='observations')
    category = models.CharField(max_length=100)
    score = models.IntegerField()
    recorded_at = models.DateTimeField(default=timezone.now)  # Timestamp when created
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.category} for Animal {self.animal.animal_index} - Score: {self.score}"
    


class Sample(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE)
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name='samples')
    sample_id = models.CharField(max_length=100)
    sample_type = models.CharField(max_length=100)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    timestamp = models.DateTimeField(default=timezone.now)  # Default to the current time


    def __str__(self):
        return f"Sample {self.sample_id} ({self.sample_type}) for Animal {self.animal.name}"
    
class Dose(models.Model):
    experiment = models.ForeignKey('Experiment', on_delete=models.CASCADE)
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name='doses')
    drug_name = models.CharField(max_length=100, default='Unknown Drug') 
    dose = models.DecimalField(max_digits=10, decimal_places=2)
    stock_concentration = models.DecimalField(max_digits=10, decimal_places=2)
    dose_volume = models.DecimalField(max_digits=10, decimal_places=2)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    timestamp = models.DateTimeField(default=timezone.now)  # Default to the current time


    def __str__(self):
        return f"Dose for Animal {self.animal.name} - Amount: {self.dose} mg"
    
class Comment(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE)
    animal_index = models.PositiveIntegerField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Comment by {self.user.username} on Animal {self.animal_index}"

class RFIDAssignment(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE)
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name='rfid_assignments')  # Add related_name for easy querying
    rfid = models.CharField(max_length=100, unique=True)
    weight = models.FloatField(null=True, blank=True)
    initial_weight = models.FloatField(null=True, blank=True)
    tumor_size = models.FloatField(null=True, blank=True)
    removed = models.BooleanField(default=False)
    cage_number = models.PositiveIntegerField(default=1)
    initial_weight_date = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ('experiment', 'animal')

    def __str__(self):
        return f"RFID Assignment for Animal {self.animal.id} in Experiment {self.experiment.name}"
class WeightMeasurement(models.Model):
    rfid_assignment = models.ForeignKey('RFIDAssignment', on_delete=models.CASCADE, null=True, blank=True)
    animal = models.ForeignKey('Animal', on_delete=models.CASCADE)
    weight = models.FloatField()
    tumor_size = models.FloatField(null=True, blank=True)
    weight_change = models.FloatField(null=True, blank=True)
    tumor_size_change = models.FloatField(null=True, blank=True)  # Store the change in tumor size
    recorder = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(default=timezone.now)
    session_timestamp = models.DateTimeField(default=timezone.now)  # Use the timestamp when the session started
    session_id = models.UUIDField(default=uuid.uuid4)  # Unique identifier for each weighing session

    def save(self, *args, **kwargs):
        # Calculate weight change relative to the initial weight
        if self.rfid_assignment.initial_weight is not None:
            self.weight_change = ((self.weight - self.rfid_assignment.initial_weight) / self.rfid_assignment.initial_weight) * 100
        else:
            self.weight_change = 0.0

        # Calculate tumor size change relative to the initial tumor size
        if self.rfid_assignment.tumor_size is not None:
            self.tumor_size_change = ((self.tumor_size - self.rfid_assignment.tumor_size) / self.rfid_assignment.tumor_size) * 100
        else:
            self.tumor_size_change = 0.0

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Measurement for Animal {self.animal.animal_index} in {self.animal.experiment.name}"
    
class Cage(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE, null=True)
    cage_number = models.PositiveIntegerField(default=1)
    number = models.PositiveIntegerField()
    name = models.CharField(max_length=100)
    capacity = models.IntegerField()

    def __str__(self):
        return f"Cage {self.cage_number} in {self.experiment.name if self.experiment else 'No Experiment'}"



class Collaborator(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE, related_name='collaborators')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
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
    type = models.CharField(max_length=50, choices=[('private', 'Private'), ('group', 'Group')], default='private')
    user1 = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='conversations_initiated')
    user2 = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='conversations_received', null=True, blank=True)
    name = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        if self.type == 'private':
            return f"Private conversation between {self.user1.username} and {self.user2.username}"
        return f"Group conversation: {self.name}"


class GroupMember(models.Model):
    conversation = models.ForeignKey(Conversation, related_name='groupmember', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.user.username} in group {self.conversation.name}"

class Message(models.Model):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField(blank=True, null=True)  # Allow blank content
    timestamp = models.DateTimeField(default=timezone.now)
    conversation = models.ForeignKey(Conversation, related_name='messages', on_delete=models.CASCADE)
    attachment = models.FileField(upload_to='message_attachments/', null=True, blank=True)
    invitation_id = models.IntegerField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    def __str__(self):
        return f"Message from {self.sender.username} in conversation {self.conversation.id}"
    
class Friend(models.Model):
    user1 = models.ForeignKey(User, related_name='friendship_creator_set', on_delete=models.CASCADE)
    user2 = models.ForeignKey(User, related_name='friend_set', on_delete=models.CASCADE)
    status = models.CharField(max_length=10)  # e.g., 'accepted', 'pending'

    def __str__(self):
        return f"{self.user1.username} is friends with {self.user2.username}"


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
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE)
    message = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"Notification for {self.user.username} - {self.experiment.name}"
    