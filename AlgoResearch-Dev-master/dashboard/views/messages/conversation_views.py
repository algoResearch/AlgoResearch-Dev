from django.contrib import messages
from django.core import serializers
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.utils.timezone import now, timezone
from django.utils.dateformat import format as django_format
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
import base64
from myapp.utils.notifications import notify_user_ws
from myapp.utils.messages import create_message_user_entries
import time
from myapp.utils.image_tools import generate_group_photo
from myapp.utils.image_helpers import generate_group_profile_picture, generate_group_initials_picture
from django.db.models.functions import Replace
from django.urls import reverse
from django.core.serializers.json import DjangoJSONEncoder
from dashboard.scripts.generate_key import encrypt_message, get_conversation_key
from django.db.models import Q, F, Avg, Max, Min, Count, Case, When, IntegerField, BooleanField, ExpressionWrapper, OuterRef, Subquery, F
from django.utils import timezone
from django.utils.timezone import localtime, now
from django.utils.html import escape
from myapp.utils.get_base_template import get_base_template

from dashboard.models import (Conversation, Message, User, Notification, MessageUser, ConversationUser, Organization, InboxNotification, GroupMember, EventInvitation, Experiment, RFIDAssignment, WeightMeasurement, Collaborator, CalendarEvent, Comment, Friend, Cage, Animal, Sample, Dose, Observation, Comment)
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, authenticate
from django.contrib.auth.models import User
from django.contrib.messages import error  # Import specifically if needed
import pandas as pd
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.core.paginator import Paginator
import mimetypes
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import random
from django.contrib.auth import logout
from django.db import IntegrityError
from django.contrib.auth import get_user_model
from dashboard.forms import CustomUserCreationForm, UpdateProfileForm, ExperimentForm, UpdateGroupInfoForm
import json
from django.http import HttpResponseRedirect
from django.utils.safestring import mark_safe
from dashboard.forms import UserProfileForm
from dashboard.forms import ProfilePictureForm, MessageForm
from dashboard.forms import UpdateProfileForm, OverviewForm, ObservationForm, SampleForm, DoseForm
from django.views.decorators.http import require_http_methods
from django.utils.dateparse import parse_datetime
import csv
from dashboard.models import Invitation
from django.templatetags.static import static
from django.template.loader import render_to_string
from datetime import date, datetime
from django.utils import timezone
import pytz
from django.db.models import Prefetch

channel_layer = get_channel_layer()

import logging
# Assuming you have access to request.user and the last_message_time is in UTC.

logger = logging.getLogger('performance')
# Set up logging

from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.contrib.staticfiles.storage import staticfiles_storage

@login_required
def fetch_messages(request, org_id=None):
    user = request.user
    organization = None
    if org_id:
        organization = get_object_or_404(Organization, id=org_id)

    if request.user.position_type == 'it_admin' or request.path.startswith('/it/'):
        base_template = 'it_admin/it_admin_base_dashboard.html'
       
    elif org_id and request.path.startswith(f'/{org_id}/admin/'):
        base_template = 'admin/base_admin_dashboard.html'
    else:
        base_template = 'base/base_dashboard.html'

    active_tab = request.GET.get("tab", "messages")
    selected_notification_id = request.GET.get("notification_id", None)

    conversation_list = []
    notification_list = []
    unread_messages_count = 0
    unread_notifications_count = 0
    selected_notification = None

    if active_tab == "messages":
        conversations = Conversation.objects.filter(
            Q(user1=user) | Q(user2=user) | Q(group_members__user=user)
        ).annotate(
            last_deleted_at=Subquery(
                ConversationUser.objects.filter(
                    user=user,
                    conversation=OuterRef('pk')
                ).values('last_deleted_at')[:1]
            ),
            last_message_time=Max('messages__timestamp'),
            unread_count=Count(
                'messages',
                filter=Q(messages__is_read=False) & ~Q(messages__sender=user) &
                       (Q(messages__timestamp__gt=F('last_deleted_at')) | Q(last_deleted_at__isnull=True))
            ),
            is_muted=ExpressionWrapper(
                Q(mute_notifications__in=[user]),
                output_field=BooleanField()
            )
        ).filter(
            Q(last_deleted_at__isnull=True) |
            Q(last_message_time__gt=F('last_deleted_at'))
        ).distinct()

        for convo in conversations:
            if convo.last_deleted_at:
                last_msg = Message.objects.filter(
                    conversation=convo,
                    timestamp__gt=convo.last_deleted_at
                ).exclude(
                    message_users__user=user,
                    message_users__deleted_at__isnull=False
                ).order_by('-timestamp').first()
            else:
                last_msg = Message.objects.filter(
                    conversation=convo
                ).exclude(
                    message_users__user=user,
                    message_users__deleted_at__isnull=False
                ).order_by('-timestamp').first()

            last_message_time = last_msg.timestamp if last_msg else None

            last_message_preview = last_msg.get_decrypted_content() if last_msg else ""
            if last_msg and last_msg.attachment:
                mime_type, _ = mimetypes.guess_type(last_msg.attachment.name)
                if mime_type and mime_type.startswith('image/'):
                    last_message_preview = "[Image]"
                elif mime_type and mime_type.startswith('video/'):
                    last_message_preview = "[Video]"
                elif mime_type and mime_type.startswith('application/'):
                    last_message_preview = "[File]"

            if convo.type == 'private':
                other_user = convo.user2 if convo.user1 == user else convo.user1
                name = other_user.username
                user_obj = other_user 
                profile_picture = (
                    other_user.profile_picture.url if other_user.profile_picture
                    else static("img/default-profile.jpg")
                )
                
            else:
                name = convo.name.strip() if convo.name and convo.name.strip() else "Unnamed Group"
                profile_picture = (
                    convo.profile_picture.url if convo.profile_picture
                    else static("img/group-default.png")
                )

            unread_count = convo.unread_count
            unread_messages_count += unread_count

            conversation_list.append({
                'id': convo.id,
                'name': name,
                'user': user_obj if convo.type == 'private' else None,  # ✅ Add this
                'type': convo.type,
                'profile_picture': profile_picture,
                'unread_count': unread_count,
                'last_message_time': timezone.localtime(last_message_time) if last_message_time else timezone.make_aware(datetime.min),
                'last_message_preview': last_message_preview,
                'is_muted': bool(convo.is_muted), 
            })

        conversation_list.sort(
            key=lambda x: (
                x['is_muted'],
                -x['unread_count'],
                x['last_message_time'] or timezone.datetime.min
            ),
            reverse=True
        )

    notifications = InboxNotification.objects.filter(user=user).order_by('-timestamp')
    for notification in notifications:
        notification_list.append({
            'id': notification.id,
            'title': notification.title,
            'message': notification.message,
            'sender_name': notification.sender_name,
            'timestamp': notification.timestamp,
            'is_read': notification.is_read,
        })
        if not notification.is_read:
            unread_notifications_count += 1

    if selected_notification_id:
        try:
            selected_notification = InboxNotification.objects.get(id=selected_notification_id, user=user)
            if not selected_notification.is_read:
                selected_notification.is_read = True
                selected_notification.save()
        except InboxNotification.DoesNotExist:
            pass

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'conversations': conversation_list,
            'notifications': notification_list,
            'unread_messages_count': unread_messages_count,
            'unread_notifications_count': unread_notifications_count,
        })

    return render(request, 'conversations/conversations.html', {
        'conversations': conversation_list if active_tab == "messages" else [],
        'notifications': notification_list if active_tab == "notifications" else [],
        'selected_notification': selected_notification,
        'base_template': base_template,
        'unread_messages_count': unread_messages_count,
        'unread_notifications_count': unread_notifications_count,
        'organization': organization,
        'org_id': org_id if org_id else '',
      
        'active_tab': active_tab,
    })

