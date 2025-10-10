from __future__ import annotations
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

def default_profile_picture(request):
    return {"DEFAULT_PROFILE_PICTURE": getattr(settings, "DEFAULT_PROFILE_PICTURE", None)}

def organization_context(request):
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {}
    org = getattr(user, "organization", None)
    return {"user": user, "organization": org} if org else {}

def is_committee_member_context(request):
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {}
    try:
        from dashboard.models import CommitteeMember
        return {"is_committee_member": CommitteeMember.objects.filter(user=user).exists()}
    except Exception as e:
        logger.exception("is_committee_member_context failed: %s", e)
        return {"is_committee_member": False}

def default_form_context(request):
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {"default_form_id": None}
    try:
        from dashboard.models import PDFTemplate
        org = getattr(user, "organization", None)
        if not org:
            return {"default_form_id": None}
        default_form = PDFTemplate.objects.filter(organization_id=org.id).first()
        return {"default_form_id": default_form.id if default_form else None}
    except Exception as e:
        logger.exception("default_form_context failed: %s", e)
        return {"default_form_id": None}

def unread_conversations_count(request):
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {"unread_conversations_count": 0, "unread_notifications_count": 0}
    try:
        from django.db.models import Q
        from dashboard.models import Conversation, InboxNotification
        conversations = (
            Conversation.objects
            .filter(
                Q(messages__is_read=False),
                Q(user1=user) | Q(user2=user) | Q(group_members__user=user),
            )
            .exclude(messages__sender=user)
            .distinct()
        )
        conv_count = conversations.count()
        notif_count = InboxNotification.objects.filter(user=user, is_read=False).count()
        logger.debug("Unread: conversations=%s notifications=%s", conv_count, notif_count)
        return {
            "unread_conversations_count": conv_count,
            "unread_notifications_count": notif_count,
        }
    except Exception as e:
        logger.exception("unread_conversations_count failed: %s", e)
        return {"unread_conversations_count": 0, "unread_notifications_count": 0}

def committee_membership_context(request):
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {}
    try:
        from dashboard.models import IACUCMember, IRBMember
        org = getattr(user, "organization", None)
        if not org:
            return {}
        return {
            "is_iacuc_member": IACUCMember.objects.filter(
                user=user, committee__organization=org, is_active=True
            ).exists(),
            "is_irb_member": IRBMember.objects.filter(
                user=user, committee__organization=org, is_active=True
            ).exists(),
        }
    except Exception as e:
        logger.exception("committee_membership_context failed: %s", e)
        return {"is_iacuc_member": False, "is_irb_member": False}

__all__ = [
    "default_profile_picture",
    "organization_context",
    "is_committee_member_context",
    "default_form_context",
    "unread_conversations_count",
    "committee_membership_context",
]
