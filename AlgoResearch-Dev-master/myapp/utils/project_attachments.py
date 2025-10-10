# utils/project_attachments.py
import os
from django.conf import settings
from dashboard.models import ProjectAttachment
from django.core.files.base import ContentFile
from django.utils.text import slugify
import hashlib


def attach_submission_pdf(submission, form_type, filename_prefix):
    """
    Saves a generated PDF (if it exists) for a submission as a ProjectAttachment.

    :param submission: SubmittedPackage instance
    :param form_type: str, like "RR_Other_Information"
    :param filename_prefix: str, like "RR_Other_Information"
    """
    pdf_filename = f'{filename_prefix}_{submission.submission_name}.pdf'
    pdf_path = os.path.join(settings.MEDIA_ROOT, 'generated_pdfs', pdf_filename)

    if os.path.exists(pdf_path):
        with open(pdf_path, 'rb') as f:
            file_content = f.read()

        file_hash = hashlib.md5(file_content).hexdigest()

        already_exists = ProjectAttachment.objects.filter(
            project=submission.project,
            file_hash=file_hash
        ).exists()

        if not already_exists:
            ProjectAttachment.objects.create(
                project=submission.project,
                file=ContentFile(file_content, name=pdf_filename),
                uploaded_by=None,  # System
                file_hash=file_hash
            )