@login_required
def fetch_notifications(request, org_id=None):
    user = request.user

    if user.is_it_admin_user:
        notifications = InboxNotification.objects.filter(user=user).order_by('-timestamp')
    else:
        notifications = InboxNotification.objects.filter(user=user, organization_id=org_id).order_by('-timestamp')

    notification_list = [
        {
            'id': notification.id,
            'title': notification.title,
            'message': notification.message,
            'sender_name': notification.sender_name or "System",
            'timestamp': notification.timestamp.isoformat(),
            'is_read': notification.is_read,
        }
        for notification in notifications
    ]

    unread_count = notifications.filter(is_read=False).count()

    return JsonResponse({
        'notifications': notification_list,
        'unread_count': unread_count,
    })
def get_invitation_response(event_id, user_id):
    try:
        invitation = EventInvitation.objects.get(event_id=event_id, invited_user_id=user_id)
        return invitation.status  # 'accepted', 'declined', or other possible states
    except EventInvitation.DoesNotExist:
        return None

logger = logging.getLogger(__name__)
@login_required
def conversation_view(request, org_id, conversation_id):
    user = request.user
    organization = get_object_or_404(Organization, id=org_id)
    is_admin = '/admin/' in request.path
    conversation = get_object_or_404(
        Conversation.objects.prefetch_related('group_members__user', 'mute_notifications').filter(
            Q(user1=user) | Q(user2=user) | Q(group_members__user=user),
            id=conversation_id
        )
    )
    if conversation.type == 'private':
        other_user = conversation.user2 if conversation.user1 == user else conversation.user1
        profile_picture = (
            other_user.profile_picture.url if other_user.profile_picture
            else static("img/default-profile.jpg")
        )
        conversation_name = other_user.get_full_name() or other_user.username or "Unnamed User"
    else:
        profile_picture = (
            conversation.profile_picture.url if conversation.profile_picture
            else static("img/group-default.png")
        )
        conversation_name = conversation.name.strip() if conversation.name and conversation.name.strip() else "Unnamed Group"

    conversations = Conversation.objects.filter(
        Q(user1=user) | Q(user2=user) | Q(group_members__user=user),
    ).annotate(
        last_message_time=Max('messages__timestamp')
    ).prefetch_related('mute_notifications').order_by('-last_message_time')

    conversation_list = []
    for convo in conversations:
        if convo.type == 'private':
            other_user = convo.user2 if convo.user1 == user else convo.user1
            name = other_user.username
            convo_picture = (
                other_user.profile_picture.url if other_user.profile_picture
                else static("img/default-profile.jpg")
            )
        else:
            name = convo.name.strip() if convo.name and convo.name.strip() else "Unnamed Group"      
            convo_picture = convo.profile_picture.url if convo.profile_picture else static("img/default-profile.jpg")
        conversation_list.append({
            'id': convo.id,
            'name': name,
            'type': convo.type,
            'profile_picture': convo_picture,
            'last_message_time': timezone.localtime(convo.last_message_time) if convo.last_message_time else None,
            'unread_count': convo.messages.filter(is_read=False).exclude(sender=user).count(),
            'is_muted': user in convo.mute_notifications.all(),
        })

    last_deleted_at = ConversationUser.objects.filter(
        user=user,
        conversation=conversation
    ).values_list('last_deleted_at', flat=True).first()

    # Filter messages the user hasn't deleted and are newer than deletion
    messages = Message.objects.filter(
        conversation=conversation
    ).exclude(
        message_users__user=user,
        message_users__deleted_at__isnull=False
    ).filter(
        Q(timestamp__gt=last_deleted_at) | Q(last_deleted_at__isnull=True)
    ).order_by('timestamp')
    unread_messages = messages.filter(is_read=False).exclude(sender=user)
    unread_message_ids = list(unread_messages.values_list('id', flat=True))
    unread_messages.update(is_read=True, read_timestamp=now())

    decrypted_messages = [
        {
            'id': msg.id,
            'sender': msg.sender,
            'content': msg.get_decrypted_content(),
            'timestamp': timezone.localtime(msg.timestamp),
            'read_at': msg.read_timestamp.isoformat() if msg.read_timestamp else None,
            'attachment_url': msg.attachment.url if msg.attachment else None,
            'attachment_name': msg.attachment.name if msg.attachment else None,
            'is_image': msg.attachment.name.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')) if msg.attachment else False,
            'is_pdf': msg.attachment.name.lower().endswith('.pdf') if msg.attachment else False,
            'is_video': msg.attachment.name.lower().endswith(('.mp4', '.avi', '.mkv', '.mov')) if msg.attachment else False,
        }
        for msg in messages
    ]

    if unread_message_ids:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        for msg_id in unread_message_ids:
            async_to_sync(channel_layer.group_send)(
                f"chat_{conversation.id}",
                {
                    "type": "read_receipt",
                    "message_id": msg_id,
                    "read_timestamp": now().isoformat(),
                },
            )

    # 👇 Check request.path here!
    if '/admin/' in request.path:
        base_template = 'admin/base_admin_dashboard.html'
    else:
        base_template = 'base/base_dashboard.html'

    context = {
        'conversation': conversation,
        'conversation_name': conversation_name,
        'profile_picture': profile_picture,
        'messages': decrypted_messages,
        'org_id': org_id,
        'selected_conversation_id': conversation_id,
        'active_tab': 'messages',
        'conversations': conversation_list,
        'is_muted': user in conversation.mute_notifications.all(),
        'base_template': base_template,  # 🛠️ Pass it into template
        'is_admin': is_admin,  # ✅ Add this
    }

    return render(request, 'conversations/conversations.html', context)

@login_required
def admin_conversation(request, org_id, conversation_id):
    return conversation(request, org_id, conversation_id)  # ✅ No extra `admin`
