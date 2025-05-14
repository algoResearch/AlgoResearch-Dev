from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, WildlifeCapture, IRBCommittee, IRBMember, SpeciesUseLocation, SpeciesStrain, IRBDocument,IACUCPersonnel, Meeting, MeetingItem, IACUCMember, IRBFundingSource, SpeciesMSS, IRBSubmission, DatabaseSearch, SpeciesEuthanasia, HazardousAgent, SpeciesVetDrug, SpeciesBreeding, SpeciesSurgery, SpeciesRestraint, SpeciesProcedure, FieldStudyPermit, Opportunity, FieldSafetyPrecautions, PublicTransportUse, FieldStudyDetails, IACUCFundingSource, OutsideHousing, OffCampusWork, ExternalCollaboration, IACUCPrivateFundingSource,  IACUCProtocolSpecies, IACUCSubmission, TaskAttachment, Department, PackageForm, TaskComment, ProjectTask, Project, OtherPersonnel, SeniorKeyPerson, BudgetPeriod, PerformanceSiteLocation, Protocol, Experiment, AdminCreatedForm, TrainingFolder, Certification, FormField, Task, Cage, Animal, Conversation, Attachment# Import your custom User and Experiment models
from .models import Organization, IRBStudyDevice, FormPackage, SF424Form, IACUCInternalFundingSource, SubMiniStep, MiniStep, MiniStepField, Animal, Observation, Sample, Dose, Message, AdminPDFTemplate
from pytz import common_timezones
from django.utils import timezone
from django.forms import inlineformset_factory
import mimetypes
import logging
logger = logging.getLogger(__name__)

class UpdateProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'email', 
            'institution', 'role', 'location', 
            'profile_picture', 'profile_banner'
        ]
        widgets = {
            'profile_picture': forms.FileInput(attrs={'class': 'form-control'}),
            'profile_banner': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def clean_profile_banner(self):
        banner = self.cleaned_data.get('profile_banner')

        if banner:
            # Validate file size (e.g., 10MB max)
            max_file_size = 10 * 1024 * 1024  # 10MB
            if banner.size > max_file_size:
                raise forms.ValidationError("The file size exceeds 10MB.")

            # Validate file type
            valid_mime_types = ['image/jpeg', 'image/png']
            

        return banner

class BannerUploadForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['profile_banner']
        widgets = {
            'profile_banner': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }

    def clean_profile_banner(self):
        banner = self.cleaned_data.get('profile_banner')

        if banner:
            # Validate file size
            max_file_size = 10 * 1024 * 1024  # 10MB
            if banner.size > max_file_size:
                raise forms.ValidationError("The file size exceeds 10MB.")

            # Validate file type
            valid_mime_types = ['image/jpeg', 'image/png']
            if banner.content_type not in valid_mime_types:
                raise forms.ValidationError("Invalid file type. Allowed types: JPEG, PNG.")

        return banner


class CageCreationForm(forms.ModelForm):
    class Meta:
        model = Cage
        fields = ['name', 'capacity']
        labels = {
            'name': 'Cage Name',
            'capacity': 'Capacity',
        }



class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    middle_name = forms.CharField(max_length=50, required=False)
    last_name = forms.CharField(max_length=30, required=True)
    prefix = forms.CharField(max_length=10, required=False)
    suffix = forms.CharField(max_length=10, required=False)
    position = forms.CharField(max_length=255, required=False)
    institution = forms.CharField(max_length=100, required=False)
    role = forms.ChoiceField(choices=User.ROLE_CHOICES, required=True, label="Role")
    POSITION_CHOICES = [
        ('', '---------'),
        ('app_viewer', 'Application Viewer'),
        ('app_editor', 'Application Editor'),
        ('dept_app_editor', 'Department Application Editor'),
        ('proposal_reviewer', 'Proposal Reviewer'),
        ('dept_app_viewer', 'Department Application Viewer'),
    ]
    position_type = forms.ChoiceField(choices=POSITION_CHOICES, required=False, label="Application Position")
    location = forms.CharField(max_length=100, required=False)
    street1 = forms.CharField(max_length=255, required=False, label="Street 1")
    street2 = forms.CharField(max_length=255, required=False, label="Street 2")
    city = forms.CharField(max_length=100, required=False)
    county = forms.CharField(max_length=100, required=False)
    state = forms.CharField(max_length=100, required=False, label="State (if US)")
    province = forms.CharField(max_length=100, required=False, label="Province (if not US)")
    country = forms.CharField(max_length=100, required=False)
    zip_code = forms.CharField(max_length=20, required=False)
    phone_number = forms.CharField(required=True, label="Phone Number")
    fax = forms.CharField(required=False, label="Fax")
    net_id = forms.CharField(required=True, label="Net ID")
    department = forms.ModelChoiceField(queryset=Department.objects.none(), required=False)
    mail_code = forms.CharField(required=True, label="Mail Code")

    class Meta:
        model = User
        fields = (
            "username", "prefix", "first_name", "middle_name", "last_name", "suffix", "position",
            "institution", "role","position_type", "location", "street1", "street2", "city", "county", "state", "province",
            "country", "zip_code", "phone_number", "fax", "net_id", "department", "mail_code",
            "email", "password1", "password2",
        )

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop("organization", None)
        super().__init__(*args, **kwargs)

        # Filter departments to match the passed organization
        if organization:
            self.fields['department'].queryset = Department.objects.filter(organization=organization)

        # Apply Bootstrap styling
        for field_name, field in self.fields.items():
            field.widget.attrs.update({
                'class': 'form-control shadow-sm',
                'placeholder': f'Enter {field.label}'
            })

    def save(self, commit=True):
        user = super().save(commit=False)

        for attr in [
            "email", "prefix", "first_name", "middle_name", "last_name", "suffix",
            "position", "institution", "role", "position_type", "location", "street1", "street2",
            "city", "county", "state", "province", "country", "zip_code", "phone_number",
            "fax", "net_id", "department", "mail_code"
        ]:
            setattr(user, attr, self.cleaned_data.get(attr))

        # Assign a default profile picture if none is set
        if not user.profile_picture:
            initial = user.first_name[0].upper() if user.first_name else "U"
            user.profile_picture.save(
                f"profile_{user.username}.png",
                User.generate_default_profile_picture(initial),
            )

        if commit:
            user.save()
        return user

class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Department Name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Description (optional)', 'rows': 3}),
        }
