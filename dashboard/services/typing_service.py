# dashboard/services/typing_service.py
from __future__ import annotations

import time
from typing import List, Dict, Optional

from django.conf import settings

try:
    # redis-py >= 4.2 provides asyncio client
    from redis.asyncio import Redis
except Exception:  # pragma: no cover
    Redis = None

# In-memory fallback for dev (when Redis isn't present/configured)
_INMEM: Dict[str, Dict[str, float]] = {}  # {conv_id: {username: expiry_epoch}}


def _now() -> float:
    return time.time()


def _get_redis_url() -> Optional[str]:
    # Prefer CHAT_REDIS_URL, fall back to REDIS_URL
    return getattr(settings, "CHAT_REDIS_URL", None) or getattr(settings, "REDIS_URL", None)


async def _redis_client() -> Optional["Redis"]:
    url = _get_redis_url()
    if not url or Redis is None:
        return None
    # decode_responses=True → get/set str, not bytes
    return Redis.from_url(url, decode_responses=True)


async def mark_typing_and_get_active(
    conversation_id: str | int,
    username: str,
    is_typing: bool,
    ttl_seconds: int = 20,
) -> List[str]:
    """
    Mark `username` as typing/not-typing for `conversation_id` and return
    the list of currently-active typing usernames.

    Redis strategy (O(1) reads):
      - Maintain a SET: typing:{conv} with members = usernames.
      - Maintain TTL keys: typingttl:{conv}:{username} → "1" with EX=ttl.
      - When listing members, read SMEMBERS, drop those whose TTL key is gone,
        and lazily SREM them.

    In-memory fallback mirrors the behavior for dev environments.
    """
    conv = str(conversation_id)
    client = await _redis_client()

    if client:
        set_key = f"typing:{conv}"
        ttl_key = f"typingttl:{conv}:{username}"

        if is_typing:
            # add to set + set TTL heartbeat
            await client.sadd(set_key, username)
            await client.set(ttl_key, "1", ex=ttl_seconds)
        else:
            # user stopped typing: remove from set + nuke TTL key
            await client.srem(set_key, username)
            await client.delete(ttl_key)

        # Fetch all candidates in O(1)
        members = await client.smembers(set_key)
        if not members:
            return []

        # Keep only those whose TTL key still exists; lazily clean up set
        alive: list[str] = []
        to_remove: list[str] = []
        # Pipeline to minimize round-trips
        pipe = client.pipeline()
        for u in members:
            pipe.exists(f"typingttl:{conv}:{u}")
        exists_flags = await pipe.execute()

        for u, alive_flag in zip(members, exists_flags):
            if alive_flag:
                alive.append(u)
            else:
                to_remove.append(u)

        if to_remove:
            await client.srem(set_key, *to_remove)

        return sorted(alive)

    # -------- In-memory fallback (dev) --------
    bucket = _INMEM.setdefault(conv, {})
    now = _now()

    if is_typing:
        bucket[username] = now + ttl_seconds
    else:
        bucket.pop(username, None)

    # prune expired
    expired = [u for u, exp in bucket.items() if exp < now]
    for u in expired:
        bucket.pop(u, None)

    return sorted(bucket.keys())