@login_required
def fetch_group_members(request, group_id):
    query = request.GET.get('query', '')
    try:
        conversation = Conversation.objects.get(id=group_id)
        if conversation.type != 'group':
            return JsonResponse({'error': 'Not a group conversation'}, status=400)

        group_members = conversation.members_new.filter(username__icontains=query)[:10]
        members_data = [{'id': member.id, 'username': member.username} for member in group_members]

        return JsonResponse({'members': members_data}, status=200)

    except Conversation.DoesNotExist:
        return JsonResponse({'error': 'Group not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def search_conversations(request, org_id):
    query = request.GET.get("query", "").strip()
    user = request.user
    is_admin = request.GET.get("is_admin") == "true"

    if not query:
        return JsonResponse({"conversations": [], "messages": [], "is_admin": is_admin})

    # Get all conversations the user is part of
    user_conversations = Conversation.objects.filter(
        Q(user1=user) | Q(user2=user) | Q(group_members__user=user)
    ).distinct()

    # Filter by name, participants, or group members matching the query
    conversations = user_conversations.filter(
        Q(name__icontains=query) |
        Q(user1__username__icontains=query) |
        Q(user2__username__icontains=query) |
        Q(group_members__user__username__icontains=query) |
        Q(group_members__user__first_name__icontains=query) |
        Q(group_members__user__last_name__icontains=query)
    ).distinct()

    # Build conversation results
    conversation_results = []
    for convo in conversations:
        if convo.type == "private":
            other_user = convo.user2 if convo.user1 == user else convo.user1
            name = other_user.get_full_name() or other_user.username or "Unnamed User"
            profile_picture = (
                other_user.profile_picture.url if other_user.profile_picture
                else static("img/default-profile.jpg")
            )
        else:
            name = convo.name.strip() if convo.name and convo.name.strip() else "Unnamed Group"
            profile_picture = (
                convo.profile_picture.url if convo.profile_picture
                else static("img/group-default.png")
            )

        conversation_results.append({
            "id": convo.id,
            "name": name,
            "type": convo.type,
            "profile_picture": profile_picture,
        })

    # Messages that match the query, in user’s conversations only
    messages = Message.objects.filter(
        Q(content__icontains=query),
        conversation__in=user_conversations
    ).select_related("conversation")

    message_results = []
    for msg in messages:
        conversation_name = (
            msg.conversation.name.strip() if msg.conversation.type == "group"
            else (
                msg.conversation.user2.get_full_name() if msg.conversation.user1 == user
                else msg.conversation.user1.get_full_name()
            )
        ) or "Unnamed Conversation"

        message_results.append({
            "id": msg.id,
            "content": msg.content,
            "conversation": {
                "id": msg.conversation.id,
                "name": conversation_name,
            },
            "title": f'"{msg.content}", in {conversation_name}',
        })

    return JsonResponse({
        "conversations": conversation_results,
        "messages": message_results,
        "is_admin": is_admin
    })

@login_required
def get_group_members(request, org_id, conversation_id):
    if request.method == 'GET':
        # Fetch the group members for the given conversation
        members = (
            GroupMember.objects.filter(conversation_id=conversation_id)
            .select_related('user')
            .values('user__id', 'user__username', 'user__profile_picture')
        )
        return JsonResponse({'status': 'success', 'members': list(members)}, safe=False)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)

@login_required
def conversation(request, org_id, conversation_id):
    user = request.user
    organization = get_object_or_404(Organization, id=org_id)
    is_admin = '/admin/' in request.path

    conversation = get_object_or_404(
        Conversation.objects.prefetch_related('group_members__user', 'mute_notifications').filter(
            Q(user1=user) | Q(user2=user) | Q(group_members__user=user),
            id=conversation_id
        )
    )
    # ✅ Deleted at logic (skip messages before user's delete)
    last_deleted_at = ConversationUser.objects.filter(
        user=user,
        conversation=conversation
    ).values('last_deleted_at').first()
    last_deleted_at = last_deleted_at['last_deleted_at'] if last_deleted_at else None

    # ✅ Display name and picture
    if conversation.type == 'private':
        other_user = conversation.user2 if conversation.user1 == user else conversation.user1
        conversation_name = other_user.get_full_name() or other_user.username
        
        profile_picture = (
            other_user.profile_picture.url if other_user.profile_picture
            else static("img/default-profile.jpg")
        )
    else:
        conversation_name = conversation.name.strip() if conversation.name else "Unnamed Group"
        profile_picture = (
            conversation.profile_picture.url if conversation.profile_picture
            else static("img/group-default.png")
        )

    group_members = (
        GroupMember.objects.filter(conversation=conversation).select_related('user')
        if conversation.type == 'group' else None
    )

    # ✅ Sidebar conversations
    conversations = Conversation.objects.filter(
        Q(user1=user) | Q(user2=user) | Q(group_members__user=user),
        
    ).annotate(
        last_message_time=Max('messages__timestamp'),
        last_deleted_at=Subquery(
            ConversationUser.objects.filter(
                conversation=OuterRef('pk'),
                user=user
            ).values('last_deleted_at')[:1]
        )
    ).filter(
        Q(last_deleted_at__isnull=True) | Q(last_message_time__gt=F('last_deleted_at'))
    ).order_by('-last_message_time')

    conversation_list = []
    for convo in conversations:
        if convo.type == 'private':
            other_user = convo.user2 if convo.user1 == user else convo.user1
            name = other_user.username
            convo_picture = (
                other_user.profile_picture.url if other_user.profile_picture
                else static("img/default-profile.jpg")
            )
            other_user = convo.user2 if convo.user1 == user else convo.user1
            # Add a temporary attribute for badge URL
            other_user.agency_badge_url = other_user.agency_badge.url if other_user.agency_badge else None
            conversation_user = other_user 
        else:
            name = convo.name.strip() if convo.name else "Unnamed Group"
            convo_picture = convo.profile_picture.url if convo.profile_picture else static("img/group-default.jpg")
            conversation_user = None

        conversation_list.append({
            'id': convo.id,
            'name': name,
            'type': convo.type,
            'profile_picture': convo_picture,
            'last_message_time': localtime(convo.last_message_time) if convo.last_message_time else None,
            'unread_count': convo.messages.filter(is_read=False).exclude(sender=user).count(),
            'is_muted': user in convo.mute_notifications.all(),
            'user': conversation_user,
        })
    # ✅ Get messages
    messages = Message.objects.filter(conversation=conversation).exclude(
        message_users__user=user,
        message_users__deleted_at__isnull=False
    ).order_by('timestamp')

    unread_message_ids = list(messages.filter(is_read=False).exclude(sender=user).values_list('id', flat=True))
    messages.filter(id__in=unread_message_ids).update(is_read=True, read_timestamp=now())

    # ✅ Decrypt content (assumes get_decrypted_content method exists)
    decrypted_messages = [
        {
            'id': msg.id,
            'sender': msg.sender,
            'content': msg.get_decrypted_content(),
            'timestamp': timezone.localtime(msg.timestamp),
            'read_at': msg.read_timestamp.isoformat() if msg.read_timestamp else None,
            'attachment_url': msg.attachment.url if msg.attachment else None,
            'attachment_name': msg.attachment.name if msg.attachment else None,
            'is_image': msg.attachment.name.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')) if msg.attachment else False,
            'is_pdf': msg.attachment.name.lower().endswith('.pdf') if msg.attachment else False,
            'is_video': msg.attachment.name.lower().endswith(('.mp4', '.avi')) if msg.attachment else False,
        }
        for msg in messages
    ]

    context = {
        'conversation': conversation,
        'conversation_name': conversation_name,
        'profile_picture': profile_picture,
        'messages': decrypted_messages,
        'org_id': org_id,
        'selected_conversation_id': conversation.id,
        'conversations': conversation_list,
        'group_members': group_members,
        'is_muted': user in conversation.mute_notifications.all(),
        'is_admin': is_admin,
        'base_template': 'admin/base_admin_dashboard.html' if is_admin else 'base/base_dashboard.html',
        'active_tab': 'messages',
        'other_user': other_user if conversation.type == 'private' else None,
    }

    return render(request, 'conversations/conversations.html', context)


@login_required
def notification_conversation(request, org_id, notification_id):
    user = request.user
    organization = get_object_or_404(Organization, id=org_id)
    
    # Handle tab switching
    active_tab = request.GET.get('tab')
    if active_tab == 'messages':
        return redirect('messages', org_id=org_id) + '?tab=messages'

    notification = get_object_or_404(InboxNotification, id=notification_id, user=user)

    # Mark as read if unread
    if not notification.is_read:
        notification.is_read = True
        notification.save()

    # Set sender_name based on whether it's from an admin or another user
    sender_name = "Organization" if notification.from_admin else (notification.sender.username if notification.sender else "Unknown")

    messages = [{
        'sender': sender_name,
        'content': notification.message,
        'timestamp': notification.timestamp,
        'is_read': notification.is_read,
        'attachment': None
    }]
    base_template = get_base_template(request.user)
    context = {
        'conversations': get_user_conversations(user, organization),
        'messages': messages,
        'selected_conversation_id': notification_id,
        'org_id': org_id,
        'base_template': base_template,  # ← add this
        'active_tab': 'notifications'
    }
    return render(request, 'conversations/conversations.html', context)
def get_user_info(request, username):
    if request.method == "GET":
        try:
            user = User.objects.get(username=username)
            return JsonResponse({
                'status': 'success',
                'user': {
                    'username': user.username,
                    'full_name': f"{user.first_name} {user.last_name}",
                    'email': user.email,
                    'bio': user.profile.bio if hasattr(user, 'profile') else None,
                }
            })
        except User.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'User not found.'}, status=404)

