from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test, login_required
from .models import User, Organization
from .forms import OrganizationForm, CustomUserCreationForm

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
        form = OrganizationForm(request.POST, request.FILES)  # Handle file uploads
        if form.is_valid():
            form.save()
            messages.success(request, 'Organization created successfully!')
            return redirect('organization_list')  # Redirect to the organization list page
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

