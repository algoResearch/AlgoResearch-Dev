from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.http import JsonResponse
from dashboard.models import User, Organization
from django.core.paginator import Paginator

from dashboard.forms import OrganizationITAdminCreationForm

def is_org_it_admin(user):
    """Check if the user is an Organizational IT Admin."""
    return user.role == 'org_it_admin'

# Organizational IT Admin Login View
def org_it_admin_login(request):
    """
    Login view for Organizational IT Admins.
    """
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None and user.role == 'org_it_admin':
            login(request, user)
            return redirect('org_it_admin_dashboard')  # Redirect to the Organizational IT Admin dashboard
        else:
            messages.error(request, 'Invalid credentials or insufficient permissions.')

    return render(request, 'org_it_admin/org_it_admin_login.html')

# Organizational IT Admin Dashboard View
@login_required
@user_passes_test(is_org_it_admin)
def org_it_admin_dashboard(request):
    """
    Dashboard view for Organizational IT Admins.
    """
    organization = request.user.organization
    total_users = User.objects.filter(organization=organization).count()

    context = {
        'organization': organization,
        'total_users': total_users,
    }

    return render(request, 'org_it_admin/org_it_admin_dashboard.html', context)

# Organizational IT Admin Manage Users View
@login_required
@user_passes_test(is_org_it_admin)
def org_it_admin_manage_users(request):
    """
    View to manage users within the organization.
    """
    organization = request.user.organization
    users = User.objects.filter(organization=organization)

    if request.method == 'POST':
        form = OrganizationITAdminCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.organization = organization
            user.save()
            messages.success(request, 'User created successfully!')
            return redirect('org_it_admin_manage_users')
        else:
            messages.error(request, 'There was an error creating the user.')
    else:
        form = OrganizationITAdminCreationForm()

    context = {
        'organization': organization,
        'users': users,
        'form': form,
    }

    return render(request, 'org_it_admin/org_it_admin_manage_users.html', context)

# Organizational IT Admin Settings View
@login_required
@user_passes_test(is_org_it_admin)
def org_it_admin_settings(request):
    """
    View to manage Organizational IT Admin settings.
    """
    organization = request.user.organization

    if request.method == 'POST':
        organization.name = request.POST.get('organization_name', organization.name)
        organization.save()
        messages.success(request, 'Organization settings updated successfully!')
        return redirect('org_it_admin_settings')

    context = {
        'organization': organization,
    }

    return render(request, 'org_it_admin/org_it_admin_settings.html', context)



@login_required
def org_it_admin_user_list(request):
    org_id = request.user.organization.id  # Assuming the user has an organization
    users = User.objects.filter(organization_id=org_id)  # Adjust query based on models
    paginator = Paginator(users, 10)  # 10 users per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'org_it_admin/org_it_user_list.html', {
        'users': page_obj,  # Pass paginated users
        'org_id': org_id,   # Pass org_id
    })
