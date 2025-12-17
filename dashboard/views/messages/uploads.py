# dashboard/views/messages/uploads.py
import math, uuid, mimetypes, shutil
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

# ✅ correct model module + class names
from dashboard.model_uploads import UploadSession, Attachments
from dashboard.models import Conversation, Message

# thumbnail task (optional)
try:
    from dashboard.tasks import generate_attachment_thumbnail
except Exception:
    generate_attachment_thumbnail = None

TMP_DIR = Path(settings.MEDIA_ROOT) / "chunks"
TMP_DIR.mkdir(parents=True, exist_ok=True)

def _group_name(conversation_id: int) -> str:
    return f"chat_{conversation_id}"

@login_required
@require_POST
def init_upload(request, org_id, conversation_id):
    conv = get_object_or_404(Conversation, pk=conversation_id)

    filename = request.POST.get("filename")
    try:
        total_size = int(request.POST.get("total_size", "0"))
    except (TypeError, ValueError):
        total_size = 0
    mime_type = (
        request.POST.get("mime_type")
        or (mimetypes.guess_type(filename)[0] if filename else None)
        or "application/octet-stream"
    )

    if not filename or total_size <= 0:
        return HttpResponseBadRequest("filename and total_size are required")

    part_size = getattr(settings, "FILE_CHUNK_SIZE", 2 * 1024 * 1024)  # 2MB default
    total_parts = max(1, math.ceil(total_size / part_size))

    us = UploadSession.objects.create(
        conversation=conv,
        filename=filename,
        mime_type=mime_type,
        total_size=total_size,
        part_size=part_size,
        total_parts=total_parts,
        created_by=request.user,
    )

    (TMP_DIR / str(us.id)).mkdir(parents=True, exist_ok=True)

    # heads-up to clients
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        _group_name(conv.id),
        {
            "type": "chat_message",
            "event": "attachment_pending",
            "filename": filename,
            "mime_type": mime_type,
            "uploaded_by": request.user.username,
            "timestamp": timezone.localtime().isoformat(),
        },
    )

    return JsonResponse(
        {"upload_id": str(us.id), "part_size": part_size, "total_parts": total_parts},
        status=200,
    )

@login_required
@require_POST
def upload_part(request, org_id, conversation_id):
    upload_id = request.POST.get("upload_id")
    try:
        part_no = int(request.POST.get("part_no", "0"))
    except (TypeError, ValueError):
        part_no = -1

    blob = request.FILES.get("blob")
    if not upload_id or blob is None or part_no < 0:
        return HttpResponseBadRequest("upload_id, part_no and blob are required")

    us = get_object_or_404(UploadSession, pk=upload_id, conversation_id=conversation_id)

    part_path = TMP_DIR / str(us.id) / f"part_{part_no:06d}"
    part_path.parent.mkdir(parents=True, exist_ok=True)
    with part_path.open("wb") as f:
        for chunk in blob.chunks():
            f.write(chunk)

    # idempotent bump
    us.received_parts = min(us.total_parts, us.received_parts + 1)
    us.save(update_fields=["received_parts"])

    return JsonResponse({"ok": True, "received": part_no}, status=200)

@login_required
@require_POST
def complete_upload(request, org_id, conversation_id):
    upload_id = request.POST.get("upload_id")
    message_text = (request.POST.get("message_text") or "").strip()
    if not upload_id:
        return HttpResponseBadRequest("upload_id is required")

    us = get_object_or_404(UploadSession, pk=upload_id, conversation_id=conversation_id)

    parts_dir = TMP_DIR / str(us.id)
    part_files = sorted(parts_dir.glob("part_*"))
    if len(part_files) != us.total_parts:
        return HttpResponseBadRequest("Not all parts uploaded")

    # assemble into final file
    final_name = f"{uuid.uuid4().hex}_{us.filename}"
    final_rel = f"attachments/{final_name}"
    final_abs = Path(settings.MEDIA_ROOT) / final_rel
    final_abs.parent.mkdir(parents=True, exist_ok=True)

    with final_abs.open("wb") as out:
        for p in part_files:
            with p.open("rb") as inp:
                shutil.copyfileobj(inp, out)

    # clean temp
    shutil.rmtree(parts_dir, ignore_errors=True)

    # persist as Attachment and Message (attachment-only)
    att = Attachments.objects.create(
        conversation_id=conversation_id,
        uploaded_by=request.user,
        file=str(final_rel),
        mime_type=us.mime_type,
        size=us.total_size,
    )

    msg = Message.objects.create(
        conversation_id=conversation_id,
        sender=request.user,
        content=message_text or "",
        is_read=False,
    )
    # Refresh to ensure iv/content fields reflect DB state before decrypting.
    msg.refresh_from_db(fields=["content", "iv"])
    decrypted_text = msg.get_decrypted_content() or ""
    if msg.iv and decrypted_text == (msg.content or ""):
        # Decryption fell back to raw ciphertext; prefer the submitted text instead.
        decrypted_text = ""
    display_text = decrypted_text or message_text or ""
    # (If you also mirror file onto Message.attachment, do it here.)

    # async thumbnail (if configured)
    if generate_attachment_thumbnail:
        try:
            generate_attachment_thumbnail.delay(att.id)
        except Exception:
            pass

    # notify room
    channel_layer = get_channel_layer()
    attachment_url = (
        att.file.url if hasattr(att.file, "url") else f"{settings.MEDIA_URL}{final_rel}"
    )
    sender_profile_picture = (
        request.user.profile_picture.url
        if getattr(request.user, "profile_picture", None)
        else "/static/img/default-profile.jpg"
    )

    async_to_sync(channel_layer.group_send)(
        _group_name(conversation_id),
        {
            "type": "chat_message",
            "event": "attachment_uploaded",
            "attachment_id": att.id,
            "attachment_url": attachment_url,
            "mime_type": att.mime_type,
            "uploaded_by": request.user.username,
            "timestamp": timezone.localtime().isoformat(),
            "message_text": display_text,
            "sender_profile_picture": sender_profile_picture,
        },
    )

    return JsonResponse(
        {
            "ok": True,
            "attachment_id": att.id,
            "attachment_url": attachment_url,
            "mime_type": att.mime_type,
            "message_text": display_text,
        },
        status=200,
    )
