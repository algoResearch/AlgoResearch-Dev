from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, Experiment  # Import your custom User and Experiment models
from .models import Animal, Observation, Sample, Dose, Message

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

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.institution = self.cleaned_data["institution"]
        user.role = self.cleaned_data["role"]
        user.location = self.cleaned_data["location"]

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

class ProfilePictureForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['profile_picture']



class OverviewForm(forms.ModelForm):
    class Meta:
        model = Animal
        fields = ['tail', 'ear', 'tag', 'donor', 'tracking_date', 'age', 'sex', 'species', 'strain']
        widgets = {
            'tracking_date': forms.DateInput(attrs={'type': 'date'}),
            'age': forms.NumberInput(attrs={'placeholder': 'Age in Days'}),
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
        fields = ['dose', 'stock_concentration', 'dose_volume']
        widgets = {
            'dose': forms.TextInput(attrs={'placeholder': 'Enter Dose'}),
            'stock_concentration': forms.TextInput(attrs={'placeholder': 'Enter Stock Concentration'}),
            'dose_volume': forms.TextInput(attrs={'placeholder': 'Enter Dose Volume'}),
        }



class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['content', 'attachment']

    def clean(self):
        cleaned_data = super().clean()
        content = cleaned_data.get('content')
        attachment = cleaned_data.get('attachment')

        if not content and not attachment:
            raise forms.ValidationError("You must provide either a message or an attachment.")
        