from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.utils.timezone import now
import xml.etree.ElementTree as ET
from django.contrib.auth.decorators import user_passes_test, login_required
from .models import User, Organization, Opportunity, FormPackage, PackageForm
from .forms import *
from myapp.utils.parsing import parse_date  # wherever your parse_date lives
from datetime import datetime
from dashboard import user_views
from dashboard.user_views import send_2fa_code 
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
def import_opportunities_from_url(url):
    import requests
    import xml.etree.ElementTree as ET
    from dashboard.models import Opportunity, Agency
    from datetime import datetime, date
    from django.utils.timezone import now
    from django.utils.text import slugify

    def parse_date(raw):
        try:
            return datetime.strptime(raw, "%m%d%Y").date()
        except Exception as e:
            print(f"⚠️ Error parsing date '{raw}': {e}")
            return None

    def truncate(val, max_length=255):
        return val[:max_length] if val else val

    print(f"🌐 Attempting to stream XML's from: {url}")
    try:
        response = requests.get(url, stream=True, timeout=20)
        response.raise_for_status()
        print("✅ XML stream opened successfully.")
    except Exception as e:
        print(f"❌ Failed to fetch XML: {e}")
        return

    ns_uri = "http://apply.grants.gov/system/OpportunityDetail-V1.0"
    imported_count = 0
    cutoff_date = date.today()

    try:
        context = ET.iterparse(response.raw, events=("end",))
    except Exception as e:
        print(f"❌ Failed to parse XML stream: {e}")
        return

    try:
        for i, (event, elem) in enumerate(context):
            if elem.tag.endswith("OpportunitySynopsisDetail_1_0"):
                try:
                    def get_text(tag):
                        el = elem.find(f"{{{ns_uri}}}{tag}")
                        return el.text.strip() if el is not None and el.text else ""

                    number = get_text("OpportunityNumber")
                    close_date = parse_date(get_text("CloseDate"))
                    print(f"🔍 Found opportunity: {number} | CloseDate: {close_date}")

                    if not close_date or close_date < cutoff_date:
                        print(f"⏩ Skipping {number} (closed or invalid)")
                        elem.clear()
                        continue

                    if Opportunity.objects.filter(number=number).exists():
                        print(f"🔁 Already exists: {number}")
                        elem.clear()
                        continue

                    title = truncate(get_text("OpportunityTitle") or "Untitled", 255)
                    agency_name = truncate(get_text("AgencyName"), 255)
                    comp_id = truncate(get_text("AgencyCode"), 100)
                    comp_title = truncate(get_text("CategoryExplanation"), 255)
                    cfda = truncate(get_text("CFDANumbers"), 100)
                    open_date = parse_date(get_text("PostDate"))

                    agency_ref = None
                    if agency_name:
                        agency_ref, _ = Agency.objects.get_or_create(
                            name=agency_name,
                            defaults={"slug": slugify(agency_name)}
                        )

                    Opportunity.objects.create(
                        number=number,
                        title=title,
                        comp_id=comp_id,
                        comp_title=comp_title,
                        agency_ref=agency_ref,
                        cfda=cfda,
                        open_date=open_date,
                        close_date=close_date,
                        created_at=now(),
                        updated_at=now()
                    )

                    print(f"✅ Imported: {number} - {title}")
                    imported_count += 1


                except Exception as e:
                    print(f"❌ Error processing opportunity: {e}")

                elem.clear()

    except Exception as e:
        print(f"❌ Outer loop error: {e}")

    print(f"\n✅ Finished. Total imported: {imported_count}")