def get_user_conversations(user, organization):
    """Fetch conversations for the user with prefetching and annotations."""
    conversations = Conversation.objects.filter(
        Q(user1=user) | Q(user2=user) | Q(group_members__user=user),
        organization=organization
    ).annotate(
        last_message_time=Max('messages__timestamp'),
        unread_count=Count('messages', filter=Q(messages__is_read=False) & ~Q(messages__sender=user)),
        is_muted=ExpressionWrapper(Q(mute_notifications__in=[user]), output_field=BooleanField())
    ).prefetch_related(
        Prefetch(
            'messages',
            queryset=Message.objects.order_by('-timestamp'),
            to_attr='prefetched_messages'
        )
    ).order_by(
        'is_muted',  # Unmuted conversations first
        '-unread_count',  # Then unread conversations
        '-last_message_time'  # Then by last message time
    )

    conversation_list = []
    for convo in conversations:
        if convo.type == 'private':
            other_user = convo.user2 if convo.user1 == user else convo.user1
            name = other_user.username  # Set the name to the other user's username
        elif convo.type == 'group':
            name = convo.name.strip() if convo.name and convo.name.strip() else "Unnamed Group"  # Use group name or fallback
        else:
            name = "Unknown Conversation"  # Default fallback for unknown types

        # Construct the conversation dictionary
        conversation_list.append({
            'id': convo.id,
            'name': name,
            'type': convo.type,
            'profile_picture': profile_picture,
            'last_message_time': timezone.localtime(last_message_time) if last_message_time else timezone.make_aware(datetime.min),
            'last_message_preview': last_message_preview,
            'is_muted': bool(convo.is_muted),
            'user': conversation_user,
        })
    logger.info(f"Constructed Conversation List: {conversation_list}")
    return conversation_list


@login_required
def conversations_list(request):
    conversations = Conversation.objects.filter(
        group_members__user=request.user
    ).distinct()  # Get all conversations (private and group) the user is part of
    base_template = get_base_template(request.user)
    return render(request, 'conversations/conversations.html', {
        'conversations': conversations,
        'base_template': base_template,  # ← add this
        })

@login_required
def create_group_chat(request, org_id):
    if request.method == 'POST':
        name = request.POST.get('name')
        user_ids = request.POST.getlist('users')  # List of user IDs

        conversation = Conversation.objects.create(name=name, type='group', organization_id=org_id)

        # Add members: current user + selected users
        GroupMember.objects.create(conversation=conversation, user=request.user)
        for user_id in user_ids:
            user = User.objects.get(id=user_id)
            GroupMember.objects.create(conversation=conversation, user=user)

        # ⬇️ Generate group photo after all members are added
        from myapp.utils.image_tools import generate_group_photo
        member_images = [
            gm.user.profile_picture for gm in conversation.group_members.select_related('user').all()
            if gm.user.profile_picture and hasattr(gm.user.profile_picture, 'file')
        ][:4]
        if member_images:
            group_photo = generate_group_photo(member_images)
            conversation.profile_picture.save(group_photo.name, group_photo, save=True)

        return redirect('conversation', conversation_id=conversation.id, org_id=org_id)

    all_users = User.objects.exclude(id=request.user.id)
    base_template = get_base_template(request.user)
    return render(request, 'conversations/conversations.html', {
        'users': all_users,
        'org_id': org_id,
        'base_template': base_template,
    })

@login_required
def update_group_info(request, org_id, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id, type='group')

    if request.method == 'POST':
        group_name = request.POST.get('group_name', '').strip()
        group_photo = request.FILES.get('group_photo', None)

        if group_name:
            conversation.name = group_name
        if group_photo:
            conversation.profile_picture = group_photo

        try:
            conversation.save()
            messages.success(request, "Group information updated successfully.")
        except Exception as e:
            messages.error(request, f"Failed to update group information. Error: {str(e)}")

        return redirect('conversation', org_id=org_id, conversation_id=conversation.id)
    base_template = get_base_template(request.user)
    return render(request, 'conversations/conversations.html', {
        'conversation': conversation,
        'base_template': base_template,  # ← add this
        })

@login_required
def it_update_group_info(request, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id, type='group')

    if not conversation.is_user_part_of_conversation(request.user):
        return HttpResponseForbidden("You are not a member of this group.")

    if request.method == 'POST':
        group_name = request.POST.get('group_name', '').strip()
        group_photo = request.FILES.get('group_photo', None)

        if group_name:
            conversation.name = group_name
        if group_photo:
            conversation.profile_picture = group_photo

        try:
            conversation.save()
            messages.success(request, "Group information updated successfully.")
        except Exception as e:
            messages.error(request, f"Failed to update group information. Error: {str(e)}")

        return redirect('it_conversation', conversation_id=conversation.id)

    return render(request, 'conversation-detail.html', {
        'conversation': conversation,
        'base_template': 'it_admin/it_admin_base_dashboard.html',
    })


@login_required
def ajax_conversation_details(request, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id)
    conversation_key = get_conversation_key(conversation.id)
    messages = Message.objects.filter(conversation=conversation).order_by('-timestamp')[:10]
    decrypted_messages = decrypt_messages_bulk(messages, conversation_key)

    # Decrypt each message
    # Decrypt each message for the AJAX response
    messages_data = [
    {
        'sender': message.sender.username,
        'content': message.get_decrypted_content(),
        'timestamp': message.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    }
    for message in messages
]


    return JsonResponse({'messages': messages_data})

@login_required
def conversations(request, org_id):
    conversations = Conversation.objects.filter(
        Q(user1=User) | Q(user2=User),
            organization=Organization  # Filter by organization ID
        ).annotate(
            last_message_time=Max('messages__timestamp')
        ).order_by('-last_message_time')
    return render(request, 'conversations/conversations.html', {'conversations': conversations})

@login_required
@require_POST
def send_new_message(request, org_id):
    message_type = request.POST.get('message_type', 'group')
    receiver_usernames = request.POST.get('receiver_usernames', '').split(',')
    content = request.POST.get('content', '')
    attachment = request.FILES.get('attachment')

    if not receiver_usernames or not content:
        return JsonResponse({'status': 'Error', 'message': 'Invalid data'}, status=400)

    if message_type == 'individual':
        conversation_ids = []
        for username in receiver_usernames:
            user = User.objects.filter(username=username).first()
            if not user:
                continue

            user1, user2 = sorted([request.user, user], key=lambda u: u.id)
            conversation, _ = Conversation.objects.get_or_create(
                type='private',
                user1=user1,
                user2=user2,
            )

            msg = Message.objects.create(
                sender=request.user,
                content=content,
                conversation=conversation,
                attachment=attachment if attachment else None
            )
            create_message_user_entries(msg, conversation)

            notify_user_ws(
                user=user,
                sender=request.user,
                message=msg,
                org_id=org_id,
                conversation_id=conversation.id,
                mentioned=False,
                request_path=request.path
            )

            conversation_ids.append(conversation.id)

        # Redirect to inbox or somewhere neutral after individual sends
        inbox_url = reverse('inbox', args=[org_id])
        return JsonResponse({
            'status': 'Message sent',
            'redirect_url': inbox_url
        })

    # Otherwise: GROUP logic
    all_usernames = sorted(set(receiver_usernames + [request.user.username]))
    all_users = list(User.objects.filter(username__in=all_usernames))

    if len(all_users) == 2:
        user1, user2 = sorted(all_users, key=lambda u: u.id)
        conversation, _ = Conversation.objects.get_or_create(
            type='private',
            user1=user1,
            user2=user2,
        )
    else:
        existing_conversations = (
            Conversation.objects
            .filter(type='group')
            .annotate(member_count=Count('group_members'))
            .filter(member_count=len(all_users))
        )

        conversation = None
        for convo in existing_conversations:
            convo_usernames = set(convo.group_members.values_list('user__username', flat=True))
            if convo_usernames == set(all_usernames):
                conversation = convo
                break

        if not conversation:
            conversation = Conversation.objects.create(
                type='group',
                name=f'Group Chat {request.user.username} & others'
            )
            for user in all_users:
                GroupMember.objects.create(conversation=conversation, user=user)

            initials = [(u.first_name or u.username or "U")[0].upper() for u in all_users]
            conversation.profile_picture = generate_group_initials_picture(initials)
            conversation.save(update_fields=['profile_picture'])

    msg = Message.objects.create(
        sender=request.user,
        content=content,
        conversation=conversation,
        attachment=attachment if attachment else None
    )
    create_message_user_entries(msg, conversation)

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"chat_{conversation.id}",
        {
            'type': 'chat_message',
            'message': msg.get_decrypted_content(),
            'sender_username': request.user.username,
            'sender_full_name': f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
            'sender_id': request.user.id,
            'sender_profile_picture': (
                request.user.profile_picture.url
                if hasattr(request.user, 'profile_picture') and request.user.profile_picture
                else '/static/img/default-profile.jpg'
            ),
            'timestamp': msg.timestamp.isoformat(),
            'timestamp_display': django_format(msg.timestamp, "M d, Y h:i A"),
            'mentioned_users': [],
            'attachment_url': '',
            'attachment_type': '',
            'thumbnail_url': '',
        }
    )

    recipients = (
        [u for u in all_users if u != request.user]
        if conversation.type == 'private' else
        [member.user for member in conversation.group_members.exclude(user=request.user).select_related('user')]
    )

    for recipient in recipients:
        notify_user_ws(
            user=recipient,
            sender=request.user,
            message=msg,
            org_id=org_id,
            conversation_id=conversation.id,
            mentioned=False,
            request_path=request.path
        )

    is_admin = request.path.startswith(f"/{org_id}/admin/")
    redirect_url = reverse(
        'admin_conversation' if is_admin else 'conversation',
        kwargs={'org_id': org_id, 'conversation_id': conversation.id}
    )

    return JsonResponse({
        'status': 'Message sent',
        'conversation_id': conversation.id,
        'redirect_url': redirect_url
    })
