import os
import hashlib
from django.conf import settings
from django.core.files.base import ContentFile
from dashboard.models import ProjectAttachment


def attach_pdf_to_project(project, pdf_path, label, uploaded_by=None):
    """
    Attaches a PDF at `pdf_path` to the project if not already attached (hash-checked).
    """
    if not os.path.exists(pdf_path):
        print(f"❌ Skipping missing file: {pdf_path}")
        return

    with open(pdf_path, 'rb') as f:
        file_data = f.read()
    file_hash = hashlib.sha256(file_data).hexdigest()

    if ProjectAttachment.objects.filter(project=project, file_hash=file_hash).exists():
        print(f"⚠️ Already attached: {os.path.basename(pdf_path)}")
        return

    attachment = ProjectAttachment(
        project=project,
        uploaded_by=uploaded_by,
        file_hash=file_hash
    )
    attachment.file.save(os.path.basename(pdf_path), ContentFile(file_data), save=True)
    print(f"📎 Attached: {os.path.basename(pdf_path)}")
