from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, Experiment, AdminCreatedForm, FormField, Task, Cage, Animal, Conversation, Attachment# Import your custom User and Experiment models
from .models import Animal, Observation, Sample, Dose, Message, AdminPDFTemplate
from pytz import common_timezones
from django.utils import timezone

class UpdateProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'institution', 'role', 'location', 'profile_picture', 'profile_banner']
        widgets = {
            'profile_picture': forms.FileInput(),
            'profile_banner': forms.FileInput(),  # For banner upload
        }

class BannerUploadForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['profile_banner']
        widgets = {
            'profile_banner': forms.FileInput(attrs={'class': 'form-control'}),
        }

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
    last_name = forms.CharField(max_length=30, required=True)
    institution = forms.CharField(max_length=100, required=False)
    role = forms.ChoiceField(choices=User.ROLE_CHOICES, required=True, label="Role")
    location = forms.CharField(max_length=100, required=False)

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "institution", "role", "location", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add Bootstrap classes to each field
        self.fields['username'].widget.attrs.update({'class': 'form-control shadow-sm', 'placeholder': 'Enter Username'})
        self.fields['first_name'].widget.attrs.update({'class': 'form-control shadow-sm', 'placeholder': 'Enter First Name'})
        self.fields['last_name'].widget.attrs.update({'class': 'form-control shadow-sm', 'placeholder': 'Enter Last Name'})
        self.fields['email'].widget.attrs.update({'class': 'form-control shadow-sm', 'placeholder': 'Enter Email'})
        self.fields['institution'].widget.attrs.update({'class': 'form-control shadow-sm', 'placeholder': 'Enter Institution'})
        self.fields['role'].widget.attrs.update({'class': 'form-control shadow-sm', 'placeholder': 'Enter Role'})
        self.fields['location'].widget.attrs.update({'class': 'form-control shadow-sm', 'placeholder': 'Enter Location'})
        self.fields['password1'].widget.attrs.update({'class': 'form-control shadow-sm', 'placeholder': 'Enter Password'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control shadow-sm', 'placeholder': 'Confirm Password'})

    def save(self, commit=True, organization=None):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.institution = self.cleaned_data["institution"]
        user.role = self.cleaned_data["role"]
        user.location = self.cleaned_data["location"]

        # Assign organization to the user
        if organization:
            user.organization = organization

        if commit:
            user.save()
        return user
    


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'email', 'profile_picture']  # Include profile_picture


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
            'age',
            'sex',
            'species',
            'strain',
            'strains',
            'drugs',
            'is_removed',
            'is_active',
        ]
        widgets = {
            'tracking_date': forms.DateInput(attrs={'type': 'date'}),
            'age': forms.NumberInput(attrs={'placeholder': 'Age in Days'}),
            'strain': forms.CheckboxSelectMultiple(),
        }

class ObservationForm(forms.ModelForm):
    class Meta:
        model = Observation
        fields = ['category', 'score']  # Replace 'name' with 'category'
        widgets = {
            'score': forms.NumberInput(attrs={'min': 1, 'max': 5}),
        }

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
    content = forms.CharField(required=False, widget=forms.Textarea(attrs={'placeholder': 'Type a message...'}))
    attachment = forms.FileField(required=False)

    class Meta:
        model = Message
        fields = ['content', 'attachment']  # Attachment is included

    def clean(self):
        cleaned_data = super().clean()
        content = cleaned_data.get('content')
        attachment = cleaned_data.get('attachment')

        if not content and not attachment:
            raise forms.ValidationError("Please enter a message or attach a file.")

        if attachment:
            if attachment.size > 10 * 1024 * 1024:  # 10MB size limit
                raise forms.ValidationError("File size should not exceed 10MB.")
            # Optionally, check file type (e.g., allow only images/PDFs)
            if not attachment.name.lower().endswith(('.jpg', '.jpeg', '.png', '.pdf')):
                raise forms.ValidationError("Only .jpg, .jpeg, .png, and .pdf files are allowed.")
        return cleaned_data

    

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
    class Meta:
        model = Task
        fields = ['title', 'description', 'due_date', 'assigned_to']

    assigned_to = forms.ModelMultipleChoiceField(queryset=User.objects.all(), widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, **kwargs):
        experiment = kwargs.pop('experiment', None)
        super().__init__(*args, **kwargs)
        if experiment:
            # Use the User objects linked to the collaborators
            self.fields['assigned_to'].queryset = User.objects.filter(
                id__in=experiment.collaborators.values_list('user', flat=True)
            )

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