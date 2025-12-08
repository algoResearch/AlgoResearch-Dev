import asyncio
import os
import random
import json
import time
import math
from collections import Counter, defaultdict
import requests
import websockets

# ----------------- ENV / TARGET CONFIG -----------------

# high-level environment selector: local | staging | prod
LOADTEST_ENV = os.environ.get("LOADTEST_ENV", "local").lower().strip()

if LOADTEST_ENV == "staging":
    default_http = "https://algoresearch-staging-6b4399c2d0ad.herokuapp.com"
    default_ws = "wss://algoresearch-staging-6b4399c2d0ad.herokuapp.com"
elif LOADTEST_ENV == "prod":
    # only use this when you're *sure* you want to hit prod
    default_http = "https://www.ryanccarmody.com"
    default_ws = "wss://www.ryanccarmody.com"
else:
    # local dev default
    default_http = "http://127.0.0.1:8000"
    default_ws = "ws://127.0.0.1:8000"

# allow explicit overrides if you want a custom target
BASE_HTTP = os.environ.get("LOADTEST_BASE_HTTP", default_http)
BASE_WS = os.environ.get("LOADTEST_BASE_WS", default_ws)

LOADTEST_SECRET = os.environ.get("LOADTEST_SECRET", "super-secret-loadtest-key")

# login behavior:
# - by default, local uses /loadtest-login/
# - staging/prod default to SKIP_HTTP_LOGIN=1 unless you explicitly override
_raw_skip_login = os.environ.get("LOADTEST_SKIP_LOGIN")
if _raw_skip_login is None:
    SKIP_HTTP_LOGIN = LOADTEST_ENV in ("staging", "prod")
else:
    SKIP_HTTP_LOGIN = _raw_skip_login == "1"

NUM_USERS = int(os.environ.get("LOADTEST_NUM_USERS", "10"))
MESSAGES_PER_USER = 3
MIN_CONVO_ID = 4
MAX_CONVO_ID = 4

MAX_PARALLEL_HANDSHAKES = 10
USER_START_STAGGER = 0.05

DEBUG_SAMPLE_FRAMES = True



