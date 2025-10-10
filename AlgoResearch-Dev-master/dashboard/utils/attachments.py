from django.core.files import File
from django.contrib import admin
from dashboard.models import ProjectAttachment
import os
from django.conf import settings
def create_project_attachment(file_url, user, project, source_folder="uploads"):
    if not file_url or file_url == "No file uploaded":
        return

    file_name = os.path.basename(file_url)
    relative_path = f"{source_folder}/{file_name}"
    full_path = os.path.join(settings.MEDIA_ROOT, relative_path)

    if not os.path.exists(full_path):
        print(f"⚠️ File not found: {full_path}")
        return

    if not ProjectAttachment.objects.filter(file=f"project_attachments/{file_name}", project=project).exists():
        with open(full_path, "rb") as f:
            django_file = File(f)
            attachment = ProjectAttachment(
                project=project,
                uploaded_by=user,
            )
            attachment.file.save(file_name, django_file, save=True)
            print(f"📎 ProjectAttachment created for {file_name}")