class ProtocolCreationForm(forms.ModelForm):
    class Meta:
        model = Protocol
        fields = ['title', 'description', 'file']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter protocol title'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Describe the protocol'}),
            'file': forms.FileInput(attrs={'class': 'form-control'}),
        }

class ProtocolApprovalForm(forms.ModelForm):
    class Meta:
        model = Protocol
        fields = ['approval_status']
        widgets = {
            'approval_status': forms.Select(choices=Protocol.STATUS_CHOICES, attrs={'class': 'form-control'}),
        }


class OrganizationForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ['name', 'address', 'sidebar_color', 'hover_color', 'primary_color', 'secondary_color']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Organization Name'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Address', 'rows': 3}),
            'sidebar_color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control'}),
            'hover_color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control'}),
            'primary_color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control'}),
            'secondary_color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control'}),
        }
        labels = {
            'name': 'Organization Name',
            'address': 'Address (Optional)',
            'sidebar_color': 'Sidebar Color',
            'hover_color': 'Sidebar Hover Color',
            'primary_color': 'Primary Logo Color',
            'secondary_color': 'Secondary Logo Color',
        }

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'email', 'profile_picture']  # Include profile_picture
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control shadow-sm',
                'placeholder': 'Enter your username',
                'readonly': True  # Make username read-only to avoid accidental changes
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control shadow-sm',
                'placeholder': 'Enter your email'
            }),
            'profile_picture': forms.FileInput(attrs={
                'class': 'form-control shadow-sm',
                'accept': 'image/*'  # Restrict file input to image files
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add Bootstrap or custom classes to each field for styling
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control shadow-sm'})
            if field_name == 'profile_picture':
                field.widget.attrs.update({'accept': 'image/*'})  # Limit file input to images

class ExperimentBasicInfoForm(forms.ModelForm):
    start_date = forms.DateField(
        initial=timezone.now, 
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Experiment Start Date"
    )

    class Meta:
        model = Experiment
        fields = ['name', 'description', 'start_date']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Enter experiment name'})
        self.fields['description'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Enter experiment description'})
        self.fields['start_date'].widget.attrs.update({'class': 'form-control'})


class ExperimentForm(forms.ModelForm):
    class Meta:
        model = Experiment
        fields = [
            'name', 'description', 'start_date', 'end_date', 'number_of_animals',
            'number_of_groups', 'max_per_cage', 'drug_list', 'strain_list',
            'tumor_size_method', 'rfid_required', 'weight_schedule',
            'weigh_in_interval', 'tumor_measurement_interval',
        ]  # Remove 'monitor_weight' and 'monitor_tumor'

    def save(self, commit=True):
        experiment = super().save(commit=False)
        experiment.organization = self.initial['organization']  # Assign to the same organization as the user
        if commit:
            experiment.save()
        return experiment

class ProfilePictureForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['profile_picture']

class UserSearchForm(forms.Form):
    query = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Start typing to search for users...',
        'id': 'userSearch'
    }))


class ExperimentMetricsForm(forms.Form):
    # Weight-related fields
    monitor_weight = forms.ChoiceField(
        choices=[('yes', 'Yes'), ('no', 'No')],
        label="Monitor Weight?",
        widget=forms.RadioSelect
    )
    weight_schedule = forms.ChoiceField(
        choices=[('yes', 'Yes'), ('no', 'No')],
        label="Weight Schedule?",
        widget=forms.RadioSelect,
        required=False
    )
    weigh_in_interval = forms.IntegerField(
        label="Weigh-In Interval (days)", required=False
    )
    experiment_duration = forms.IntegerField(
        label="Experiment Duration (days)", required=False
    )
    warning_weight_percentage = forms.FloatField(
        label="Warning Weight (%)", required=False
    )
    removal_weight_percentage = forms.FloatField(
        label="Removal Weight (%)", required=False
    )

    # Tumor-related fields
    monitor_tumor = forms.ChoiceField(
        choices=[('yes', 'Yes'), ('no', 'No')],
        label="Monitor Tumor Size?",
        widget=forms.RadioSelect
    )
    tumor_schedule = forms.ChoiceField(
        choices=[('yes', 'Yes'), ('no', 'No')],
        label="Tumor Size Schedule?",
        widget=forms.RadioSelect,
        required=False
    )
    tumor_measurement_interval = forms.IntegerField(
        label="Tumor Measurement Interval (days)", required=False
    )
    tumor_duration = forms.IntegerField(
        label="Tumor Measurement Duration (days)", required=False
    )
    tumor_growth_warning = forms.FloatField(
        label="Tumor Growth Warning (mm)", required=False
    )
    tumor_growth_removal = forms.FloatField(
        label="Tumor Growth Removal (mm)", required=False
    )


class OverviewForm(forms.ModelForm):
    class Meta:
        model = Animal
        fields = [
            'rfid_tag',
            'animal_index',
            'date_of_birth',
            'sex',
            'species',
            'strain',
            'strains',
            'drugs',
            'is_removed',
            'is_active',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'strain': forms.CheckboxSelectMultiple(),
        }

class ObservationForm(forms.ModelForm):
    class Meta:
        model = Observation
        fields = ['category', 'score']  # Replace 'name' with 'category'
        widgets = {
            'score': forms.NumberInput(attrs={'min': 1, 'max': 5}),
        }


class SubMiniStepForm(forms.ModelForm):
    class Meta:
        model = SubMiniStep
        fields = ["name", "order", "is_required"]



class SampleForm(forms.ModelForm):
    class Meta:
        model = Sample
        fields = ['sample_id', 'sample_type']
        widgets = {
            'sample_id': forms.TextInput(attrs={'placeholder': 'Enter Sample ID'}),
            'sample_type': forms.TextInput(attrs={'placeholder': 'Enter Sample Type'}),
        }

class AttachmentForm(forms.ModelForm):
    class Meta:
        model = Attachment
        fields = ['file', 'description']
        widgets = {
            'file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Add a description'}),
        }
        labels = {
            'file': 'Attachment File',
            'description': 'Description (Optional)',
        }
class DoseForm(forms.ModelForm):
    class Meta:
        model = Dose
        fields = ['drug_name', 'dose', 'stock_concentration', 'dose_volume']
        widgets = {
            'dose': forms.TextInput(attrs={'placeholder': 'Enter Dose'}),
            'stock_concentration': forms.TextInput(attrs={'placeholder': 'Enter Stock Concentration'}),
            'dose_volume': forms.TextInput(attrs={'placeholder': 'Enter Dose Volume'}),
        }

