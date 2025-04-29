# utils/project_attachments.py
import os
from django.conf import settings
from dashboard.models import ProjectAttachment
from django.core.files.base import ContentFile
from django.utils.text import slugify
import hashlib

# myapp/utils/get_base_template.py

def get_base_template(user):
    if user.position_type in [
        'fund_manager', 'agency_user', 'nih_sro',
        'nih_chair', 'nih_board_member', 'admin', 'principal_admin'
    ]:
        return "admin/base_admin_dashboard.html"
    return "base_dashboard.html"