@login_required
@require_POST
def it_send_new_message(request):
    message_type = request.POST.get('message_type', 'group')
    receiver_usernames = request.POST.get('receiver_usernames', '').split(',')
    content = request.POST.get('content', '')
    attachment = request.FILES.get('attachment')

    if not receiver_usernames or not content:
        return JsonResponse({'status': 'Error', 'message': 'Invalid data'}, status=400)

    if message_type == 'individual':
        for username in receiver_usernames:
            user = User.objects.filter(username=username).first()
            if not user:
                continue

            user1, user2 = sorted([request.user, user], key=lambda u: u.id)
            conversation, _ = Conversation.objects.get_or_create(
                type='private',
                user1=user1,
                user2=user2,
            )

            msg = Message.objects.create(
                sender=request.user,
                content=content,
                conversation=conversation,
                attachment=attachment if attachment else None
            )
            create_message_user_entries(msg, conversation)

            notify_user_ws(
                user=user,
                sender=request.user,
                message=msg,
                org_id=None,
                conversation_id=conversation.id,
                mentioned=False,
                request_path=request.path
            )

        return JsonResponse({
            'status': 'Message sent',
            'redirect_url': reverse('it_fetch_messages')
        })

    # Group messaging logic
    all_usernames = sorted(set(receiver_usernames + [request.user.username]))
    all_users = list(User.objects.filter(username__in=all_usernames))

    if len(all_users) == 2:
        user1, user2 = sorted(all_users, key=lambda u: u.id)
        conversation, _ = Conversation.objects.get_or_create(
            type='private',
            user1=user1,
            user2=user2,
        )
    else:
        existing_conversations = (
            Conversation.objects
            .filter(type='group')
            .annotate(member_count=Count('group_members'))
            .filter(member_count=len(all_users))
        )

        conversation = None
        for convo in existing_conversations:
            convo_usernames = set(convo.group_members.values_list('user__username', flat=True))
            if convo_usernames == set(all_usernames):
                conversation = convo
                break

        if not conversation:
            conversation = Conversation.objects.create(
                type='group',
                name=f'IT Group Chat - {request.user.username} & co.'
            )
            for user in all_users:
                GroupMember.objects.create(conversation=conversation, user=user)

            initials = [(u.first_name or u.username or "U")[0].upper() for u in all_users]
            conversation.profile_picture = generate_group_initials_picture(initials)
            conversation.save(update_fields=['profile_picture'])

    msg = Message.objects.create(
        sender=request.user,
        content=content,
        conversation=conversation,
        attachment=attachment if attachment else None
    )
    create_message_user_entries(msg, conversation)

    for recipient in (
        [u for u in all_users if u != request.user]
        if conversation.type == 'private'
        else [gm.user for gm in conversation.group_members.exclude(user=request.user)]
    ):
        notify_user_ws(
            user=recipient,
            sender=request.user,
            message=msg,
            org_id=None,
            conversation_id=conversation.id,
            mentioned=False,
            request_path=request.path
        )

    return JsonResponse({
        'status': 'Message sent',
        'conversation_id': conversation.id,
        'redirect_url': reverse('it_fetch_messages')
    })
@login_required
def it_conversation(request, conversation_id):
    user = request.user
    conversation = get_object_or_404(
        Conversation.objects.prefetch_related('group_members__user', 'mute_notifications'),
        Q(user1=user) | Q(user2=user) | Q(group_members__user=user),
        id=conversation_id
    )

    active_tab = request.GET.get("tab", "messages")  # ← Fix: respect query param

    # Decryption + unread marking
    messages_qs = Message.objects.filter(conversation=conversation).exclude(
        message_users__user=user,
        message_users__deleted_at__isnull=False
    ).order_by('timestamp')

    unread_ids = messages_qs.filter(is_read=False).exclude(sender=user).values_list('id', flat=True)
    messages_qs.filter(id__in=unread_ids).update(is_read=True, read_timestamp=now())

    decrypted_messages = [
        {
            'id': msg.id,
            'sender': msg.sender,
            'content': msg.get_decrypted_content(),
            'timestamp': timezone.localtime(msg.timestamp),
            'read_at': msg.read_timestamp.isoformat() if msg.read_timestamp else None,
            'attachment_url': msg.attachment.url if msg.attachment else None,
            'attachment_name': msg.attachment.name if msg.attachment else None,
            'is_image': msg.attachment.name.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')) if msg.attachment else False,
            'is_pdf': msg.attachment.name.lower().endswith('.pdf') if msg.attachment else False,
            'is_video': msg.attachment.name.lower().endswith(('.mp4', '.avi')) if msg.attachment else False,
        }
        for msg in messages_qs
    ]

    if conversation.type == 'private':
        other_user = conversation.user2 if conversation.user1 == user else conversation.user1
        conversation_name = other_user.get_full_name() or other_user.username
        profile_picture = other_user.profile_picture.url if other_user.profile_picture else static("img/default-profile.jpg")
    else:
        conversation_name = conversation.name or "Unnamed Group"
        profile_picture = conversation.profile_picture.url if conversation.profile_picture else static("img/group-default.png")

    group_members = GroupMember.objects.filter(conversation=conversation).select_related('user') if conversation.type == 'group' else None

    # 🔁 Get notifications if tab is 'notifications'
    notifications = InboxNotification.objects.filter(user=user).order_by('-timestamp') if active_tab == "notifications" else []

    return render(request, 'conversations/conversations.html', {
        'conversation': conversation,
        'conversation_name': conversation_name,
        'profile_picture': profile_picture,
        'messages': decrypted_messages if active_tab == "messages" else [],
        'notifications': notifications if active_tab == "notifications" else [],
        'selected_conversation_id': conversation.id,
        'group_members': group_members,
        'org_id': '',
        'base_template': 'it_admin/it_admin_base_dashboard.html',
        'is_muted': user in conversation.mute_notifications.all(),
        'is_admin': False,
        'active_tab': active_tab,  # ← FIX: pass actual tab
        'other_user': other_user if conversation.type == 'private' else None,
    })


