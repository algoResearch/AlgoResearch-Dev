from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test, login_required
from .models import User, Organization, Opportunity, FormPackage, PackageForm
from .forms import OrganizationForm, CustomUserCreationForm, OpportunityForm, CreateOpportunityForm, PackageFormForm, FormPackageForm


AVAILABLE_FORM_TEMPLATES = [
    ("admin/fill_out_sf424.html", "SF-424 Form"),
    ("admin/RR_Budget.html", "RR Budget"),
]

def it_admin_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None and user.is_superuser:  # Only allow superusers for IT Admin
            login(request, user)
            return redirect('it_admin_dashboard')  # Redirect to IT Admin Dashboard
        else:
            messages.error(request, 'Invalid credentials or insufficient permissions.')

    return render(request, 'it_admin/it_admin_login.html')

def is_it_admin(user):
    """Check if the user is an IT Admin (superuser)."""
    return user.is_superuser

@login_required
@user_passes_test(is_it_admin)
def it_admin_dashboard(request):
    """
    IT Admin Dashboard: Display an overview of organizations and users.
    """
    # Fetch all organizations
    organizations = Organization.objects.all()

    # Count total users and organizations
    total_users = User.objects.count()
    total_organizations = organizations.count()

    # Context for the dashboard
    context = {
        'user': request.user, 
        'organizations': organizations,  # Pass organizations to template
        'total_users': total_users,
        'total_organizations': total_organizations,
    }

    return render(request, 'it_admin/it_admin_dashboard.html', context)

@user_passes_test(lambda u: u.is_superuser)  # Ensure only superusers can access
def organization_list(request):
    organizations = Organization.objects.all()
    return render(request, 'it_admin/organization_list.html', {'organizations': organizations})

def add_organization(request):
    if request.method == 'POST':
        form = OrganizationForm(request.POST)
        if form.is_valid():
            organization = form.save(commit=False)
            organization.logo = 'organization_logos/logo-small.svg'  # Default logo path
            organization.save()
            messages.success(request, f"Organization '{organization.name}' created successfully!")
            return redirect('organization_list')
        else:
            messages.error(request, 'There was an error creating the organization.')
    else:
        form = OrganizationForm()

    return render(request, 'it_admin/add_organization.html', {'form': form})

@user_passes_test(lambda u: u.is_superuser)
def manage_users(request):
    users = User.objects.all()

    if request.method == 'POST':
        username = request.POST.get('username')
        role = request.POST.get('role')

        # Create a new user
        user = User.objects.create_user(username=username, password='defaultpassword')
        user.role = role  # Assign role
        user.save()

        messages.success(request, 'User created successfully!')
        return redirect('manage_users')

    return render(request, 'it_admin/manage_users.html', {'users': users})

def it_create_user(request):
    organizations = Organization.objects.all()  # Fetch all organizations to display in the dropdown

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        organization_id = request.POST.get('organization')  # Get the selected organization from the form

        if form.is_valid() and organization_id:
            user = form.save(commit=False)
            user.organization_id = organization_id  # Assign the organization to the user
            user.save()
            messages.success(request, 'User created successfully and assigned to the organization!')
            return redirect('it_admin_dashboard')  # Redirect to a relevant page
        else:
            messages.error(request, 'Error creating user. Please check the form and ensure an organization is selected.')
    else:
        form = CustomUserCreationForm()

    # Pass the form and organizations to the template
    return render(request, 'it_admin/it_create_user.html', {'form': form, 'organizations': organizations})

@user_passes_test(lambda u: u.is_superuser)
def it_create_opportunity(request):
    if request.method == 'POST':
        form = CreateOpportunityForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Opportunity created successfully.")
            return redirect('it_admin_dashboard')  # or another overview page
    else:
        form = CreateOpportunityForm()

    return render(request, 'it_admin/it_create_opportunity.html', {'form': form})

# it_admin_views.py

@login_required
@user_passes_test(is_it_admin)
def create_form_package(request):
    if request.method == "POST":
        name = request.POST.get("name")
        package_type = request.POST.get("package_type")
        selected_templates = request.POST.getlist("form_templates")

        if not name or not package_type:
            messages.error(request, "Name and Package Type are required.")
        else:
            package = FormPackage.objects.create(name=name, package_type=package_type)

            for index, template_path in enumerate(selected_templates):
                PackageForm.objects.create(
                    package=package,
                    html_template_name=template_path,
                    order=index
                )

            messages.success(request, "Form Package created successfully!")
            return redirect("it_admin_dashboard")

    return render(request, "it_admin/create_form_package.html", {
        "form_templates": AVAILABLE_FORM_TEMPLATES,
        "package_types": FormPackage.PACKAGE_TYPE_CHOICES,
    })