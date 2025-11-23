
# views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import transaction
from dashboard.forms import DeviationAuthorizationForm
from dashboard.models import SubmittedPackage, Project, Opportunity
from django.utils import timezone

def user_can_edit_project(user, project):  # you likely already have this
    return True  # replace with your real check

@login_required
@transaction.atomic
def deviation_authorization(request, org_id, package_id, project_id):
    """Create/edit Deviation Authorization text and save to SubmittedPackage (draft or final)."""
    # Resolve project
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        messages.error(request, "Project not found.")
        return redirect("organization_dashboard", org_id=org_id)

    # Load existing draft (if any)
    draft = SubmittedPackage.objects.filter(
        org_id=org_id,
        package_id=package_id,
        project=project,
        is_draft=True
    ).first()

    initial = (draft.deviation_authorization_data or {}) if draft else {}

    if request.method == "POST":
        form = DeviationAuthorizationForm(request.POST)
        if form.is_valid():
            data = {
                "omb_number": "3145-0058",
                "expiration_date": "10/31/2025",
                "deviation_text": form.cleaned_data.get("deviation_text", "").strip(),
                "updated_at": timezone.now().isoformat(),
            }

            if "save_draft" in request.POST:
                if not user_can_edit_project(request.user, project):
                    messages.error(request, "You do not have permission to edit this project.")
                    return redirect("package_display", org_id=org_id, package_id=package_id, project_id=project_id)

                # upsert draft
                draft, _created = SubmittedPackage.objects.get_or_create(
                    org_id=org_id,
                    package_id=package_id,
                    project=project,
                    is_draft=True,
                    defaults={
                        "submission_name": f"Draft - {project.name}",
                        "submission_date": timezone.now(),
                        "last_edited_by": request.user,
                    }
                )
                draft.deviation_authorization_data = data
                draft.last_edited_by = request.user
                draft.save()
                messages.success(request, "Deviation Authorization draft saved.")
                return redirect("specific_project_home", org_id=org_id, project_id=project_id)

            # Finalize into a non-draft submission slice or attach to an existing one you’re finalizing elsewhere
            final = SubmittedPackage.objects.filter(
                org_id=org_id, package_id=package_id, project=project, is_draft=False
            ).order_by("-submission_date").first()

            if not final:
                final = SubmittedPackage.objects.create(
                    user=request.user,
                    org_id=org_id,
                    package_id=package_id,
                    project=project,
                    submission_name=f"Submission - {project.name}",
                    submission_date=timezone.now(),
                    is_draft=False,
                )

            final.deviation_authorization_data = data
            final.save()
            messages.success(request, "Deviation Authorization saved.")
            return redirect("package_summary", org_id=org_id, package_id=package_id)

    else:
        form = DeviationAuthorizationForm(initial=initial)

    return render(
        request,
        "admin/deviation_authorization.html",
        {
            "form": form,
            "org_id": org_id,
            "package_id": package_id,
            "project_id": project_id,
        },
    )

@login_required
def download_deviation_authorization_pdf(request, org_id, package_id, project_id):
    submission = SubmittedPackage.objects.filter(
        org_id=org_id, package_id=package_id, project_id=project_id, is_draft=False
    ).order_by('-submission_date').first()

    if not submission or not submission.deviation_authorization_data:
        messages.error(request, "No Deviation Authorization data available.")
        return redirect("package_summary", org_id=org_id, package_id=package_id)

    html = render_to_string(
        "admin/deviation_authorization_answers.html",
        {"data": submission.deviation_authorization_data}
    )
    css = CSS(string="""
      @page { size: Letter; margin: 0.5in; }
      body { font-family: 'Times New Roman', serif; font-size: 11pt; }
      .title { text-align:center; font-size:18pt; font-weight:700; margin-bottom:4mm; }
      .omb { text-align:right; font-size:9pt; }
      .label { margin: 6pt 0; }
      .box { border:1px solid #000; background:#dfe6ff; padding:8pt; min-height:180pt; white-space:pre-wrap; }
    """)
    with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as tmp:
        HTML(string=html).write_pdf(tmp.name, stylesheets=[css])
        with open(tmp.name, "rb") as f:
            resp = HttpResponse(f.read(), content_type="application/pdf")
            resp["Content-Disposition"] = 'attachment; filename="Deviation_Authorization.pdf"'
            return resp
        