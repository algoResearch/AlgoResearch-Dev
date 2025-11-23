# dashboard/realtime/dispatcher.py
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import sys
from typing import Any, Dict, Tuple, Optional

import django
from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.conf import settings

try:
    from redis.asyncio import Redis
except Exception:  # pragma: no cover
    Redis = None

# Lazy Django setup if run as a standalone module (python -m ...)
if not settings.configured:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "algoresearch.settings.dev")
    django.setup()

from dashboard.services.chat_service import build_group_chat_event  # noqa
from dashboard.models import Message  # noqa

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ---- Config ----
STREAM_NAME = getattr(settings, "CHAT_STREAM_NAME", "stream:messages")
STREAM_GROUP = getattr(settings, "CHAT_STREAM_GROUP", "chat-dispatchers")
DLQ_STREAM = getattr(settings, "CHAT_DLQ_STREAM", f"{STREAM_NAME}:dlq")
READ_COUNT = int(getattr(settings, "CHAT_STREAM_READ_COUNT", 100))
BLOCK_MS = int(getattr(settings, "CHAT_STREAM_BLOCK_MS", 5000))
CLAIM_IDLE_MS = int(getattr(settings, "CHAT_STREAM_CLAIM_IDLE_MS", 60_000))  # 60s
PENDING_CLAIM_BATCH = int(getattr(settings, "CHAT_PENDING_CLAIM_BATCH", 200))

# Try CHAT_REDIS_URL first, fall back to REDIS_URL
REDIS_URL = getattr(settings, "CHAT_REDIS_URL", None) or getattr(settings, "REDIS_URL", "redis://127.0.0.1:6379/0")


def _consumer_name() -> str:
    host = socket.gethostname()
    pid = os.getpid()
    return f"{host}:{pid}"


async def _redis() -> Redis:
    if Redis is None:
        raise RuntimeError("redis.asyncio is not installed. Install `redis>=4.2`.")
    return Redis.from_url(REDIS_URL, decode_responses=True)


async def _ensure_consumer_group(r: Redis) -> None:
    try:
        # MKSTREAM creates stream if missing; ignore if group exists
        await r.xgroup_create(STREAM_NAME, STREAM_GROUP, id="$", mkstream=True)
        logger.info("Created consumer group %s on %s", STREAM_GROUP, STREAM_NAME)
    except Exception as e:
        # BUSYGROUP if already exists; ignore
        msg = str(e)
        if "BUSYGROUP" in msg:
            return
        logger.exception("xgroup_create failed")
        raise


def _parse_entry(fields: Dict[str, str]) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
    """
    Accepts either:
      - {"payload": "<json>"}  (preferred)
      - or a flat map that includes keys directly.
    Returns: (conversation_id, frame_or_none). If frame is None, caller may build it.
    """
    try:
        payload_raw = fields.get("payload")
        if payload_raw:
            payload = json.loads(payload_raw)
        else:
            # Some producers may write flat fields directly
            payload = {k: _maybe_json(v) for k, v in fields.items()}

        conv_id = payload.get("conversation_id")
        # If a prebuilt frame is present, use it directly.
        frame = payload.get("frame")
        if frame and isinstance(frame, dict):
            # Ensure event handler name matches consumer (chat_message/edit_message/user_typing)
            t = frame.get("type")
            if t not in ("chat_message", "edit_message", "user_typing"):
                # default to chat_message for safety if missing/unknown
                frame["type"] = "chat_message"
            return int(conv_id) if conv_id is not None else None, frame

        # Otherwise return payload for later frame construction by message_id
        return int(conv_id) if conv_id is not None else None, payload
    except Exception:
        logger.exception("Failed to parse stream entry fields=%s", fields)
        return None, None


def _maybe_json(val: str):
    try:
        return json.loads(val)
    except Exception:
        return val


@sync_to_async
def _load_message(mid: int) -> Message:
    return Message.objects.select_related("sender", "conversation").get(id=mid)