class DataInputMethodForm(forms.Form):
    INPUT_METHOD_CHOICES = (
        ('bluetooth', 'Bluetooth'),
        ('serial', 'Serial Port'),
        ('simulation', 'Manual Simulation')
    )
    input_method = forms.ChoiceField(choices=INPUT_METHOD_CHOICES, label="Select Data Input Method")
    

class WeightEntryForm(forms.Form):
    animal_id = forms.IntegerField(widget=forms.HiddenInput())
    weight = forms.FloatField(label="Enter Weight (g)")

    def clean_weight(self):
        weight = self.cleaned_data.get("weight")
        if weight <= 0:
            raise forms.ValidationError("Weight must be a positive number.")
        return weight
class TumorSizeEntryForm(forms.Form):
    animal_id = forms.IntegerField(widget=forms.HiddenInput())
    tumor_size = forms.FloatField(label="Enter Tumor Size (mm)")

    def clean_tumor_size(self):
        tumor_size = self.cleaned_data.get("tumor_size")
        if tumor_size < 0:
            raise forms.ValidationError("Tumor size cannot be negative.")
        return tumor_size

class AnimalRegistrationForm(forms.ModelForm):
    cage = forms.CharField(required=False)

    class Meta:
        model = Animal
        fields = [
            'rfid_tag',
            'sex',
            'strain',
            'date_of_birth',
            'cage',  # Keep only fields present in the Animal model
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
        }

    def save(self, commit=True, org_id=None):
        animal = super().save(commit=False)
        if org_id:
            animal.organization_id = org_id  # Set organization ID
        if commit:
            animal.save()
        return animal

    
class AnimalForm(forms.ModelForm):
    class Meta:
        model = Animal
        fields = ['date_of_birth', 'species', 'strain']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'species': forms.TextInput(attrs={'placeholder': 'Enter Species'}),
            'strain': forms.TextInput(attrs={'placeholder': 'Enter Strain'}),
        }

    def save(self, commit=True, org_id=None):
        animal = super().save(commit=False)
        if org_id:
            animal.organization_id = org_id
        if commit:
            animal.save()
        return animal

class MessageForm(forms.ModelForm):
    content = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'placeholder': 'Type a message...'}),
        strip=True,  # Strip whitespace from the input
    )
    attachment = forms.FileField(required=False)

    class Meta:
        model = Message
        fields = ['content', 'attachment']  # Include the attachment field

    def clean_content(self):
        content = self.cleaned_data.get('content', '')
        logger.debug(f"Raw content from form: {content} (Type: {type(content)})")
        
        if content and not isinstance(content, str):
            logger.error("Content must be a string.")
            raise forms.ValidationError("Content must be a string.")
        
        return content.strip()  # Ensure content is stripped of leading/trailing whitespace

    def clean_attachment(self):
        attachment = self.cleaned_data.get('attachment')
        if not attachment and self.instance.pk:
            # If editing and no new attachment is uploaded, use the existing attachment
            return self.instance.attachment

        if attachment:
            logger.debug(f"Attachment details: Name={attachment.name}, Size={attachment.size}, Type={attachment.content_type}")

            # Validate file size (10 MB limit)
            max_file_size = 10 * 1024 * 1024  # 10MB
            if attachment.size > max_file_size:
                logger.error("File size exceeds 10MB limit.")
                raise forms.ValidationError("File size should not exceed 10MB.")

            # Validate file extension
            allowed_extensions = ['.jpg', '.jpeg', '.png', '.pdf', '.mp4']
            if not any(attachment.name.lower().endswith(ext) for ext in allowed_extensions):
                logger.error("Invalid file extension.")
                raise forms.ValidationError(
                    "Invalid file extension. Allowed: .jpg, .jpeg, .png, .pdf, .mp4."
                )

            # Validate MIME type
            mime_type, _ = mimetypes.guess_type(attachment.name)
            allowed_mime_types = ['image/jpeg', 'image/png', 'application/pdf', 'video/mp4']
            if mime_type not in allowed_mime_types:
                logger.error(f"Invalid MIME type: {mime_type}")
                raise forms.ValidationError(
                    "Invalid file type. Allowed types: JPEG, PNG, PDF, MP4."
                )
        else:
            logger.debug("No attachment provided.")
    
        return attachment
    def __init__(self, *args, **kwargs):
        self.is_edit = kwargs.pop('is_edit', False)
        super().__init__(*args, **kwargs)
        
    def clean(self):
        cleaned_data = super().clean()
        content = cleaned_data.get('content', '').strip()
        attachment = cleaned_data.get('attachment')

        logger.debug(f"Cleaned data - Content: {content}, Attachment: {attachment}")

        if not content and not attachment:
            # Allow empty content if editing and no changes are needed
            if not self.instance.pk or not (self.instance.content or self.instance.attachment):
                logger.error("Validation failed: Both content and attachment are empty.")
                raise forms.ValidationError("Please enter a message or attach a file.")

        # Ensure content is a string
        if content and not isinstance(content, str):
            logger.warning("Content is not a string; attempting conversion.")
            cleaned_data['content'] = str(content)

        return cleaned_data
    


class MiniStepForm(forms.ModelForm):
    class Meta:
        model = MiniStep
        fields = ['name', 'order', 'is_required']

class MiniStepFieldForm(forms.ModelForm):
    class Meta:
        model = MiniStepField
        
        fields = ['label', 'field_type', 'options', 'is_required', 'column_names', 'fixed_rows', 'allow_dynamic_rows', 'parent_field', 'trigger_option']
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["parent_field"].queryset = MiniStepField.objects.filter(
            mini_step=self.instance.mini_step if self.instance else None, field_type="dropdown"
        ) if self.instance and self.instance.mini_step else MiniStepField.objects.none()

        # ✅ Ensure only dropdown fields from the same mini_step are selectable as parent fields
        if "instance" in kwargs and kwargs["instance"].mini_step:
            self.fields["parent_field"].queryset = MiniStepField.objects.filter(
                mini_step=kwargs["instance"].mini_step, field_type="dropdown"
            )
        else:
            self.fields["parent_field"].queryset = MiniStepField.objects.none()

class ImportForm(forms.Form):
    import_file = forms.FileField()

    def clean_import_file(self):
        file = self.cleaned_data.get('import_file')
        
        # Check if the file is a CSV
        if not file.name.endswith('.csv'):
            raise forms.ValidationError('Invalid file type. Please upload a CSV file.')
        
        # Check if the file is not empty
        if file.size == 0:
            raise forms.ValidationError('The file is empty. Please upload a non-empty CSV file.')
        
        # Check file size (optional, limit to 5MB)
        if file.size > 5 * 1024 * 1024:
            raise forms.ValidationError('The file is too large. Maximum allowed size is 5MB.')

        return file

