# dashboard/services/chat_service.py
from __future__ import annotations
import base64
import json
import mimetypes
import os
import uuid
from typing import Optional, Dict, Any

from asgiref.sync import sync_to_async
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.dateformat import format as django_format

from dashboard.models import Conversation, Message


# =========================
# Internal helpers (sync)
# =========================

def _guess_mime_for(msg: Message) -> str:
    """Prefer stored mime; fall back to a path-based guess."""
    if getattr(msg, "attachment_mime_type", None):
        return msg.attachment_mime_type or ""
    if getattr(msg, "attachment", None) and msg.attachment:
        mt, _ = mimetypes.guess_type(getattr(msg.attachment, "path", "") or "")
        return mt or ""
    return ""


def _safe_decrypt(msg: Message) -> str:
    """
    Decrypts message content if your model provides `get_decrypted_content()`.
    Falls back to raw `content` if not available.
    """
    if hasattr(msg, "get_decrypted_content"):
        try:
            return msg.get_decrypted_content() or ""
        except Exception:
            # If decryption fails for some legacy/system rows, avoid crashing fan-out.
            return ""
    return getattr(msg, "content", "") or ""


def _build_dto_sync(msg: Message) -> Dict[str, Any]:
    """
    Build the DTO your WS clients expect. Keep field names stable.
    """
    plaintext = _safe_decrypt(msg)
    ts = msg.edited_at or msg.timestamp
    is_edited = bool(msg.edited_at)

    # Attachment mapping
    attachment_url = msg.attachment.url if getattr(msg, "attachment", None) else ""
    attachment_type = _guess_mime_for(msg)
    thumbnail_url = (
        getattr(msg, "thumbnail_url", "") or
        (msg.thumbnail.url if getattr(msg, "thumbnail", None) else "") or
        ""
    )

    # Sender mapping
    sender = getattr(msg, "sender", None)
    sender_username = getattr(sender, "username", "system")
    full_name = (
        " ".join([
            getattr(sender, "first_name", "") or "",
            getattr(sender, "last_name", "") or "",
        ]).strip()
        or sender_username
    )
    if getattr(sender, "profile_picture", None):
        profile_url = sender.profile_picture.url
    else:
        # Match your frontend’s default image path
        profile_url = "/static/img/default-profile.jpg"

    return {
        "id": msg.id,
        "message": plaintext,
        "message_content": plaintext,
        "sender_username": sender_username,
        "sender_full_name": full_name,
        "sender_profile_picture": profile_url,
        "timestamp": ts.isoformat(),
        "timestamp_display": django_format(ts, "M d, Y h:i A"),
        "is_edited": is_edited,
        "attachment_url": attachment_url,
        "attachment_type": attachment_type,
        "thumbnail_url": thumbnail_url,
    }


# =========================
# DB operations (sync)
# =========================

def _create_message(
    conversation_id: int,
    user,
    text: str,
    client_id: Optional[str] = None,
    inline_attachment: Optional[dict] = None,
) -> Message:
    """
    Create a message row. Your Message.save() can handle encryption.
    """
    conv = Conversation.objects.select_related("user1", "user2").get(id=conversation_id)
    # Store something even when an attachment is present and text is empty.
    content = text or ""
    msg = Message.objects.create(
        conversation=conv,
        sender=user,
        content=content,
    )
    if inline_attachment:
        _apply_inline_attachment(msg, inline_attachment)
    # you can persist client_id for idempotency if your schema supports it
    return msg


def _edit_message(conversation_id: int, user, message_id: int, new_text: str) -> Message:
    """
    Edit a message the user owns inside the conversation.
    """
    msg = Message.objects.select_related("sender", "conversation").get(
        id=message_id,
        conversation_id=conversation_id,
        sender=user,
    )
    msg_content = new_text or ""
    msg.content = msg_content              # re-encrypt on save() if applicable
    msg.edited_at = timezone.now()
    msg.save(update_fields=["content", "edited_at", "iv"])
    return msg


# =========================
# Async wrappers
# =========================

@sync_to_async
def build_dto(msg: Message) -> Dict[str, Any]:
    return _build_dto_sync(msg)


@sync_to_async
def build_group_chat_event(msg: Message) -> Dict[str, Any]:
    """
    Frame for group fan-out, already shaped for the client.
    """
    dto = _build_dto_sync(msg)
    return {"type": "chat_message", **dto}