@csrf_exempt
@login_required
@require_POST
def send_message(request, conversation_id, org_id):  # org_id may no longer be needed
    conversation = get_object_or_404(Conversation, pk=conversation_id)

    # Log the POST data
    logger.debug(f"POST data: {request.POST}")
    logger.debug(f"FILES data: {request.FILES}")

    if not request.POST.get('content') and not request.FILES.get('attachment'):
        return JsonResponse({'status': 'Error', 'message': 'Message content or attachment is required.'}, status=400)

    form = MessageForm(request.POST, request.FILES)

    if form.is_valid():
        message = form.save(commit=False)
        message.sender = request.user
        message.conversation = conversation
        message.is_read = False

        # Encrypt content
        if message.content:
            try:
                key = conversation.get_key()
                iv, encrypted_content = encrypt_message(message.content, key)
                message.content = base64.b64encode(encrypted_content).decode('utf-8')
                message.iv = base64.b64encode(iv).decode('utf-8')
            except Exception as e:
                logger.error(f"Encryption error: {e}")
                return JsonResponse({'status': 'Error', 'message': f'Encryption failed: {str(e)}'}, status=400)

        ConversationUser.objects.filter(
            conversation=conversation,
            last_deleted_at__isnull=False
        ).update(last_deleted_at=None)

        message.save()
        create_message_user_entries(message, conversation)
        # Handle attachments
        attachment_url = None
        attachment_type = None
        if message.attachment:
            if message.attachment.size == 0:
                return JsonResponse({'status': 'Error', 'message': 'Empty file attachment is not allowed.'}, status=400)

            mime_type, _ = mimetypes.guess_type(message.attachment.name)
            allowed_mime_types = [
                'image/jpeg', 'image/png', 'image/gif',
                'video/mp4', 'application/pdf', 'application/msword',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            ]
            if mime_type in allowed_mime_types:
                attachment_url = message.attachment.url
                attachment_type = mime_type
            else:
                return JsonResponse({'status': 'Error', 'message': 'Invalid file type.'}, status=400)

        message_data = {
            'type': 'chat_message',
            'message_content': message.get_decrypted_content() or '[No Text]',
            'sender': message.sender.username,
            'sender_profile_picture': (
                message.sender.profile_picture.url
                if message.sender.profile_picture else '/static/img/default-profile.jpg'
            ),
            'timestamp': timezone.localtime(message.timestamp),
            'attachment_url': attachment_url,
            'attachment_type': attachment_type,
        }

        # Send via WebSocket
        try:
            async_to_sync(channel_layer.group_send)(
                f'chat_{conversation_id}',
                {
                    'type': 'chat_message',
                    **message_data,
                }
            )
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            return JsonResponse({'status': 'Error', 'message': f'WebSocket error: {str(e)}'}, status=500)

        return JsonResponse({'status': 'Message sent', **message_data}, status=200)

    logger.error(f"Form errors: {form.errors}")
    return JsonResponse({'status': 'Error', 'message': 'Invalid message data.'}, status=400)

@csrf_exempt
@login_required
@require_POST
def it_send_message(request, conversation_id):
    return send_message(request, conversation_id=conversation_id, org_id=None)

@login_required
def unsend_message(request, org_id, message_id):
    user = request.user

    # Fetch the message
    message = get_object_or_404(Message, id=message_id)
    


    # Check if the requesting user is the sender
    if message.sender != user:
        return JsonResponse({'status': 'error', 'error': 'You can only unsend your own messages.'}, status=403)

    # Delete the message completely (unsend)
    message.delete()

    return JsonResponse({'status': 'success', 'message': 'Message unsent successfully.'})

@login_required
def delete_message(request, org_id, message_id):
    user = request.user

    # Fetch the message
    message = get_object_or_404(Message, id=message_id)


    # Ensure the user is part of the conversation
    if not message.conversation.is_user_part_of_conversation(user):
        return JsonResponse({'status': 'error', 'error': 'You do not have permission to delete this message.'}, status=403)

    # Mark the message as deleted for the current user
    MessageUser.objects.update_or_create(
        user=user,
        message=message,
        defaults={'deleted_at': timezone.now()}
    )

    return JsonResponse({'status': 'success', 'message': 'Message deleted successfully.'})


@login_required
def edit_message(request, org_id, message_id):
    user = request.user

    # Fetch the message
    message = get_object_or_404(Message, id=message_id, conversation__organization_id=org_id)

    # Ensure the user is the sender
    if not message.is_editable_by_user(user):
        return JsonResponse({'status': 'error', 'error': 'You do not have permission to edit this message.'}, status=403)

    # Get the new content from the request
    new_content = request.POST.get('content', '').strip()
    if not new_content:
        return JsonResponse({'status': 'error', 'error': 'Content cannot be empty.'}, status=400)

    # Update the message
    message.content = new_content
    message.edited_at = timezone.now()
    message.save(update_fields=['content', 'edited_at'])

    return JsonResponse({'status': 'success', 'message': 'Message edited successfully.'})

@csrf_exempt
@login_required
def delete_conversation(request, org_id, conversation_id):
    user = request.user
    organization = get_object_or_404(Organization, id=org_id)

    try:
        conversation = get_object_or_404(Conversation, id=conversation_id)

        if not conversation.is_user_part_of_conversation(user):
            return JsonResponse({'error': 'You are not part of this conversation.'}, status=403)

        # Update ConversationUser record
        convo_user, _ = ConversationUser.objects.update_or_create(
            user=user,
            conversation=conversation,
            defaults={'last_deleted_at': timezone.now()}
        )

        # ALSO update MessageUser.deleted_at for ALL messages in that conversation for this user
        MessageUser.objects.filter(
            message__conversation=conversation,
            user=user
        ).update(deleted_at=timezone.now())

        return JsonResponse({
            'status': 'success',
            'message': 'Conversation deleted successfully.',
            'redirect_url': reverse('fetch_messages', kwargs={'org_id': org_id})  # or admin_fetch_messages
        })
    except Exception as e:
        logger.error(f"Error deleting conversation: {e}")
        return JsonResponse({'error': 'Failed to delete conversation.'}, status=500)

@login_required
def new_message(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)

    friends = Friend.objects.filter(
        (Q(user1=request.user) | Q(user2=request.user)) & Q(status='accepted')
    ).values_list('user1__username', 'user2__username')

    friends = set(
        friend for pair in friends for friend in pair if friend != request.user.username
    )

    # Base Template Logic
    if '/admin/' in request.path:
        base_template = 'admin/base_admin_dashboard.html'
    else:
        base_template = 'base/base_dashboard.html'

    return render(request, 'conversations/new-message.html', {
        'friends': friends,
        'org_id': org_id,
        'base_template': base_template,
    })
@login_required
def it_new_message(request):
    # IT Admins have no org_id
    friends = Friend.objects.filter(
        (Q(user1=request.user) | Q(user2=request.user)) & Q(status='accepted')
    ).values_list('user1__username', 'user2__username')

    friends = set(
        friend for pair in friends for friend in pair if friend != request.user.username
    )

    return render(request, 'conversations/new-message.html', {
        'friends': friends,
        'org_id': '',  # Can be used in template if needed
        'base_template': 'it_admin/it_admin_base_dashboard.html',
    })

@login_required
def leave_group(request, org_id, conversation_id):
    user = request.user
    organization = get_object_or_404(Organization, id=org_id)
    conversation = get_object_or_404(Conversation, id=conversation_id)

    # Ensure this is a group conversation
    if conversation.type != 'group':
        messages.error(request, "You can only leave group conversations.")
        return redirect('fetch_messages', org_id=org_id)

    # Check if the user is a member of the group
    group_member = GroupMember.objects.filter(conversation=conversation, user=user).first()
    if not group_member:
        messages.error(request, "You are not a member of this group.")
        return redirect('fetch_messages', org_id=org_id)

    # Remove the user from the group
    group_member.delete()

    # Check if the group has no members left and delete the conversation if necessary
    if not conversation.group_members.exists():
        conversation.delete()

    messages.success(request, "You have left the group.")
    return redirect('fetch_messages', org_id=org_id)


User = get_user_model()  # Get the custom user model

@login_required
def add_members(request, org_id, conversation_id):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            member_usernames = data.get('members', [])
            if not member_usernames:
                return JsonResponse({'status': 'error', 'message': 'No members provided.'}, status=400)

            conversation = get_object_or_404(Conversation, id=conversation_id, type='group')

            is_group_member = GroupMember.objects.filter(conversation=conversation, user=request.user).exists()
            if not is_group_member:
                return JsonResponse({'status': 'error', 'message': 'You are not authorized to add members.'}, status=403)

            # Filter out already-added users
            new_members = User.objects.filter(username__in=member_usernames).exclude(
                id__in=GroupMember.objects.filter(conversation=conversation).values_list('user_id', flat=True)
            )
            if not new_members.exists():
                return JsonResponse({'status': 'error', 'message': 'No valid users to add.'}, status=400)

            # Add new members
            GroupMember.objects.bulk_create(
                [GroupMember(conversation=conversation, user=user) for user in new_members]
            )

            # Create a system message for each user added
            timestamp = localtime(now()).strftime('%b %d, %Y %I:%M %p')
            for user in new_members:
                Message.objects.create(
                    conversation=conversation,
                    sender=request.user,
                    content=f"{user.username} was added to the group at {timestamp} by {request.user.username}",
                    is_system_message=True
                )

            return JsonResponse({'status': 'success', 'message': 'Members added successfully!'})

        except Conversation.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Conversation not found.'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=400)