def percentile(data, p):
    if not data:
        return None
    data_sorted = sorted(data)
    k = (len(data_sorted) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return data_sorted[int(k)]
    d0 = data_sorted[f] * (c - k)
    d1 = data_sorted[c] * (k - f)
    return d0 + d1


# ----------------- LOGIN PHASE (SYNC) -----------------
def login_users_sync():
    """
    Do all /loadtest-login/ calls synchronously before we start asyncio.
    Returns a dict: user_index -> (cookies_dict, conversation_id).
    """
    users = {}

    # NEW: fast path for environments without /loadtest-login/ (like prod)
    if SKIP_HTTP_LOGIN:
        for i in range(NUM_USERS):
            username = f"lt_user_{i}"
            convo_id = random.randint(MIN_CONVO_ID, MAX_CONVO_ID)
            print(f"[{username}] SKIPPING HTTP login, using synthetic cookies")
            users[i] = ({}, convo_id)  # empty cookie dict
        return users

    # original local/dev path
    session = requests.Session()

    for i in range(NUM_USERS):
        username = f"lt_user_{i}"
        convo_id = random.randint(MIN_CONVO_ID, MAX_CONVO_ID)

        print(f"[{username}] logging in…")
        resp = session.post(
            f"{BASE_HTTP}/loadtest-login/",
            data={"username": username, "secret": LOADTEST_SECRET},
        )
        resp.raise_for_status()
        try:
            print(f"[{username}] login response:", resp.json())
        except Exception:
            pass

        cookies = session.cookies.get_dict()
        users[i] = (dict(cookies), convo_id)

    return users


# ----------------- PER-USER WS TASK (ASYNC) -----------------

async def run_user(user_index: int, cookies: dict, conversation_id: int,
                   handshake_sem: asyncio.Semaphore):
    """
    Open a WS connection, send MESSAGES_PER_USER messages, record latencies.

    Returns a dict with:
      - ok: bool
      - conversation_id: int
      - error: str | None
      - messages_sent: int
      - latencies: list[float] (ms)
    """
    username = f"lt_user_{user_index}"

    cookie_header_value = "; ".join(f"{k}={v}" for k, v in cookies.items())
    ws_url = (
        f"{BASE_WS}/ws/chat/{conversation_id}/"
        f"?lt_user={username}&lt_secret={LOADTEST_SECRET}"
    )
    print(f"[{username}] connecting to {ws_url}")

    ws = None
    error_str = None
    messages_sent = 0
    latencies: list[float] = []

    # Map client_id -> send_timestamp
    pending: dict[str, float] = {}

    async def recv_loop():
        """
        Receive loop:
        - Parses JSON frames
        - For 'chat_message' events, tries to match the echo of messages
          we sent, to measure latency.

        We handle two cases:
          1) Server echoes message_client_id / client_id.
          2) Server does *not* echo client_id, but does echo:
             - type = "chat_message"
             - sender_username == our username
             - message starts with "Hello from <username>"
        """
        nonlocal latencies
        sample_printed = 0

        try:
            print(f"[{username}] recv_loop started")
            async for raw in ws:
                now = time.perf_counter()

                # websockets usually gives us str; if bytes, decode
                if isinstance(raw, bytes):
                    try:
                        raw = raw.decode("utf-8", "ignore")
                    except Exception:
                        continue

                try:
                    data = json.loads(raw)
                except Exception:
                    if DEBUG_SAMPLE_FRAMES and user_index < 2:
                        print(f"[{username}] RECV NON-JSON: {raw!r}")
                    continue

                if DEBUG_SAMPLE_FRAMES and user_index < 2 and sample_printed < 10:
                    print(f"[{username}] RECV RAW: {data}")
                    sample_printed += 1

                if data.get("type") != "chat_message":
                    # ignore errors, typing, etc. for latency
                    continue

                matched = False

                # --- Case 1: server echoes a client_id-like field ---
                client_id = (
                    data.get("message_client_id")
                    or data.get("client_id")
                )
                if client_id and client_id in pending:
                    sent_ts = pending.pop(client_id)
                    latency_ms = (now - sent_ts) * 1000.0
                    latencies.append(latency_ms)
                    matched = True

                # --- Case 2: no client_id, but we can infer it's our own echo ---
                if not matched:
                    msg = (data.get("message") or "")
                    sender = (data.get("sender_username") or "").lower()
                    if sender == username.lower() and msg.startswith(f"Hello from {username}"):
                        # Pick the oldest pending client_id for this user
                        own_keys = sorted(
                            k for k in pending.keys()
                            if k.startswith(username + "-")
                        )
                        if own_keys:
                            k = own_keys[0]
                            sent_ts = pending.pop(k)
                            latency_ms = (now - sent_ts) * 1000.0
                            latencies.append(latency_ms)
                            matched = True

                if DEBUG_SAMPLE_FRAMES and user_index < 2:
                    status = "matched" if matched else "unmatched"
                    print(f"[{username}] processed chat_message ({status}); pending={len(pending)}")

        except asyncio.CancelledError:
            # Expected when we cancel at the end
            pass
        except Exception as e:
            print(f"[{username}] recv_loop error: {e!r}")

    try:
        # Limit concurrent handshakes
        async with handshake_sem:
            ws = await websockets.connect(
                ws_url,
                subprotocols=["json"],
                open_timeout=60,
                additional_headers=[
                    ("Cookie", cookie_header_value),
                ],
            )
        print(f"[{username}] WS connected")

        recv_task = asyncio.create_task(recv_loop())

        # Send messages
        for i in range(MESSAGES_PER_USER):
            text = f"Hello from {username} #{i}"
            client_id = f"{username}-{i}"
            payload = {
                "type": "message",
                "message": text,
                "attachment": None,
                "message_client_id": client_id,
            }
            pending[client_id] = time.perf_counter()
            await ws.send(json.dumps(payload))
            messages_sent += 1
            print(f"[{username}] sent: {text}")
            await asyncio.sleep(random.uniform(0.5, 1.5))

        # keep them idle a bit to simulate “being online”
        await asyncio.sleep(random.uniform(2, 5))

        # Done sending; stop recv loop and close
        recv_task.cancel()
        try:
            await recv_task
        except asyncio.CancelledError:
            pass

        await ws.close()
        return {
            "ok": True,
            "conversation_id": conversation_id,
            "error": None,
            "messages_sent": messages_sent,
            "latencies": latencies,
        }

    except Exception as e:
        error_str = repr(e)
        print(f"[{username}] WS error: {error_str!r}")
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass
        return {
            "ok": False,
            "conversation_id": conversation_id,
            "error": error_str,
            "messages_sent": messages_sent,
            "latencies": latencies,
        }


# ----------------- MAIN ASYNC ORCHESTRATION -----------------

async def main_async(users):
    handshake_sem = asyncio.Semaphore(MAX_PARALLEL_HANDSHAKES)
    tasks = []

    for i in range(NUM_USERS):
        cookies, convo_id = users[i]
        await asyncio.sleep(USER_START_STAGGER)
        tasks.append(run_user(i, cookies, convo_id, handshake_sem))

    print("\n=== Starting WS phase ===\n")
    results = await asyncio.gather(*tasks)
    print("\n=== WS PHASE COMPLETE ===\n")

    total_users = NUM_USERS
    ok_users = sum(1 for r in results if r["ok"])
    failed_users = total_users - ok_users
    total_messages = sum(r["messages_sent"] for r in results)

    error_counter = Counter(r["error"] for r in results if r["error"])

    per_convo = defaultdict(lambda: {"ok": 0, "total": 0})
    for r in results:
        cid = r["conversation_id"]
        per_convo[cid]["total"] += 1
        if r["ok"]:
            per_convo[cid]["ok"] += 1

    # Latency aggregation
    all_latencies = [lat for r in results for lat in r["latencies"]]
    latency_summary = {}
    if all_latencies:
        latency_summary = {
            "count": len(all_latencies),
            "min": min(all_latencies),
            "max": max(all_latencies),
            "avg": sum(all_latencies) / len(all_latencies),
            "p95": percentile(all_latencies, 95),
            "p99": percentile(all_latencies, 99),
        }
    for idx, r in enumerate(results[:5]):
        print(f"user {idx}: {len(r['latencies'])} latency samples")
    print("========== LOAD TEST SUMMARY ==========")
    print(f"Total users simulated:   {total_users}")
    print(f"Users connected OK:      {ok_users}")
    print(f"Users failed to connect: {failed_users}")
    print(f"Total messages sent:     {total_messages}")
    print()

    print("Error types:")
    if not error_counter:
        print("  (none)")
    else:
        for err, count in error_counter.most_common():
            print(f"  {err}: {count}")
    print()

    print("Per-conversation results:")
    for cid in sorted(per_convo.keys()):
        info = per_convo[cid]
        print(f"  Conversation {cid}: {info['ok']}/{info['total']} users connected")
    print()

    if latency_summary:
        print("Message latency (ms):")
        print(f"  samples: {latency_summary['count']}")
        print(f"  min:     {latency_summary['min']:.2f}")
        print(f"  avg:     {latency_summary['avg']:.2f}")
        print(f"  p95:     {latency_summary['p95']:.2f}")
        print(f"  p99:     {latency_summary['p99']:.2f}")
        print(f"  max:     {latency_summary['max']:.2f}")
    else:
        print("Message latency (ms): no samples recorded")
    print("=======================================")


# ----------------- ENTRY POINT -----------------

def main():
    users = login_users_sync()
    asyncio.run(main_async(users))


if __name__ == "__main__":
    main()