@sync_to_async
def build_edit_event(msg: Message) -> Dict[str, Any]:
    """
    Frame for an edit fan-out, matching your client contract.
    """
    return {
        "type": "edit_message",
        "message_id": msg.id,
        "content": _safe_decrypt(msg),
        "is_edited": True,
        "timestamp": (msg.edited_at or msg.timestamp).isoformat(),
    }


@sync_to_async
def _create_message_async(conversation_id: int, user, text: str, client_id: Optional[str]) -> Message:
    return _create_message(conversation_id, user, text, client_id)


@sync_to_async
def _edit_message_async(conversation_id: int, user, message_id: int, new_text: str) -> Message:
    return _edit_message(conversation_id, user, message_id, new_text)


# =========================
# Public async API (used by consumers)
# =========================

async def enqueue_send_message(
    user,
    conversation_id: int,
    text: str,
    attachment=None,
    client_id: Optional[str] = None,
) -> Message:
    """
    Create a message and return the Message object for subsequent fan-out.
    Attachment handling can be added here if you store files post-create.
    """
    msg = await _create_message_async(conversation_id, user, text, client_id)

    if attachment:
        msg = await _attach_inline_file_async(msg.id, attachment)

    # TODO (optional): if `attachment` arrives as metadata/blob token,
    # associate file here and update mime/thumbnail fields, then save.

    return msg


async def enqueue_edit_message(
    user,
    conversation_id: int,
    message_id: int,
    new_text: str,
) -> Message:
    """
    Edit a message and return the updated Message object for fan-out.
    """
    return await _edit_message_async(conversation_id, user, message_id, new_text)


@sync_to_async
def _attach_inline_file_async(message_id: int, attachment_data: dict) -> Message:
    msg = Message.objects.select_related("conversation").get(id=message_id)
    _apply_inline_attachment(msg, attachment_data)
    return msg


def _apply_inline_attachment(msg: Message, attachment: dict):
    """
    Persist a small inline attachment that arrived via WebSocket (base64 payload).
    """
    if not attachment:
        return

    raw_content = attachment.get("content") or ""
    if not raw_content:
        return

    try:
        file_bytes = base64.b64decode(raw_content)
    except Exception:
        # Invalid base64—skip silently to avoid crashing the consumer.
        return

    original_name = attachment.get("name") or f"upload_{uuid.uuid4().hex}"
    mime_type = attachment.get("type") or mimetypes.guess_type(original_name)[0] or "application/octet-stream"

    content_file = ContentFile(file_bytes, name=original_name)
    msg.attachment.save(original_name, content_file, save=False)
    msg.attachment_mime_type = mime_type
    msg.save(update_fields=["attachment", "attachment_mime_type"])


# =========================
# Stream publish (beta fan-out)
# =========================

# Minimal Redis Streams publisher to support CHAT_FANOUT_MODE="stream"
# This is intentionally simple; your dispatcher service will do the XREAD/GROUP and
# call Channels group_send to complete the fan-out.

try:
    import redis  # redis-py
except Exception:  # pragma: no cover
    redis = None  # allow app to run without redis in dev

STREAM_NAME = os.getenv("CHAT_STREAM", "stream:messages")
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")


def _xadd(kind: str, conversation_id: int, message_id: int, payload: Dict[str, Any]):
    """
    Synchronous XADD used under a sync_to_async wrapper.
    Keep payload lean; dispatcher can rehydrate if needed.
    """
    if redis is None:
        # Redis not installed/available; no-op so local dev still works.
        return None

    r = redis.from_url(REDIS_URL)
    fields = {
        "kind": kind,  # "chat_message" | "edit_message" | ...
        "conversation_id": str(conversation_id),
        "message_id": str(message_id),
        # compact JSON for lower overhead
        "payload": json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
    }
    return r.xadd(STREAM_NAME, fields)


@sync_to_async
def publish_chat_event_to_stream(
    kind: str,
    conversation_id: int,
    message_id: int,
    payload: Dict[str, Any],
):
    """
    Async-friendly wrapper that publishes a chat event to Redis Streams.
    Your dispatcher will read from STREAM_NAME and do group fan-out.
    """
    return _xadd(kind, conversation_id, message_id, payload)