@csrf_exempt
@login_required
def toggle_mute_notifications(request, org_id, conversation_id):
    if request.method != "POST":
        return JsonResponse({'error': 'Invalid request method'}, status=400)

    user = request.user
    organization = get_object_or_404(Organization, id=org_id)
    conversation = get_object_or_404(Conversation, id=conversation_id)

    # Group conversation permissions
    if conversation.type == 'group':
        logger.debug(f"User {user.username} attempting to toggle mute for group conversation {conversation.id}")
        # Ensure the user is a member of the group
        if not conversation.is_user_in_group(user):
            logger.warning(f"Permission denied for user {user.username} in group conversation {conversation.id}")
            return JsonResponse({'error': 'Permission denied'}, status=403)
    # Private conversation permissions
    elif conversation.type == 'private':
        logger.debug(f"User {user.username} attempting to toggle mute for private conversation {conversation.id}")
        if user != conversation.user1 and user != conversation.user2:
            logger.warning(f"Permission denied for user {user.username} in private conversation {conversation.id}")
            return JsonResponse({'error': 'Permission denied'}, status=403)

    # Toggle mute notifications
    logger.debug(f"Toggling mute notifications for user {user.username} in conversation {conversation.id}")
    if user in conversation.mute_notifications.all():
        conversation.mute_notifications.remove(user)
        status = 'unmuted'
        logger.info(f"User {user.username} unmuted conversation {conversation.id}")
    else:
        conversation.mute_notifications.add(user)
        status = 'muted'
        logger.info(f"User {user.username} muted conversation {conversation.id}")

    return JsonResponse({'status': status})

