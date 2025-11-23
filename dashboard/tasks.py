# dashboard/tasks.py
from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile, File
from django.utils import timezone
from pathlib import Path
import base64, mimetypes, os, shlex, subprocess

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .models import Message
try:
    from .models_uploads import Attachment  # new chunked model
except Exception:
    Attachment = None

def _safe_mime(path, fallback="application/octet-stream"):
    mime, _ = mimetypes.guess_type(path)
    return mime or fallback

def _group(conversation_id: int) -> str:
    return f"chat_{conversation_id}"

def _notify_ready(conversation_id: int, payload: dict):
    ch = get_channel_layer()
    async_to_sync(ch.group_send)(_group(conversation_id), {"type": "chat_message", "event": "attachment_ready", **payload})

# -------- Legacy (base64 -> Message.attachment) ----------
@shared_task
def process_attachment_task(message_id: int, attachment: dict):
    msg = Message.objects.get(id=message_id)
    name = attachment.get("name") or "file.bin"
    b64  = attachment.get("content", "")
    data = base64.b64decode(b64 or b"")

    msg.attachment.save(name, ContentFile(data), save=False)
    msg.attachment_mime_type = _safe_mime(msg.attachment.path)
    msg.save(update_fields=["attachment", "attachment_mime_type"])

    if msg.attachment_mime_type.startswith("video/"):
        generate_thumbnail_task.delay(message_id)

@shared_task
def generate_thumbnail_task(message_id: int):
    msg = Message.objects.get(id=message_id)
    if not msg.attachment:
        return

    src = Path(msg.attachment.path)
    mime = _safe_mime(str(src))

    thumbs_dir = Path(settings.MEDIA_ROOT) / "thumbnails"
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = thumbs_dir / f"{msg.id}_thumb.jpg"

    try:
        if mime.startswith("image/"):
            from PIL import Image
            with Image.open(src) as im:
                im.thumbnail((512, 512))
                im.convert("RGB").save(thumb_path, "JPEG", quality=80)
        elif mime.startswith("video/"):
            cmd = (
                f'ffmpeg -y -ss 00:00:01 -i {shlex.quote(str(src))} '
                f'-frames:v 1 -vf "scale=\'min(512,iw)\':-1" {shlex.quote(str(thumb_path))}'
            )
            subprocess.run(cmd, shell=True, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            return
    except Exception:
        return

    # Persist to your fields
    with thumb_path.open("rb") as f:
        msg.thumbnail.save(thumb_path.name, File(f), save=False)
    msg.thumbnail_url = f"{settings.MEDIA_URL}thumbnails/{thumb_path.name}"
    msg.save(update_fields=["thumbnail", "thumbnail_url"])

    _notify_ready(msg.conversation_id, {"message_id": msg.id, "thumb_url": msg.thumbnail_url})

# Back-compat stub referenced elsewhere
def generate_video_thumbnail(*args, **kwargs):
    return None

# -------- New (chunked -> models_uploads.Attachment) ----------
@shared_task
def generate_attachment_thumbnail(attachment_id: int):
    if Attachment is None:
        return
    att = Attachment.objects.get(pk=attachment_id)
    if not att.file:
        return

    src = Path(att.file.path)
    mime = (att.mime_type or _safe_mime(str(src))).lower()

    thumbs_dir = Path(settings.MEDIA_ROOT) / "attachments" / "thumbs"
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = thumbs_dir / (src.stem + "_thumb.jpg")

    thumb_url = None
    try:
        if mime.startswith("image/"):
            from PIL import Image
            with Image.open(src) as im:
                im.thumbnail((512, 512))
                im.convert("RGB").save(thumb_path, "JPEG", quality=80)
        elif mime.startswith("video/"):
            cmd = (
                f'ffmpeg -y -ss 00:00:01 -i {shlex.quote(str(src))} '
                f'-frames:v 1 -vf "scale=\'min(512,iw)\':-1" {shlex.quote(str(thumb_path))}'
            )
            subprocess.run(cmd, shell=True, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            return

        # If Attachment has an ImageField for thumb (recommended):
        if hasattr(att, "thumbnail") and att.thumbnail is not None:
            with thumb_path.open("rb") as f:
                att.thumbnail.save(thumb_path.name, File(f), save=False)

        # Make a URL (works even if you don’t persist the ImageField)
        rel = f"attachments/thumbs/{thumb_path.name}"
        thumb_url = f"{settings.MEDIA_URL}{rel}"

        # If Attachment has a URL field/property, set it:
        if hasattr(att, "thumb_url"):
            att.thumb_url = thumb_url

        att.save()
    except Exception:
        pass

    # WS notify the room
    try:
        payload = {
            "attachment_id": att.id,
            "attachment_url": att.url,   # assumes property that returns MEDIA_URL + file.name
            "thumb_url": thumb_url,
            "mime_type": mime,
            "timestamp": timezone.localtime().isoformat(),
        }
        _notify_ready(att.conversation_id, payload)
    except Exception:
        pass