async def _to_frame(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Build a fan-out frame if the stream payload only provided identifiers.
    Expected keys:
      - conversation_id (int)
      - message_id (int)
      - (optional) event_type: "chat_message" | "edit_message"
    """
    try:
        mid = int(payload["message_id"])
        evt = payload.get("event_type") or "chat_message"

        msg = await _load_message(mid)
        if evt == "chat_message":
            return await build_group_chat_event(msg)
        elif evt == "edit_message":
            # build_edit_event returns {"type": "edit_message", ...}
            from dashboard.services.chat_service import build_edit_event  # local import to avoid cycles
            return await build_edit_event(msg)
        else:
            # Unknown event type; default to chat_message
            return await build_group_chat_event(msg)
    except Exception:
        logger.exception("Failed to build frame from payload=%s", payload)
        return None


async def _deliver(conversation_id: int, frame: Dict[str, Any]) -> None:
    """
    Send to Channels group `chat_{conversation_id}`.
    The frame *must* include a `type` that maps to a method on ChatConsumer.
    """
    group = f"chat_{conversation_id}"
    layer = get_channel_layer()
    # Channels requires 'type' lowercase; rest of keys fan out to consumer handler
    await layer.group_send(group, frame)


async def _ack(r: Redis, entry_id: str) -> None:
    await r.xack(STREAM_NAME, STREAM_GROUP, entry_id)


async def _dlq(r: Redis, entry_id: str, fields: Dict[str, str], error: str) -> None:
    await r.xadd(DLQ_STREAM, {"entry_id": entry_id, "error": error, "payload": json.dumps(fields)}, maxlen=10_000)


async def _claim_stale(r: Redis, consumer_name: str) -> None:
    """
    Periodically claim messages stuck in Pending > CLAIM_IDLE_MS.
    """
    try:
        pending = await r.xpending_range(
            STREAM_NAME, STREAM_GROUP, min="-", max="+", count=PENDING_CLAIM_BATCH
        )
        if not pending:
            return
        stale_ids = [p["message_id"] for p in pending if p["idle"] >= CLAIM_IDLE_MS]
        if stale_ids:
            claimed = await r.xclaim(
                STREAM_NAME, STREAM_GROUP, consumer_name, min_idle_time=CLAIM_IDLE_MS, message_ids=stale_ids
            )
            if claimed:
                logger.info("Claimed %d stale messages", len(claimed))
    except Exception:
        logger.exception("Claim stale failed")


async def run_dispatcher(stop_event: Optional[asyncio.Event] = None) -> None:
    """
    Main loop:
      - ensure group
      - read from stream (XREADGROUP)
      - deliver to Channels group
      - ack or DLQ
    """
    consumer_name = _consumer_name()
    r = await _redis()
    await _ensure_consumer_group(r)

    last_claim = 0.0

    logger.info("Dispatcher started; stream=%s group=%s consumer=%s", STREAM_NAME, STREAM_GROUP, consumer_name)

    while True:
        if stop_event and stop_event.is_set():
            logger.info("Dispatcher stopping (stop_event set)")
            break

        try:
            # Block and read up to READ_COUNT messages for this consumer
            resp = await r.xreadgroup(
                groupname=STREAM_GROUP,
                consumername=consumer_name,
                streams={STREAM_NAME: ">"},
                count=READ_COUNT,
                block=BLOCK_MS,
            )

            # resp structure: [(stream, [(entry_id, {field: value}), ...])]
            if not resp:
                # Periodically try to claim stale messages
                now = asyncio.get_running_loop().time()
                if now - last_claim > 10:  # seconds
                    await _claim_stale(r, consumer_name)
                    last_claim = now
                continue

            _, entries = resp[0]
            for entry_id, fields in entries:
                conv_id, parsed = _parse_entry(fields)
                if not parsed or conv_id is None:
                    await _dlq(r, entry_id, fields, "parse_error")
                    await _ack(r, entry_id)
                    continue

                # If we received a prebuilt frame, send it; otherwise build from message_id
                frame = parsed if "type" in parsed else await _to_frame(parsed)
                if not frame:
                    await _dlq(r, entry_id, fields, "frame_build_failed")
                    await _ack(r, entry_id)
                    continue

                try:
                    await _deliver(conv_id, frame)
                    await _ack(r, entry_id)
                except Exception as e:
                    logger.exception("Deliver failed for conv=%s entry=%s", conv_id, entry_id)
                    await _dlq(r, entry_id, fields, f"deliver_error:{e!s}")
                    # do not ack; let it be retried/claimed

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Dispatcher loop error")
            await asyncio.sleep(1.0)  # backoff and continue

    await r.close()
    logger.info("Dispatcher terminated cleanly")
    

# --------- CLI entrypoint ---------
async def _amain() -> None:
    stop = asyncio.Event()

    def _handle_sig(*_):
        stop.set()

    try:
        import signal
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                asyncio.get_running_loop().add_signal_handler(sig, _handle_sig)
            except NotImplementedError:
                # Windows
                pass
    except Exception:
        pass

    await run_dispatcher(stop_event=stop)


if __name__ == "__main__":
    # Allow: python -m dashboard.realtime.dispatcher
    if not settings.configured:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "algoresearch.settings.dev")
        django.setup()
    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        sys.exit(130)
