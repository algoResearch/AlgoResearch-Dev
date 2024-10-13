from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, Experiment, AdminCreatedForm, FormField  # Import your custom User and Experiment models
from .models import Animal, Observation, Sample, Dose, Message, AdminPDFTemplate
from pytz import common_timezones


class UpdateProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'institution', 'role', 'location', 'profile_picture']
        widgets = {
            'profile_picture': forms.FileInput(),  # Ensure file input widget is used
        }



class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    institution = forms.CharField(max_length=100, required=False)
    role = forms.CharField(max_length=100, required=False)
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

class ExperimentForm(forms.ModelForm):
    class Meta:
        model = Experiment
        fields = ['name', 'number_of_animals', 'number_of_groups', 'investigators', 'rfid_required', 'max_per_cage', 'weigh_in_interval', 'drug', 'strain', 'weight_schedule', 'experiment_duration']

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


    
class OverviewForm(forms.ModelForm):
    class Meta:
        model = Animal
        fields = ['tail', 'ear', 'tag', 'donor', 'tracking_date', 'age', 'sex', 'species', 'strain', 'drug']
        widgets = {
            'tracking_date': forms.DateInput(attrs={'type': 'date'}),
            'age': forms.NumberInput(attrs={'placeholder': 'Age in Days'}),
            'drug': forms.CheckboxSelectMultiple(),
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
    
class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['content', 'attachment']

    content = forms.CharField(required=False)  # Explicitly make content optional

    def clean(self):
        cleaned_data = super().clean()
        content = cleaned_data.get('content')
        attachment = cleaned_data.get('attachment')

        # Allow either content or attachment, but at least one is required
        if not content and not attachment:
            raise forms.ValidationError("You must provide either a message or an attachment.")

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