class WeighInImportForm(forms.Form):
    import_file = forms.FileField(label="Upload CSV File")
    measurement_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), label="Measurement Date")

    def clean_import_file(self):
        file = self.cleaned_data.get('import_file')
        if not file.name.endswith('.csv'):
            raise forms.ValidationError('Invalid file type. Please upload a CSV file.')
        return file

    def clean_measurement_date(self):
        measurement_date = self.cleaned_data.get('measurement_date')
        if not measurement_date:
            raise forms.ValidationError('Please provide a valid date for the measurements.')
        return measurement_date

class TimeZoneForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['timezone']
        widgets = {
            'timezone': forms.Select(choices=[(tz, tz) for tz in common_timezones])
        }




class AdminCreatedFormForm(forms.ModelForm):
    class Meta:
        model = AdminCreatedForm
        fields = ['name', 'description']

    def save(self, commit=True):
        form_instance = super().save(commit=False)
        # Assign the created form to the same organization as the admin user
        form_instance.organization = self.initial['organization']
        if commit:
            form_instance.save()
        return form_instance

# forms.py

# forms.py

class AssignTaskForm(forms.ModelForm):
    DAYS_OF_WEEK = [
        ('Sunday', 'Sunday'),
        ('Monday', 'Monday'),
        ('Tuesday', 'Tuesday'),
        ('Wednesday', 'Wednesday'),
        ('Thursday', 'Thursday'),
        ('Friday', 'Friday'),
        ('Saturday', 'Saturday'),
    ]

    start_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), required=True)
    end_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), required=True)
    recurrence_days = forms.MultipleChoiceField(
        choices=DAYS_OF_WEEK,
        widget=forms.CheckboxSelectMultiple,
        required=True,
        help_text="Select the days of the week for the task to recur."
    )
    assigned_to = forms.ModelMultipleChoiceField(
        queryset=User.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=True
    )

    class Meta:
        model = Task
        fields = ['title', 'description', 'start_date', 'end_date', 'recurrence_days', 'assigned_to']

    def __init__(self, *args, **kwargs):
        experiment = kwargs.pop('experiment', None)
        super().__init__(*args, **kwargs)
        if experiment:
            # Filter users based on experiment collaborators
            self.fields['assigned_to'].queryset = User.objects.filter(
                id__in=experiment.collaborators.values_list('user', flat=True)
            )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if start_date and end_date and start_date > end_date:
            self.add_error('end_date', "End date cannot be earlier than the start date.")

        return cleaned_data
    
class FormFieldForm(forms.ModelForm):
    choices = forms.CharField(widget=forms.Textarea, required=False)

    class Meta:
        model = FormField
        fields = ['field_label', 'field_type', 'is_required', 'choices']

    def clean(self):
        cleaned_data = super().clean()
        field_type = cleaned_data.get('field_type')

        if field_type in ['yes_no', 'multiple_choice'] and not cleaned_data.get('choices'):
            raise forms.ValidationError("Choices are required for Yes/No or Multiple Choice fields.")
        
        return cleaned_data
class UploadPDFTemplateForm(forms.ModelForm):
    class Meta:
        model = AdminPDFTemplate
        fields = ['name', 'pdf_file']


class CustomEventScheduleForm(forms.Form):
    # Choice between manual and recurring schedule
    schedule_type = forms.ChoiceField(
        choices=[('manual', 'Select Dates Manually'), ('weekly', 'Repeat Every Weekday')],
        widget=forms.RadioSelect,
        label="Schedule Type"
    )
    
    # Field for manual date selection using a multi-date picker
    specific_dates = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Select specific dates'}),
        help_text="Select multiple dates for manual scheduling."
    )
    
    # Recurring weekly schedule fields
    weekday = forms.ChoiceField(
        choices=[
            ('0', 'Monday'), ('1', 'Tuesday'), ('2', 'Wednesday'), 
            ('3', 'Thursday'), ('4', 'Friday'), ('5', 'Saturday'), ('6', 'Sunday')
        ],
        required=False,
        label="Select Day of Week"
    )
    duration_weeks = forms.IntegerField(
        required=False,
        min_value=1,
        label="Number of Weeks",
        help_text="Specify duration in weeks for the weekly recurrence."
    )
    
    # Date range for the recurring schedule
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        required=False,
        label="Start Date"
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        required=False,
        label="End Date"
    )

    def clean(self):
        cleaned_data = super().clean()
        schedule_type = cleaned_data.get('schedule_type')
        specific_dates = cleaned_data.get('specific_dates')
        weekday = cleaned_data.get('weekday')
        duration_weeks = cleaned_data.get('duration_weeks')

        # Validation based on selected schedule type
        if schedule_type == 'manual' and not specific_dates:
            self.add_error('specific_dates', "Please select specific dates for manual scheduling.")
        elif schedule_type == 'weekly' and (not weekday or not duration_weeks):
            self.add_error('weekday', "Please select a weekday and specify the number of weeks.")
        
        return cleaned_data
    

class UpdateGroupInfoForm(forms.ModelForm):
    class Meta:
        model = Conversation
        fields = ['name', 'profile_picture']

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if not name or not name.strip():
            raise forms.ValidationError("Group name cannot be empty.")
        return name

    def clean_profile_picture(self):
        profile_picture = self.cleaned_data.get('profile_picture')
        if profile_picture and profile_picture.size > 10 * 1024 * 1024:  # Limit file size to 10MB
            raise forms.ValidationError("The file size must not exceed 10MB.")
        return profile_picture

class OrganizationITAdminCreationForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'role']


class TrainingFolderForm(forms.ModelForm):
    class Meta:
        model = TrainingFolder
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Folder Name'}),
        }

class CertificationForm(forms.ModelForm):
    class Meta:
        model = Certification
        fields = ['course_id', 'course_title']
        widgets = {
            'course_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Course ID'}),
            'course_title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Course Title'}),
        }


from django import forms
from .models import PerformanceSiteLocation

