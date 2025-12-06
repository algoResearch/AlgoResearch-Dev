import json
import logging
import os
from urllib.parse import parse_qs

import aiofiles
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer, AsyncWebsocketConsumer
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from dashboard.models import Conversation
from dashboard.services.chat_service import (
    enqueue_send_message,
    enqueue_edit_message,
    build_group_chat_event,
    build_edit_event,
)
from dashboard.services.typing_service import mark_typing_and_get_active

logger = logging.getLogger(__name__)

FANOUT_MODE = getattr(settings, "CHAT_FANOUT_MODE", os.getenv("CHAT_FANOUT_MODE", "direct")).lower()
STREAM_NAME = getattr(settings, "CHAT_STREAM", os.getenv("CHAT_STREAM", "stream:messages"))
REDIS_URL = getattr(settings, "REDIS_URL", os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"))

LOADTEST_SECRET = getattr(settings, "LOADTEST_SECRET", "super-secret-loadtest-key")
IS_LOADTEST_ENV = getattr(settings, "IS_LOADTEST_ENV", False)

try:
    import redis.asyncio as aioredis  # type: ignore
except Exception:  # pragma: no cover
    aioredis = None

MAX_TEXT_BYTES = 16 * 1024
User = get_user_model()


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for chat messages.
    - Auth required
    - Normal users must belong to the conversation
    - Loadtest users (username starts with `lt_user_`) can join any convo in loadtest envs
      when authenticated via lt_user/lt_secret query params
    - Uses JSON frames
    - Fan-out: direct (default) or stream-backed ('CHAT_FANOUT_MODE=stream')
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.conversation_id: int | None = None
        self.group_name: str | None = None
        self._redis = None  # lazy for stream mode
        self.is_loadtest_user: bool = False

    # ---------- Connection lifecycle ----------

    async def connect(self):
        try:
            # Resolve conversation id from URL kwarg
            raw_id = self.scope.get("url_route", {}).get("kwargs", {}).get("conversation_id")
            try:
                self.conversation_id = int(raw_id)
            except (TypeError, ValueError):
                logger.warning("WS reject: invalid conversation_id=%r", raw_id)
                await self.close(code=4400)
                return

            # Start with whatever auth Django attached
            self.user = self.scope.get("user")
            headers = {k.decode(): v.decode() for k, v in (self.scope.get("headers") or [])}
            offered = [p.strip() for p in headers.get("sec-websocket-protocol", "").split(",") if p.strip()]
            cookie_header = headers.get("cookie")

            # Parse query string for loadtest params
            raw_qs = (self.scope.get("query_string") or b"").decode()
            qs = parse_qs(raw_qs)
            lt_user = (qs.get("lt_user", [None])[0] or "").strip()
            lt_secret = (qs.get("lt_secret", [None])[0] or "").strip()

            logger.info(
                "WS CONNECT conv=%s scope_user=%s scope_auth=%s origin=%s cookie_header=%r "
                "offered=%s mode=%s qs=%r",
                self.conversation_id,
                getattr(self.user, "username", "Anonymous"),
                getattr(self.user, "is_authenticated", False),
                headers.get("origin", ""),
                cookie_header,
                offered,
                FANOUT_MODE,
                raw_qs,
            )

            # ---------- LOADTEST FAST PATH (NO DB, NO MEMBERSHIP CHECK) ----------
            if (
                IS_LOADTEST_ENV
                and lt_user
                and lt_user.lower().startswith("lt_user_")
                and lt_secret
                and lt_secret == LOADTEST_SECRET
            ):
                logger.warning(
                    "WS loadtest FAST PATH: lt_user=%s for convo=%s "
                    "(bypassing session auth & DB in connect)",
                    lt_user,
                    self.conversation_id,
                )

                class LoadtestUser:
                    def __init__(self, username: str):
                        self.username = username
                        self.id = None  # synthetic; not in DB

                    @property
                    def is_authenticated(self) -> bool:
                        return True

                self.user = LoadtestUser(lt_user)
                self.is_loadtest_user = True

                # Join group & accept immediately
                self.group_name = f"chat_{self.conversation_id}"
                await self.channel_layer.group_add(self.group_name, self.channel_name)

                if "json" in offered:
                    await self.accept(subprotocol="json")
                else:
                    await self.accept()

                logger.info(
                    "WS accepted (loadtest fast path): username=%s convo=%s",
                    self.user.username,
                    self.conversation_id,
                )
                # Skip Redis init & DB in fast path
                return

            # ---------- NORMAL PATH (real users / non-loadtest envs) ----------

            # Require auth
            if not self.user or not getattr(self.user, "is_authenticated", False):
                logger.warning(
                    "WS reject: unauthenticated user for convo %s (cookie_header=%r, lt_user=%r)",
                    self.conversation_id,
                    cookie_header,
                    lt_user,
                )
                await self.close(code=4401)
                return

            username = (self.user.username or "").lower()
            is_loadtest_username = username.startswith("lt_user_")
            self.is_loadtest_user = self.is_loadtest_user or is_loadtest_username

            # Load conversation
            conversation = await self._get_conversation(self.conversation_id)
            if conversation is None:
                logger.warning("WS reject: missing conversation %s", self.conversation_id)
                await self.close(code=4404)
                return

            # Membership check ONLY for non-loadtest users
            if not self.is_loadtest_user:
                is_member = await self._is_member(conversation, self.user)
                if not is_member:
                    logger.warning(
                        "WS reject: user %s not member of convo %s",
                        getattr(self.user, "id", None),
                        self.conversation_id,
                    )
                    await self.close(code=4403)
                    return
            else:
                logger.info(
                    "WS loadtest bypass (normal path): user=%s allowed into convo %s without membership",
                    self.user.username,
                    self.conversation_id,
                )

            # Join group & accept
            self.group_name = f"chat_{self.conversation_id}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)

            if "json" in offered:
                await self.accept(subprotocol="json")
            else:
                await self.accept()

            logger.info(
                "WS accepted: user_id=%s username=%s convo=%s is_loadtest=%s",
                getattr(self.user, "id", None),
                getattr(self.user, "username", None),
                self.conversation_id,
                self.is_loadtest_user,
            )

            # Optional Redis for stream fan-out
            if FANOUT_MODE == "stream" and aioredis is not None and self._redis is not None:
                try:
                    self._redis = aioredis.from_url(
                        REDIS_URL,
                        encoding="utf-8",
                        decode_responses=True,
                    )
                except Exception:
                    logger.exception("Failed to create Redis client for stream mode; falling back to direct")
                    self._redis = None

        except Exception:
            logger.exception("WS connect failed with unexpected error")
            await self.close(code=1011)

    async def disconnect(self, code):
        try:
            if self.group_name:
                await self.channel_layer.group_discard(self.group_name, self.channel_name)
        except Exception:
            logger.exception("WS disconnect cleanup failed")
        finally:
            try:
                if self._redis is not None:
                    await self._redis.close()
            except Exception:
                pass

    # ---------- Incoming frames ----------

    async def receive_json(self, event, **kwargs):
        try:
            if not isinstance(event, dict):
                try:
                    event = json.loads(event)
                except Exception as e:
                    logger.exception("receive_json JSON decode failed")
                    await self._send_error(f"Invalid JSON payload: {e!r}")
                    return

            t = event.get("type")

            if t == "message":
                msg = (event.get("message") or "").strip()
                attachment = event.get("attachment")
                if not msg and not attachment:
                    return await self._send_error("Message or attachment required.")
                if msg and len(msg.encode("utf-8")) > MAX_TEXT_BYTES:
                    return await self._send_error("Message is too large; please send as a file.")

                client_id = event.get("message_client_id")

                # ---------- LOADTEST MESSAGE FAST PATH (NO DB) ----------
                if self.is_loadtest_user and IS_LOADTEST_ENV:
                    ts = timezone.now()
                    frame = {
                        "id": 0,  # synthetic
                        "message": msg,
                        "sender_username": self.user.username,
                        "sender_full_name": self.user.username,
                        "sender_profile_picture": "",
                        "timestamp": ts.isoformat(),
                        "timestamp_display": ts.strftime("%b %d, %Y %I:%M %p"),
                        "is_edited": False,
                        "attachment_url": "",
                        "attachment_type": "",
                        "thumbnail_url": "",
                    }
                    if client_id:
                        frame["message_client_id"] = client_id

                    await self._fanout_chat_event("chat_message", frame)
                    return

                # ---------- NORMAL PATH (persisted messages) ----------
                saved = await enqueue_send_message(
                    user=self.user,
                    conversation_id=self.conversation_id,
                    text=msg,
                    attachment=attachment,
                    client_id=client_id,
                )
                frame = await build_group_chat_event(saved)

                # Echo client id back for loadtest latency matching
                if client_id:
                    frame["message_client_id"] = client_id

                await self._fanout_chat_event("chat_message", frame)

            elif t == "edit_message":
                message_id = event.get("message_id")
                new_content = (event.get("content") or "").strip()

                if not isinstance(message_id, int):
                    return await self._send_error("Invalid message ID.")
                if not new_content:
                    return await self._send_error("Message content cannot be empty.")

                saved = await enqueue_edit_message(
                    user=self.user,
                    conversation_id=self.conversation_id,
                    message_id=message_id,
                    new_text=new_content,
                )
                frame = await build_edit_event(saved)
                await self._fanout_chat_event("edit_message", frame)

            elif t == "typing":
                is_typing = bool(event.get("is_typing"))
                active_usernames = await mark_typing_and_get_active(
                    conversation_id=self.conversation_id,
                    username=self.user.username,
                    is_typing=is_typing,
                    ttl_seconds=20,
                )
                if self.group_name:
                    await self.channel_layer.group_send(
                        self.group_name,
                        {"type": "user_typing", "typing_users": active_usernames},
                    )

            elif t in ("unsend_message", "delete_conversation"):
                return await self._send_error("Operation not available in this beta path.")

            else:
                return await self._send_error(f"Unknown message type: {t}")

        except Exception as e:
            logger.exception("receive_json failed")
            await self._send_error(f"Failed to process the message: {e!r}")

    # ---------- Fan-out handlers ----------

    async def chat_message(self, event):
        await self.send_json(
            {"type": "chat_message", **{k: v for k, v in event.items() if k != "type"}}
        )

    async def edit_message(self, event):
        await self.send_json(
            {"type": "edit_message", **{k: v for k, v in event.items() if k != "type"}}
        )

    async def user_typing(self, event):
        await self.send_json(
            {"type": "user_typing", "typing_users": event.get("typing_users", [])}
        )

    # ---------- Helpers ----------

    async def _fanout_chat_event(self, kind: str, frame: dict):
        payload = {"type": kind, **{k: v for k, v in frame.items() if k != "type"}}

        if FANOUT_MODE == "stream" and self._redis is not None and self.conversation_id is not None:
            try:
                await self._redis.xadd(
                    STREAM_NAME,
                    {
                        "conversation_id": str(self.conversation_id),
                        "payload": json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
                    },
                    maxlen=100_000,
                    approximate=True,
                )
                return
            except Exception:
                logger.exception("Stream publish failed; falling back to direct fan-out")

        if self.group_name:
            await self.channel_layer.group_send(self.group_name, payload)

    async def _send_error(self, message: str):
        await self.send_json({"type": "error", "message": message})

    @database_sync_to_async
    def _get_conversation(self, convo_id: int):
        try:
            return Conversation.objects.get(pk=convo_id)
        except Conversation.DoesNotExist:
            return None

    @database_sync_to_async
    def _is_member(self, conversation: Conversation, user):
        return conversation.is_user_part_of_conversation(user)

class FileTransferConsumer(AsyncWebsocketConsumer):
    """
    Prefer HTTP/S3 multipart. If you keep WS, ensure this stays fully async.
    """
    async def connect(self):
        await self.accept()
        self.fp = None
        self.file_path = None

    async def disconnect(self, code):
        try:
            if self.fp:
                await self.fp.flush()
                await self.fp.close()
        except Exception:
            logger.exception("Error closing file on disconnect")

    async def receive(self, text_data=None, bytes_data=None):
        try:
            if text_data:
                data = json.loads(text_data)
                t = data.get("type")

                if t == "file_metadata":
                    name = data["metadata"]["filename"]
                    upload_dir = os.path.join(settings.MEDIA_ROOT, "uploads")
                    os.makedirs(upload_dir, exist_ok=True)
                    self.file_path = os.path.join(upload_dir, name)
                    self.fp = await aiofiles.open(self.file_path, "wb")

                elif t == "file_complete":
                    if self.fp:
                        await self.fp.flush()
                        await self.fp.close()
                        self.fp = None
                    await self.send(json.dumps({
                        "type": "file_complete",
                        "status": "success",
                        "file_path": self.file_path
                    }))

            if bytes_data and self.fp:
                await self.fp.write(bytes_data)

        except json.JSONDecodeError:
            await self.send(json.dumps({"type": "error", "message": "Invalid JSON for file control frame"}))
        except Exception:
            logger.exception("FileTransferConsumer receive failed")
            await self.send(json.dumps({"type": "error", "message": "File transfer error"}))



class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """
    Notifications WS consumer.

    - Normal users authenticate via session/cookie.
    - Loadtest users may authenticate via querystring:
        ?lt_user=lt_user_1&lt_secret=super-secret-loadtest-key

    - Each authenticated user joins group:
        user_{user.id}

    - Internal group_send expects:
        type="notification.message"
    - Client receives:
        type="notification"
    """

    async def connect(self):
        try:
            user = self.scope.get("user")
            # Parse query string for loadtest override
            raw_qs = (self.scope.get("query_string") or b"").decode()
            qs = parse_qs(raw_qs)
            lt_user = (qs.get("lt_user", [None])[0] or "").strip()
            lt_secret = (qs.get("lt_secret", [None])[0] or "").strip()

            # ---------- LOADTEST DEBUG PATH ----------
            if (
                settings.DEBUG
                and lt_user.lower().startswith("lt_user_")
                and lt_secret == LOADTEST_SECRET
            ):
                # Prefer real DB lt users if they exist (more realistic)
                db_user = await self._get_user_by_username(lt_user)
                if db_user:
                    user = db_user
                    logger.warning(
                        "Notifications loadtest auth using DB user=%s id=%s",
                        user.username, user.id
                    )
                else:
                    # Hard fast path if DB user missing.
                    class LoadtestUser:
                        def __init__(self, username: str):
                            self.username = username
                            self.id = None

                        @property
                        def is_authenticated(self):
                            return True

                    user = LoadtestUser(lt_user)
                    logger.warning(
                        "Notifications loadtest FAST PATH using synthetic user=%s",
                        lt_user
                    )

            # ---------- AUTH GATE ----------
            if not user or not getattr(user, "is_authenticated", False):
                logger.warning("Notifications WS reject: unauthenticated")
                await self.close(code=4401)
                return

            self.user = user

            # Synthetic users don't have ids, so group by username
            if getattr(user, "id", None) is not None:
                self.user_group_name = f"user_{user.id}"
            else:
                self.user_group_name = f"user_{user.username}"

            await self.channel_layer.group_add(self.user_group_name, self.channel_name)
            await self.accept()
            logger.info(
                "Notifications WS accepted user=%s group=%s",
                getattr(user, "username", None),
                self.user_group_name
            )

        except Exception:
            logger.exception("NotificationConsumer.connect failed")
            await self.close(code=1011)

    async def disconnect(self, close_code):
        try:
            if getattr(self, "user_group_name", None):
                await self.channel_layer.group_discard(
                    self.user_group_name,
                    self.channel_name
                )
                logger.info("Notifications WS disconnected group=%s", self.user_group_name)
        except Exception:
            logger.exception("NotificationConsumer.disconnect failed")

    # --------------------
    # Fanout handler
    # --------------------
    async def notification_message(self, event):
        """
        Receive from group_send.
        Convert to client WS frame.
        """
        await self.send_json({
            "type": "notification",
            "notification_client_id": event.get("notification_client_id"),
            "title": event.get("title", "Notification"),
            "message": event.get("message"),
            "org_id": event.get("org_id"),
            "conversation_id": event.get("conversation_id"),
            "sender": event.get("sender", "System"),
            "sender_profile_picture": event.get(
                "sender_profile_picture",
                "/static/img/default-profile.jpg"
            ),
            "conversation_url": event.get("conversation_url"),
            "timestamp": event.get("timestamp"),
        })

    # --------------------
    # Helpers
    # --------------------
    @database_sync_to_async
    def _get_user_by_username(self, username: str):
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            return None
        