def import_opportunities_from_xml(filepath):
    import random
    import xml.etree.ElementTree as ET
    from datetime import datetime
    from django.utils.timezone import now
    from dashboard.models import (
        Opportunity,
        FormPackage,
        Project,
        SubmittedPackage,
    )

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

    # Fetch all available form packages once
    form_packages = list(FormPackage.objects.all())

    for i, opp in enumerate(root.findall('.//ns:OpportunitySynopsisDetail_1_0', ns)):
        if i >= 5:
            print("⛔ Limit reached (5 opportunities). Stopping early for test.")
            break
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

        # Randomly pick a form package
        selected_package = random.choice(form_packages) if form_packages else None

        # Create Opportunity
        opportunity = Opportunity.objects.create(
            number=number,
            title=title,
            comp_id=comp_id,
            comp_title=comp_title,
            agency=agency,
            cfda=cfda,
            open_date=open_date,
            close_date=close_date,
            form_package=selected_package,
            created_at=now(),
            updated_at=now()
        )

        # Create Project
        project = Project.objects.create(
            name=title[:100],
            sponsor=agency,
            prime_sponsor=agency,
            sponsor_deadline=close_date,
        )

        # Link Project to Opportunity
        opportunity.project = project
        opportunity.save()

        # Create SubmittedPackage (as draft)
        if selected_package:
            SubmittedPackage.objects.create(
                user=None,  # Assign a user here if needed
                org_id=1,
                project=project,
                opportunity=opportunity,
                package_id=selected_package.id,
                is_draft=True,
                submission_name=f"Draft for {title[:50]}",
                sf424_data={},
                rr_budget_data={},
                budget_periods=[],
                cumulative_totals={},
            )

        imported_count += 1
        print(f"✅ Imported opportunity: {number} - {title}")

    print(f"\n✅ Finished processing {imported_count} opportunities.")
def it_admin_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user and user.is_it_admin_user:
            request.session['pre_2fa_authenticated'] = True
            request.session['2fa_admin'] = True
            request.session['2fa_user_id'] = user.id
            send_2fa_code(request, user)
            return redirect('verify_2fa')
        else:
            messages.error(request, 'Invalid credentials or insufficient permissions.')

    return render(request, 'it_admin/it_admin_login.html')

def is_it_admin(user):
    return user.is_superuser or user.role in [
        'product_support', 'sales_rep', 'customer_success', 'implementation_rep'
    ]

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
@login_required
@user_passes_test(lambda u: u.is_superuser)
def it_create_it_admin_user(request):
    if request.method == 'POST':
        form = ITAdminCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'IT Admin user created successfully!')
            return redirect('it_admin_dashboard')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ITAdminCreationForm()

    return render(request, 'it_admin/it_create_it_admin.html', {
        'form': form,
    })

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

@login_required
@user_passes_test(lambda u: u.is_superuser)
def create_it_admin_user(request):
    if request.method == 'POST':
        form = ITAdminCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "IT Admin user created successfully!")
            return redirect('it_admin_dashboard')
    else:
        form = ITAdminCreationForm()
    return render(request, 'it_admin/create_it_admin_user.html', {'form': form})


@login_required
def it_admin_create_user(request, org_id):
    # ✅ Ensure only IT Admins access this
    if not request.user.is_it_admin_user:
        return redirect('dashboard')  # Or return a 403

    organization = get_object_or_404(Organization, id=org_id)

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST, organization=organization)
        if form.is_valid():
            user = form.save(commit=False)
            user.organization = organization
            user.save()
            return redirect('it_admin_org_user_list', org_id=org_id)  # 👈 make sure this exists
    else:
        form = CustomUserCreationForm(organization=organization)

    return render(request, 'it_admin/create_user.html', {
        'form': form,
        'organization': organization
    })
@login_required
def it_admin_org_user_list(request, org_id):
    if not request.user.is_it_admin_user:
        return redirect('dashboard')

    organization = get_object_or_404(Organization, id=org_id)
    users = User.objects.filter(organization=organization)

    return render(request, 'it_admin/org_user_list.html', {
        'organization': organization,
        'users': users,
    })

@login_required
def select_org_for_user_creation(request):
    if not request.user.is_it_admin_user:
        return redirect('dashboard')

    organizations = Organization.objects.all()

    return render(request, 'it_admin/select_org.html', {
        'organizations': organizations
    })

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