class PerformanceSiteLocationForm(forms.ModelForm):
    class Meta:
        model = PerformanceSiteLocation
        fields = [
            'is_individual_submission', 'organization_name', 
            'street1', 'street2', 'city', 'county', 'state', 'province',
            'country', 'zip_code', 'congressional_district'
        ]
        widgets = {
            'is_individual_submission': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'organization_name': forms.TextInput(attrs={'class': 'form-control'}),
          
            'street1': forms.TextInput(attrs={'class': 'form-control', 'required': True}),
            'street2': forms.TextInput(attrs={'class': 'form-control'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'required': True}),
            'county': forms.TextInput(attrs={'class': 'form-control'}),
            'state': forms.Select(choices=[('', 'Select State')] + [(s, s) for s in ['California', 'Texas', 'New York']], attrs={'class': 'form-control'}),
            'province': forms.TextInput(attrs={'class': 'form-control'}),
            'country': forms.Select(choices=[('United States', 'United States'), ('Canada', 'Canada')], attrs={'class': 'form-control', 'required': True}),
            'zip_code': forms.TextInput(attrs={'class': 'form-control'}),
            'congressional_district': forms.TextInput(attrs={'class': 'form-control'}),
        }


class BudgetPeriodForm(forms.ModelForm):
    budget_type = forms.ChoiceField(
        choices=BudgetPeriod.BUDGET_TYPE_CHOICES,
        widget=forms.RadioSelect
    )

    start_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))

    class Meta:
        model = BudgetPeriod
        fields = [ 'budget_type', 'start_date', 'end_date']

class SeniorKeyPersonForm(forms.ModelForm):
    class Meta:
        model = SeniorKeyPerson
        fields = ['prefix', 'first_name', 'middle_name', 'last_name', 'suffix',
                  'base_salary', 'calendar_months', 'academic_months', 'summer_months',
                  'requested_salary', 'fringe_benefits', 'project_role']
        widgets = {
            'base_salary': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'calendar_months': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'academic_months': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'summer_months': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'requested_salary': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'fringe_benefits': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'project_role': forms.TextInput(attrs={'class': 'form-control'}),
        }

# Formset to handle up to 8 people dynamically
SeniorKeyPersonFormSet = inlineformset_factory(
    BudgetPeriod, SeniorKeyPerson, form=SeniorKeyPersonForm,
    extra=1, max_num=8, can_delete=True
)

class OtherPersonnelForm(forms.ModelForm):
    class Meta:
        model = OtherPersonnel
        fields = ['role', 'num_personnel', 'calendar_months', 'academic_months', 
                  'summer_months', 'requested_salary', 'fringe_benefits']
        widgets = {
            'num_personnel': forms.NumberInput(attrs={'class': 'form-control'}),
            'calendar_months': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'academic_months': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'summer_months': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'requested_salary': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'fringe_benefits': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

OtherPersonnelFormSet = inlineformset_factory(
    BudgetPeriod, OtherPersonnel, form=OtherPersonnelForm,
    extra=0, max_num=4, can_delete=False
)
class SF424FormForm(forms.ModelForm):
    position_title = forms.CharField(label="Position/Title", max_length=100, required=True)
    authorized_representative_title = forms.CharField(label="Authorized Representative Title", max_length=100, required=True)

class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            'name', 'principal_investigator', 'admin_unit', 'sponsor', 
            'prime_sponsor', 'sponsor_deadline', 'total_sponsor_costs', 
            'project_start_date', 'project_end_date', 'instrument_type'
        ]

class OpportunityForm(forms.ModelForm):
    class Meta:
        model = Opportunity
    
        fields = ['number', 'proposal_name', 'principal_investigator', 'organization', 'number_of_periods', 'due_date']
        

class CreateOpportunityForm(forms.ModelForm):
    attached_users = forms.ModelMultipleChoiceField(
        queryset=User.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={
            'class': 'form-control select2-multiple'
        })
    )

    class Meta:
        model = Opportunity
        fields = [
            'number', 'title', 'comp_id', 'comp_title', 'agency_ref',
            'package_number', 'cfda', 'open_date', 'close_date', 'form_package', 'attached_users'
        ]
        widgets = {
            'open_date': forms.DateInput(attrs={'type': 'date'}),
            'close_date': forms.DateInput(attrs={'type': 'date'}),
        }

    

class ProjectTaskForm(forms.ModelForm):
    class Meta:
        model = ProjectTask
        fields = [
            'title', 'description', 'task_type', 'task_category',
            'start_date', 'due_date', 'assignees', 'is_completed'
        ]

class TaskAttachmentForm(forms.ModelForm):
    class Meta:
        model = TaskAttachment
        fields = ['file']

class TaskCommentForm(forms.ModelForm):
    class Meta:
        model = TaskComment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Add your comment here...'}),
        }
class IACUCProtocolForm(forms.ModelForm):
    class Meta:
        model = IACUCSubmission
        fields = [
            'protocol_title',
            'principal_investigator',
        ]

class IACUCMemberForm(forms.ModelForm):
    class Meta:
        model = IACUCMember
        fields = ['user', 'role']
        widgets = {
            'user': forms.Select(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-control'}),
        }
class IACUCSubmissionDetailsForm(forms.ModelForm):
    class Meta:
        model = IACUCSubmission
        fields = [
            'protocol_title',
            'principal_investigator',
            # ✅ New options
            'federal_funding',
            'internal_federal_funding',
            'private_commercial_funding',
            'uses_outside_tissues',
            'external_collaboration',
            'off_campus_live_animal_work',
            'housing_outside_facility_12hr',
            'public_area_transport',
            'field_studies',
        ]
        widgets = {
            field: forms.CheckboxInput(attrs={'class': 'form-check-input'})
            for field in [
                'federal_funding',
                'internal_federal_funding',
                'private_commercial_funding',
                'uses_outside_tissues',
                'external_collaboration',
                'off_campus_live_animal_work',
                'housing_outside_facility_12hr',
                'public_area_transport',
                'field_studies',
            ]
        }
class IACUCProtocolSpeciesForm(forms.ModelForm):
    class Meta:
        model = IACUCProtocolSpecies
        exclude = ['submission']
        widgets = {
            field: forms.CheckboxInput(attrs={'class': 'form-check-input'})
            for field in [
                'breeding', 'procedures', 'restraint', 'surgery',
                'vet_drugs', 'test_agents', 'euthanize'
            ]
        }

class IACUCFundingSourceForm(forms.ModelForm):
    class Meta:
        model = IACUCFundingSource
        fields = ['source', 'grant_title', 'funded', 'pi_on_grant', 'end_date']
        widgets = {
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

class IACUCInternalFundingSourceForm(forms.ModelForm):
    class Meta:
        model = IACUCInternalFundingSource
        fields = ['organization', 'department', 'fund_title', 'sponsored_projects_number']

class IACUCPrivateFundingSourceForm(forms.ModelForm):
    class Meta:
        model = IACUCPrivateFundingSource
        fields = ['company_name', 'fund_title', 'due_date']
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }

class SpeciesInfoForm(forms.ModelForm):
    class Meta:
        model = IACUCProtocolSpecies
        fields = [
            "age_range",
            "target_weight",
            "max_cages",
            "avg_weeks_housed",
            "is_pathogen_free",
            "identification_methods",
        ]
        widgets = {
            "age_range": forms.TextInput(attrs={"class": "form-control"}),
            "target_weight": forms.TextInput(attrs={"class": "form-control"}),
            "max_cages": forms.NumberInput(attrs={"class": "form-control"}),
            "avg_weeks_housed": forms.NumberInput(attrs={"class": "form-control"}),
            "is_pathogen_free": forms.RadioSelect(choices=[(True, "Yes"), (False, "No")]),
            "identification_methods": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }
# forms.py

class SpeciesJustificationForm(forms.ModelForm):
    class Meta:
        model = IACUCProtocolSpecies
        fields = ["species_justification", "other_justification"]
        widgets = {
            "species_justification": forms.Select(attrs={
                "class": "form-select",
                "onchange": "toggleOtherJustification(this)"
            }),
            "other_justification": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "id": "other-justification-textarea",  # ✅ This line is essential
                "style": "display:none;"
            }),
        }


