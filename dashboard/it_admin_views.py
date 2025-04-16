from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.utils.timezone import now
import xml.etree.ElementTree as ET
from django.contrib.auth.decorators import user_passes_test, login_required
from .models import User, Organization, Opportunity, FormPackage, PackageForm
from .forms import OrganizationForm, CustomUserCreationForm, OpportunityForm, CreateOpportunityForm, PackageFormForm, FormPackageForm
from myapp.utils.parsing import parse_date  # wherever your parse_date lives
from datetime import datetime
import os
# Map HTML templates to form_type values from PackageForm.FORM_TYPE_CHOICES
AVAILABLE_FORM_TEMPLATES = [
    ("sf424", "admin/fill_out_sf424.html", "SF-424 Form"),
    ("rr_budget", "admin/RR_Budget.html", "RR Budget"),
    ("phs_plan", "admin/fill_out_PHS_Plan.html", "PHS Research Plan"),
    ("skp", "admin/senior_key_person_form.html", "Senior Key Person"),
    ("site", "admin/project_performance_site.html", "Project Performance Site"),
    ("rr_other_info", "admin/RR_Other_Information.html", "RR Other Information"),
    ("phs_cover", "admin/phs_cover_page.html", "PHS Cover Page"),
    ("phs_subjects", "admin/phs_human_subjects.html", "PHS Human Subjects"),
]

def import_opportunities_from_xml(filepath):
    from dashboard.models import Opportunity
    from datetime import datetime
    from django.utils.timezone import now
    import xml.etree.ElementTree as ET

    def parse_date(raw):
        if not raw:
            return None
        try:
            return datetime.strptime(raw, '%m%d%Y').date()
        except ValueError:
            return None

    def truncate(val, max_length=255):
        return val[:max_length] if val else val

    print(f"📄 Reading from: {filepath}")

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        print(f"🔍 First 500 characters:\n{content[:500]}")

    tree = ET.ElementTree(ET.fromstring(content))
    root = tree.getroot()

    ns_uri = 'http://apply.grants.gov/system/OpportunityDetail-V1.0'
    ns = {'ns': ns_uri}

    imported_count = 0
    cutoff_date = datetime(2025, 4, 16).date()

    for opp in root.findall('.//ns:OpportunitySynopsisDetail_1_0', ns):
        def get_text(tag):
            return opp.findtext(f'ns:{tag}', default='', namespaces=ns)

        close_date = parse_date(get_text('CloseDate'))

        if not close_date or close_date < cutoff_date:
            print(f"⏩ Skipping closed/expired: {get_text('OpportunityNumber')} - CloseDate={close_date}")
            continue

        number = truncate(get_text('OpportunityNumber'), 100)
        title = truncate(get_text('OpportunityTitle') or "Untitled Opportunity", 255)
        agency = truncate(get_text('AgencyName'), 255)
        comp_id = truncate(get_text('AgencyCode'), 100)
        comp_title = truncate(get_text('CategoryExplanation'), 255)
        cfda = truncate(get_text('CFDANumbers'), 100)
        open_date = parse_date(get_text('PostDate'))

        if Opportunity.objects.filter(number=number).exists():
            continue

        Opportunity.objects.create(
            number=number,
            title=title,
            comp_id=comp_id,
            comp_title=comp_title,
            agency=agency,
            cfda=cfda,
            open_date=open_date,
            close_date=close_date,
            created_at=now(),
            updated_at=now()
        )

        imported_count += 1
        print(f"✅ Imported opportunity: {number} - {title}")

    print(f"\n✅ Finished processing {imported_count} opportunities.")
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
        selected_templates = request.POST.getlist("form_templates")

        if not name:
            messages.error(request, "Name is required.")
        else:
            package = FormPackage.objects.create(name=name)

            for index, template_identifier in enumerate(selected_templates):
                # Match the template_identifier back to the full data
                for form_type, template_path, label in AVAILABLE_FORM_TEMPLATES:
                    if template_path == template_identifier:
                        PackageForm.objects.create(
                            package=package,
                            form_type=form_type,
                            html_template_name=template_path,
                            order=index
                        )
                        break

            messages.success(request, "Form Package created successfully!")
            return redirect("it_admin_dashboard")

    return render(request, "it_admin/create_form_package.html", {
        "form_templates": AVAILABLE_FORM_TEMPLATES,
    })