@login_required
@require_POST
def toggle_mute_conversation(request, org_id, conversation_id):
    try:
        conversation = Conversation.objects.get(id=conversation_id, organization_id=org_id)
        user = request.user

        if conversation.mute_notifications.filter(id=user.id).exists():
            # User has muted the conversation, so unmute
            conversation.mute_notifications.remove(user)
            status = "unmuted"
        else:
            # User has not muted the conversation, so mute
            conversation.mute_notifications.add(user)
            status = "muted"

        return JsonResponse({"status": status})

    except Conversation.DoesNotExist:
        return JsonResponse({"error": "Conversation not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@login_required
def get_muted_conversations(request):
    user = request.user
    muted_conversations = user.muted_conversations.values_list('id', flat=True)
    return JsonResponse({'muted_conversations': list(muted_conversations)})

@login_required
def remove_member(request, org_id, conversation_id, user_id):
    conversation = get_object_or_404(Conversation, id=conversation_id)
    user = get_object_or_404(User, id=user_id)
    if user in conversation.members.all():
        conversation.members.remove(user)
        messages.success(request, f"{user.username} has been removed from the group.")
    return redirect('conversation', org_id=org_id, conversation_id=conversation_id)

@require_POST
@login_required
def send_event_invitation(request, org_id, event_id):
    data = json.loads(request.body)
    invited_user_id = data.get("user_id")
    invited_user = get_object_or_404(User, id=invited_user_id, organization_id=org_id)
    event = get_object_or_404(CalendarEvent, id=event_id, organization_id=org_id)

    # Check if a conversation already exists between sender and invitee
    conversation, created = Conversation.objects.get_or_create(
        organization_id=org_id,
        type='private',
        user1=request.user,
        user2=invited_user
    )

    # Create the invitation
    invitation, created_invitation = EventInvitation.objects.get_or_create(
        event=event,
        invited_user=invited_user
    )

    # Send a notification if the invitation is newly created
    if created_invitation:
        InboxNotification.objects.create(
            user=invited_user,
            message=f"You've been invited to the event '{event.title}'",
            event_invitation=invitation
        )

    return JsonResponse({'status': 'success', 'invitation_id': invitation.id})
@login_required
def respond_to_event_invitation(request, org_id, invitation_id):
    data = json.loads(request.body)
    response = data.get("response")

    invitation = get_object_or_404(EventInvitation, id=invitation_id, invited_user=request.user)

    if response not in ["accepted", "declined"]:
        return JsonResponse({'status': 'error', 'message': 'Invalid response'}, status=400)

    invitation.status = response
    invitation.save()

    if response == "accepted":
        # Add user to the event or take other actions
        CalendarEvent.objects.create(
            title=invitation.event.title,
            description=invitation.event.description,
            start_date=invitation.event.start_date,
            end_date=invitation.event.end_date,
            color=invitation.event.color,
            all_day=invitation.event.all_day,
            user=invitation.invited_user,
            organization=invitation.event.organization,
            is_shared=True
        )

    return JsonResponse({'status': 'success', 'message': f'Invitation {response}'})

@login_required
@require_POST
def send_invitation(request):
    data = json.loads(request.body)
    experiment_id = data['experiment_id']
    username = data['username']
    role = data['role']

    user = get_object_or_404(User, username=username)
    experiment = get_object_or_404(Experiment, id=experiment_id)

    conversation, created = Conversation.objects.get_or_create(
        type='private',
        user1=request.user,
        user2=user,
        defaults={'name': user.username}
    )

    invitation = Invitation.objects.create(
        sender=request.user,
        receiver=user,
        experiment=experiment,
        role=role,
        status='pending'
    )

    message_content = f"You have been invited to join the experiment '{experiment.name}' as a {role}. Do you accept?"
    Message.objects.create(
        sender=request.user,
        content=message_content,
        conversation=conversation,
        invitation_id=invitation.id  # Ensure you have a field to link invitations to messages if needed
    )

    return JsonResponse({'status': 'Invitation sent successfully', 'conversation_id': conversation.id})


@login_required
@require_POST
def remove_collaborator(request):
    data = request.json()
    experiment_id = data['experiment_id']
    user_id = data['user_id']

    Collaborator.objects.filter(experiment_id=experiment_id, user_id=user_id).delete()
    return JsonResponse({'status': 'Collaborator removed'})

@login_required
@require_POST
def update_collaborator_role(request):
    data = request.json()
    experiment_id = data['experiment_id']
    user_id = data['user_id']
    role = data['role']

    Collaborator.objects.filter(experiment_id=experiment_id, user_id=user_id).update(role=role)
    return JsonResponse({'status': 'Collaborator role updated'})

@login_required
def send_experiment_message_page(request, org_id, experiment_id):
    # Ensure the experiment and members belong to the same organization
    experiment = get_object_or_404(Experiment, id=experiment_id, organization__id=org_id)
    
    # Start with the experiment owner as a member
    members = set([experiment.owner])
    
    # Include all collaborators (which should now include investigators as well)
    collaborators = Collaborator.objects.filter(experiment=experiment, user__organization=request.user.organization)
    
    for collaborator in collaborators:
        members.add(collaborator.user)
    
    # Exclude the current user (the sender) from the members
    members = [member for member in members if member != request.user]
    
    return render(request, 'conversations/send_experiment_message_page.html', {
        'experiment': experiment,
        'experiment_members': members,  # Pass all members except the sender to the template
        'org_id': org_id
    })

@login_required
def send_experiment_message(request, org_id, experiment_id):
    # Ensure the experiment belongs to the same organization
    experiment = get_object_or_404(Experiment, id=experiment_id, organization__id=org_id)

    if request.method == 'POST':
        message_content = request.POST.get('message')
        recipient_ids = request.POST.getlist('recipients')

        if not message_content:
            messages.error(request, "Message cannot be empty.")
            return redirect('send_experiment_message_page', org_id=org_id, experiment_id=experiment.id)

        if not recipient_ids:
            messages.error(request, "Please select at least one recipient.")
            return redirect('send_experiment_message_page', org_id=org_id, experiment_id=experiment.id)

        # Fetch selected recipients within the same organization
        recipients = User.objects.filter(id__in=recipient_ids, organization_id=org_id)

        # Send message to each selected user
        for recipient in recipients:
            # Check if a conversation already exists between the sender and the recipient
            conversation = Conversation.objects.filter(
                (Q(user1=request.user, user2=recipient) | Q(user1=recipient, user2=request.user)),
                type='private'
            ).first()

            # If no conversation exists, create a new one
            if not conversation:
                conversation = Conversation.objects.create(
                    user1=request.user,
                    user2=recipient,
                    type='private',
                    organization_id=org_id  # Link the conversation to the organization
                )

            # Create the message
            Message.objects.create(
                sender=request.user,
                content=message_content,
                conversation=conversation
            )

        messages.success(request, "Message sent to selected users.")
        return redirect('experiment_home', org_id=org_id, experiment_id=experiment.id)

    return redirect('experiment_home', org_id=org_id, experiment_id=experiment.id)

@login_required
def send_friend_message(request, org_id, friend_id):
    # Ensure the friend exists within the same organization
    friend = get_object_or_404(User, id=friend_id, organization__id=org_id)

    if request.method == 'POST':
        message_content = request.POST.get('message')

        if not message_content:
            messages.error(request, "Message cannot be empty.")
            return redirect('friend_info', org_id=org_id, friend_id=friend.id)

        # Check if a conversation already exists between the sender and the recipient
        conversation = Conversation.objects.filter(
            (Q(user1=request.user, user2=friend) | Q(user1=friend, user2=request.user)),
            type='private'
        ).first()

        # If no conversation exists, create a new one
        if not conversation:
            conversation = Conversation.objects.create(
                user1=request.user,
                user2=friend,
                type='private',
                organization_id=org_id  # Link the conversation to the organization
            )

        # Create the message
        Message.objects.create(
            sender=request.user,
            content=message_content,
            conversation=conversation
        )

        messages.success(request, f"Message sent to {friend.username}.")
        return redirect('friend_info', org_id=org_id, friend_id=friend.id)

    return redirect('friend_info', org_id=org_id, friend_id=friend.id)

@login_required
def start_conversation(request, org_id, friend_id):
    # Ensure the friend exists within the same organization
    friend = get_object_or_404(User, id=friend_id, organization__id=org_id)

    # Check if a conversation already exists between the sender and the recipient
    conversation = Conversation.objects.filter(
        (Q(user1=request.user, user2=friend) | Q(user1=friend, user2=request.user)),
        type='private'
    ).first()

    # If no conversation exists, create a new one
    if not conversation:
        conversation = Conversation.objects.create(
            user1=request.user,
            user2=friend,
            type='private',
            organization_id=org_id  # Link the conversation to the organization
        )

    # Redirect the user to the conversation page
    return redirect('conversation', org_id=org_id, conversation_id=conversation.id)

@login_required
def inbox_view(request, org_id):
    organization = get_object_or_404(Organization, id=org_id)
    user = request.user
    notification_id = request.GET.get('notification_id')
    # Fetch experiment-related and admin notifications
    experiment_notifications = InboxNotification.objects.filter(user=user).order_by('-timestamp')

    # Fetch the selected notification if it exists
    selected_notification = None
    if notification_id:
        selected_notification = InboxNotification.objects.filter(user=user, id=notification_id).first()
        if selected_notification and not selected_notification.is_read:
            selected_notification.is_read = True
            selected_notification.save()

    # Update sender name to "Organization" for admin notifications
    for notification in experiment_notifications:
        if notification.from_admin:
            notification.sender_name = "Organization"
        else:
            notification.sender_name = notification.user.username

    # Pass org_id to the template
    return render(request, 'conversations/inbox.html', {
        'experiment_notifications': experiment_notifications,
        'selected_notification': selected_notification,
        'selected_notification_id': notification_id,
        'org_id': org_id  # Ensure org_id is passed here
    })
@login_required
def notification_view(request, org_id, notification_id):
    user = request.user

    if user.is_it_admin_user:
        notification = get_object_or_404(InboxNotification, id=notification_id, user=user)
    else:
        notification = get_object_or_404(InboxNotification, id=notification_id, user=user, organization_id=org_id)

    # Mark as read
    if not notification.is_read:
        notification.is_read = True
        notification.save()

    is_admin = request.path.startswith("/admin/") or request.path.startswith("/it/")

    context = {
        'notification': notification,
        'is_admin': is_admin,
        'base_template': (
            'it_admin/it_admin_base_dashboard.html' if user.is_it_admin_user
            else 'admin/base_admin_dashboard.html' if is_admin
            else 'base/base_dashboard.html'
        ),
    }

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html_content = render_to_string('partials/notification_detail.html', context)
        return JsonResponse({'html': html_content})

    return render(request, 'conversations/notification_detail.html', context)

@login_required
def get_unread_count(request):
    user = request.user

    # Fetch the count of conversations with unread messages
    unread_conversations = Conversation.objects.filter(
        Q(messages__is_read=False),
        Q(user1=user) | Q(user2=user) | Q(group_members__user=user)
    ).exclude(messages__sender=user).distinct().count()

    # Fetch the count of unread notifications (if applicable)
    unread_notifications = InboxNotification.objects.filter(user=user, is_read=False).count()

    total_unread = unread_conversations + unread_notifications

    return JsonResponse({'unread_conversations': unread_conversations, 'unread_notifications': unread_notifications, 'total_unread': total_unread})

@login_required
def get_unread_messages_count(request, org_id=None):
    user = request.user

    unread_message_count = Message.objects.filter(
        conversation__in=Conversation.objects.filter(
            Q(user1=user) | Q(user2=user) | Q(group_members__user=user)
        ),
        is_read=False
    ).exclude(sender=user).count()

    unread_notification_count = InboxNotification.objects.filter(user=user, is_read=False).count()
    total_unread_count = unread_message_count + unread_notification_count

    return JsonResponse({'unread_count': total_unread_count})

def get_decrypted_message_preview(message):
    cache_key = f"message_preview_{message.id}"
    preview = cache.get(cache_key)
    if not preview:
        preview = message.get_decrypted_content()
        cache.set(cache_key, preview, timeout=300)  # Cache for 5 minutes
    return preview

@login_required
@require_POST
def mark_notification_as_read(request, org_id, notification_id):
    notification = get_object_or_404(InboxNotification, id=notification_id, user=request.user)
    notification.is_read = True
    notification.save()
    return redirect('inbox', org_id=org_id)  # Redirect back to the inbox page

def get_messages(request, conversation_id):
    page_number = request.GET.get("page", 1)
    conversation = get_object_or_404(Conversation, id=conversation_id)
    messages_qs = conversation.messages.order_by('-timestamp')  # Newest first
    paginator = Paginator(messages_qs, 25)  # 25 messages per page

    page_obj = paginator.get_page(page_number)
    messages = list(page_obj.object_list)

    return JsonResponse({
        "messages": render_to_string("partials/messages.html", {"messages": messages[::-1]}),  # oldest to newest
        "has_previous": page_obj.has_next(),  # because we're ordering DESC
        "next_page": int(page_number) + 1,
    })

@login_required
def get_paginated_messages(request, org_id, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id)
    messages_query = Message.objects.filter(conversation=conversation).order_by('-timestamp')
    messages_query = Message.objects.filter(conversation=conversation).select_related('sender').prefetch_related('attachment').order_by('-timestamp')
    
    paginator = Paginator(messages_query, 10)  # 10 messages per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    message_list = [
        {
            'content': msg.get_decrypted_content(),
            'timestamp': timezone.localtime(msg.timestamp),
            'is_sender': msg.sender == request.user,
            'attachment': msg.attachment.url if msg.attachment else None
        }
        for msg in page_obj
    ]

    return JsonResponse({
        'messages': message_list,
        'has_more': page_obj.has_next()
    })