class SpeciesUseLocationForm(forms.ModelForm):
    class Meta:
        model = SpeciesUseLocation
        fields = ["location", "room", "location_type"]
        widgets = {
            "location": forms.TextInput(attrs={"class": "form-control"}),
            "room": forms.TextInput(attrs={"class": "form-control"}),
            "location_type": forms.Select(attrs={"class": "form-select"}),
        }
class SpeciesStrainForm(forms.ModelForm):
    class Meta:
        model = SpeciesStrain
        fields = ["strain", "age", "weight", "phenotype"]
        widgets = {
            "strain": forms.TextInput(attrs={"class": "form-control"}),
            "age": forms.TextInput(attrs={"class": "form-control"}),
            "weight": forms.TextInput(attrs={"class": "form-control"}),
            "phenotype": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }
class PersonnelForm(forms.ModelForm):
    class Meta:
        model = IACUCPersonnel
        fields = ['business_role', 'name', 'organization', 'department', 'home_phone', 'email']
        widgets = {
            'business_role': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'organization': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.TextInput(attrs={'class': 'form-control'}),
            'home_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

class TissueSourceForm(forms.ModelForm):
    class Meta:
        model = IACUCSubmission
        fields = ['uses_outside_tissues', 'source_assurance_number', 'source_protocol_number']

class ExternalCollaborationForm(forms.ModelForm):
    class Meta:
        model = ExternalCollaboration
        fields = ['organization_name', 'assurance_number', 'protocol_number', 'species_list']

class OffCampusWorkForm(forms.ModelForm):
    class Meta:
        model = OffCampusWork
        fields = ['collaborator_name', 'site_location', 'assurance_number']

class OutsideHousingForm(forms.ModelForm):
    class Meta:
        model = OutsideHousing
        fields = [
            'under_24hrs', 'under_24hrs_location', 'under_24hrs_justification',
            'over_24hrs', 'over_24hrs_location', 'over_24hrs_justification'
        ]
        widgets = {
            'under_24hrs_justification': forms.Textarea(attrs={'rows': 2}),
            'over_24hrs_justification': forms.Textarea(attrs={'rows': 2}),
        }

class PublicTransportForm(forms.ModelForm):
    class Meta:
        model = PublicTransportUse
        fields = ['following_policy', 'justification']
        widgets = {
            'justification': forms.Textarea(attrs={'rows': 3}),
        }
class FieldStudyDetailsForm(forms.ModelForm):
    class Meta:
        model = FieldStudyDetails
        fields = ["location", "animals_captured"]
        widgets = {
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'animals_captured': forms.RadioSelect(choices=[(True, 'Yes'), (False, 'No')])
        }

class WildlifeCaptureForm(forms.ModelForm):
    class Meta:
        model = WildlifeCapture
        fields = [
            "equipment_used",
            "trapping_duration",
            "monitoring_protocol",
            "capture_myopathy_treatment",
            "opportunistic_species",
            "release_procedure",
            "transport_type",
            "transport_description",
            "animals_tagged",
            "health_observations",
            "physiological_parameters",
            "measurement_frequency",
            "normal_ranges",
            "out_of_range_protocol",
        ]
        widgets = {
            "equipment_used": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "trapping_duration": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "monitoring_protocol": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "capture_myopathy_treatment": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "opportunistic_species": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "release_procedure": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "transport_type": forms.Select(attrs={"class": "form-select"}),
            "transport_description": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "animals_tagged": forms.RadioSelect(choices=[(True, "Yes"), (False, "No")]),
            "health_observations": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "physiological_parameters": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "measurement_frequency":forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "normal_ranges": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "out_of_range_protocol": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
        }
class FieldSafetyPrecautionsForm(forms.ModelForm):
    class Meta:
        model = FieldSafetyPrecautions
        fields = ["decontamination_procedures", "ppe_description"]
        widgets = {
            "decontamination_procedures": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "ppe_description": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
        }

class FieldStudyPermitForm(forms.ModelForm):
    class Meta:
        model = FieldStudyPermit
        fields = ["permits_required", "permit_details"]
        widgets = {
            "permits_required": forms.RadioSelect(choices=[(True, "Yes"), (False, "No")]),
            "permit_details": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }
class BreedingForm(forms.ModelForm):
    class Meta:
        model = SpeciesBreeding
        fields = ["transgenic_flag", "maintain_colony"]
        widgets = {
            "transgenic_flag": forms.RadioSelect(choices=[(True, "Yes"), (False, "No")]),
            "maintain_colony": forms.RadioSelect(choices=[(True, "Yes"), (False, "No")]),
        }
class ProcedureForm(forms.ModelForm):
    class Meta:
        model = SpeciesProcedure
        fields = ["procedure_name", "description"]
        widgets = {
            "procedure_name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
        }
class RestraintForm(forms.ModelForm):
    class Meta:
        model = SpeciesRestraint
        fields = ["restraint_type", "rationale", "duration", "acclimation"]
        widgets = {
            "restraint_type": forms.Select(attrs={"class": "form-select"}),
            "rationale": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "duration": forms.TextInput(attrs={"class": "form-control"}),
            "acclimation": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
        }
class SurgeryInfoForm(forms.ModelForm):
    class Meta:
        model = SpeciesSurgery
        fields = ["surgery_type", "other_surgery_description", "recovery_type"]
        widgets = {
            "surgery_type": forms.Select(attrs={"class": "form-select", "id": "surgery-type-select"}),
            "other_surgery_description": forms.TextInput(attrs={"class": "form-control", "id": "other-surgery-description"}),
            "recovery_type": forms.Select(attrs={"class": "form-select"}),
        }
class SurgeryPreOpForm(forms.ModelForm):
    class Meta:
        model = SpeciesSurgery
        fields = ["pre_op_procedures", "surgical_attire", "support_anesthesia"]
        widgets = {
            "pre_op_procedures": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "surgical_attire": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "support_anesthesia": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }
class SurgeryPostOpForm(forms.ModelForm):
    class Meta:
        model = SpeciesSurgery
        fields = ["monitoring_plan", "suture_removal_timing", "clinical_parameters", "analgesics_withheld"]
        widgets = {
            "monitoring_plan": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "suture_removal_timing": forms.TextInput(attrs={"class": "form-control"}),
            "clinical_parameters": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "analgesics_withheld": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
class SurgeryLocationForm(forms.ModelForm):
    class Meta:
        model = SpeciesSurgery
        fields = ["surgery_location_building", "surgery_location_room", "surgery_location_type"]
        widgets = {
            "surgery_location_building": forms.TextInput(attrs={"class": "form-control"}),
            "surgery_location_room": forms.TextInput(attrs={"class": "form-control"}),
            "surgery_location_type": forms.Select(attrs={"class": "form-select"}),
        }


class MSSForm(forms.ModelForm):
    class Meta:
        model = SpeciesMSS
        fields = ['multiple_surgeries', 'surgery_description']
        widgets = {
            'multiple_surgeries': forms.RadioSelect(choices=[(True, "Yes"), (False, "No")]),
            'surgery_description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

class VetDrugForm(forms.ModelForm):
    ROUTE_CHOICES = [
        ('IM', 'IM'),
        ('INH', 'INH'),
        ('IND', 'IND'),
        ('ID', 'ID'),
        ('IV', 'IV'),
        ('ORL', 'ORL'),
        ('SQ', 'SQ'),
        ('TCP', 'TCP'),
        ('TOP', 'TOP'),
    ]
    route_admin = forms.MultipleChoiceField(
        choices=ROUTE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    class Meta:
        model = SpeciesVetDrug
        fields = [
            'generic_name', 'drug_type', 'dose', 'frequency',
            'route_admin', 'procedure_use', 'is_pharma_grade', 'non_pharma_justification'
        ]

class HazardousAgentForm(forms.ModelForm):
    ROUTE_CHOICES = [
        ('IM', 'IM'),
        ('INH', 'INH'),
        ('INJ', 'INJ'),
        ('IP', 'IP'),
        ('IV', 'IV'),
        ('ORL', 'ORL'),
        ('SQ', 'SQ'),
        ('TCP', 'TCP'),
        ('TOP', 'TOP'),
    ]

    route_admin = forms.MultipleChoiceField(
        choices=ROUTE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    class Meta:
        model = HazardousAgent
        fields = [
            'category',
            'agent_name',
            'committee_number',
            'route_admin',
            'other_route',
            'volume_frequency',
            'duration',
            'brought_into_facility',
            'precautions',
            'is_pharma_grade',
        ]
class EuthanasiaForm(forms.ModelForm):
    class Meta:
        model = SpeciesEuthanasia
        fields = [
            'method', 'num_b', 'num_c', 'num_d', 'num_e',
            'justification', 'pain_distress', 'pain_nature', 'euthanasia_criteria',
            'requesting_exemptions', 'exemptions_justification',
            'food_water_restriction', 'restriction_justification',
            'special_husbandry', 'husbandry_description',
            'reduce_description',
            'refine_description',
            'replace_description',
            'adverse_reactions_expected',
            'adverse_reactions_description',
        ]
        widgets = {
            'method': forms.Select(attrs={'class': 'form-select'}),
            'num_b': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'num_c': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'num_d': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'num_e': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'justification': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'pain_nature': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'euthanasia_criteria': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'requesting_exemptions': forms.RadioSelect(choices=[(True, "Yes"), (False, "No")]),
            'exemptions_justification': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'food_water_restriction': forms.RadioSelect(choices=[(True, "Yes"), (False, "No")]),
            'restriction_justification': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'special_husbandry': forms.RadioSelect(choices=[(True, "Yes"), (False, "No")]),
            'husbandry_description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'reduce_description': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'refine_description': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'replace_description': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'adverse_reactions_expected': forms.RadioSelect(choices=[(True, "Yes"), (False, "No")]),
            'adverse_reactions_description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }
class EuthanasiaNumbersForm(forms.ModelForm):
    class Meta:
        model = SpeciesEuthanasia
        fields = ['num_b', 'num_c', 'num_d', 'num_e']
        widgets = {
            'num_b': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'num_c': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'num_d': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'num_e': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
        }
class EuthanasiaMethodForm(forms.ModelForm):
    class Meta:
        model = SpeciesEuthanasia
        fields = ['method', 'justification']
        widgets = {
            'method': forms.Select(attrs={'class': 'form-select'}),
            'justification': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
class EuthanasiaPainForm(forms.ModelForm):
    class Meta:
        model = SpeciesEuthanasia
        fields = ['pain_distress', 'pain_nature', 'euthanasia_criteria']
        widgets = {
            'pain_nature': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'euthanasia_criteria': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
# forms.py

class ReduceForm(forms.ModelForm):
    class Meta:
        model = SpeciesEuthanasia
        fields = ['reduce_description']
        widgets = {
            'reduce_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }

class RefineForm(forms.ModelForm):
    class Meta:
        model = SpeciesEuthanasia
        fields = ['refine_description']
        widgets = {
            'refine_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }

class ReplaceForm(forms.ModelForm):
    class Meta:
        model = SpeciesEuthanasia
        fields = ['replace_description']
        widgets = {
            'replace_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }

class EuthanasiaAdverseForm(forms.ModelForm):
    class Meta:
        model = SpeciesEuthanasia
        fields = ['adverse_reactions_expected', 'adverse_reactions_description']
        widgets = {
            'adverse_reactions_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
class EuthanasiaExemptionsForm(forms.ModelForm):
    class Meta:
        model = SpeciesEuthanasia
        fields = [
            'requesting_exemptions', 'exemptions_justification',
            'food_water_restriction', 'restriction_justification',
            'special_husbandry', 'husbandry_description',
        ]
        widgets = {
            'exemptions_justification': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'restriction_justification': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'husbandry_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class DatabaseSearchForm(forms.ModelForm):
    class Meta:
        model = DatabaseSearch
        fields = [
            "animals_in_pain_d_or_e",
            "databases_used",
            "search_terms",
            "consultations",
            "journals",
            "scientific_meetings",
            "alternatives_reason",
            "search_date",
            "years_covered",
        ]
        widgets = {
            "animals_in_pain_d_or_e": forms.RadioSelect(choices=[(True, "Yes"), (False, "No")]),
            "databases_used": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "search_terms": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "consultations": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "journals": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "scientific_meetings": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "alternatives_reason": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "search_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "years_covered": forms.TextInput(attrs={"class": "form-control"}),
        }

class PersonnelInfoForm(forms.ModelForm):
    class Meta:
        model = IACUCPersonnel
        fields = ['business_role', 'name', 'organization', 'department', 'home_phone', 'email']
        widgets = {
            'home_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }
class FullPersonnelForm(forms.ModelForm):
    class Meta:
        model = IACUCPersonnel
        fields = [
            "business_role", "name", "organization", "department", "home_phone", "email",
            "activities_description", "training_completed", "training_date",
            "degrees", "experience_and_qualifications", "years_of_experience",
            "orientation_training_complete", "submitted_achs_questionnaire",
            "will_handle_animals", "activity_description"
        ]
        widgets = {
            "business_role": forms.TextInput(attrs={"class": "form-control"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "organization": forms.TextInput(attrs={"class": "form-control"}),
            "department": forms.TextInput(attrs={"class": "form-control"}),
            "home_phone": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "activities_description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "training_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "degrees": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "experience_and_qualifications": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "years_of_experience": forms.NumberInput(attrs={"class": "form-control"}),
            "activity_description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "training_completed": forms.CheckboxInput(),
            "orientation_training_complete": forms.CheckboxInput(),
            "submitted_achs_questionnaire": forms.CheckboxInput(),
            "will_handle_animals": forms.CheckboxInput(),
        }

class PersonnelActivitiesForm(forms.ModelForm):
    class Meta:
        model = IACUCPersonnel
        fields = ['will_handle_animals', 'activity_description']

class PersonnelTrainingForm(forms.ModelForm):
    class Meta:
        model = IACUCPersonnel

        fields = ['training_completed', 'training_date']  # Also need to be added to the model
class MeetingForm(forms.ModelForm):
    class Meta:
        model = Meeting
        fields = ['title', 'date']  # 👈 Remove 'attendees'
        widgets = {
            'date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }


class MeetingItemForm(forms.ModelForm):
    class Meta:
        model = MeetingItem
        fields = ['submission', 'notes']

class IRBSubmissionForm(forms.ModelForm):
    class Meta:
        model = IRBSubmission
        fields = ['protocol_title', 'human_subjects_involved', 'summary', 'risks', 'consent_procedures']
# forms.py

class IRBMemberForm(forms.ModelForm):
    class Meta:
        model = IRBMember
        fields = ['user', 'role']

class FormPackageForm(forms.ModelForm):
    class Meta:
        model = FormPackage
        fields = ['name', 'organization']  # ✅ removed package_type

class PackageFormForm(forms.ModelForm):
    class Meta:
        model = PackageForm
        fields = ['pdf_template', 'html_template_name', 'order']


class IRBInitialForm(forms.ModelForm):
    class Meta:
        model = IRBSubmission
        fields = [
            'protocol_title',
            'short_title',
            'description',
            'site_type',
            'external_irb',
            'principal_investigator',
            'pi_financial_interest',
        ]

        widgets = {
            'protocol_title': forms.TextInput(attrs={'class': 'form-control'}),
            'short_title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'site_type': forms.RadioSelect(),
            'external_irb': forms.RadioSelect(),
            'pi_financial_interest': forms.RadioSelect(),
            'principal_investigator': forms.Select(attrs={'class': 'form-select'}),
        }

class IRBFundingInfoForm(forms.ModelForm):
    class Meta:
        model = IRBSubmission
        fields = ['funding_additional_info']
        widgets = {
            'funding_additional_info': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3, 'placeholder': 'Enter any additional funding details...'
            }),
        }

class IRBDocumentForm(forms.ModelForm):
    class Meta:
        model = IRBDocument
        fields = [
            'document_type',
            'name',
            'version',
            'file',
            'category',
            'category_description'
        ]
        widgets = {
            'document_type': forms.HiddenInput(),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'version': forms.TextInput(attrs={'class': 'form-control'}),
            'file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'category_description': forms.TextInput(attrs={'class': 'form-control'}),
        }
class IRBStudyScopeForm(forms.ModelForm):
    class Meta:
        model = IRBSubmission
        fields = ['uses_drug_or_biologic', 'uses_device']
        widgets = {
            'uses_drug_or_biologic': forms.RadioSelect(choices=[(True, 'Yes'), (False, 'No')]),
            'uses_device': forms.RadioSelect(choices=[(True, 'Yes'), (False, 'No')]),
        }

class IRBStudyDrugForm(forms.ModelForm):
    class Meta:
        model = IRBSubmission
        fields = ['under_fda_ind', 'ind_numbers']
        widgets = {
            'under_fda_ind': forms.RadioSelect(choices=[(True, 'Yes'), (False, 'No')]),
            'ind_numbers': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., IND12345'}),
        }
class IRBStudyDeviceForm(forms.ModelForm):
    class Meta:
        model = IRBSubmission
        fields = ['device_exemption_status', 'evaluates_device_safety_effectiveness']
        widgets = {
            'device_exemption_status': forms.Select(choices=[
                ('IDE', 'IDE'),
                ('Abbreviated IDE', 'Claim of Abbreviated IDE (Nonsignificant Risk Device)'),
                ('Exempt', 'Exempt from IDE Requirements'),
                ('Not Applicable', 'Not Applicable'),
            ]),
            'evaluates_device_safety_effectiveness': forms.RadioSelect(choices=[(True, 'Yes'), (False, 'No')]),
        }
