# loadtest_notifications.py
import asyncio
import os
import json
import time
from collections import defaultdict, Counter

import requests
import websockets

BASE_HTTP = "http://127.0.0.1:8000"
BASE_WS = "ws://127.0.0.1:8000"
LOADTEST_SECRET = os.environ.get("LOADTEST_SECRET", "super-secret-loadtest-key")

WS_NOTIF_PATH = "/ws/notifications/"  # adjust if needed

NUM_USERS = 100
MAX_PARALLEL_HANDSHAKES = 40
USER_START_STAGGER = 0.03
TEST_DURATION = 20.0  # seconds to listen for notifications

# ---------- login ----------

def login_users_sync():
    users = {}
    session = requests.Session()

    for i in range(NUM_USERS):
        username = f"lt_user_{i}"
        print(f"[{username}] logging in for notifications…")
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
        users[i] = dict(cookies)

    return users

# ---------- per-user WS ----------

async def run_notif_user(user_index: int, cookies: dict, handshake_sem: asyncio.Semaphore):
    """
    Connect to NotificationConsumer and listen for TEST_DURATION seconds.
    Returns:
      {
        "ok": bool,
        "error": str|None,
        "notifications": int,
      }
    """
    username = f"lt_user_{user_index}"
    cookie_header_value = "; ".join(f"{k}={v}" for k, v in cookies.items())
    ws_url = (
        f"{BASE_WS}{WS_NOTIF_PATH}"
        f"?lt_user={username}&lt_secret={LOADTEST_SECRET}"
    )
    print(f"[{username}] connecting to {ws_url}")

    ws = None
    error_str = None
    notif_count = 0

    async def recv_loop():
        nonlocal notif_count
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    try:
                        raw = raw.decode("utf-8")
                    except Exception:
                        continue
                try:
                    data = json.loads(raw)
                except Exception:
                    continue

                if data.get("type") == "message":
                    notif_count += 1
        except Exception:
            # connection close is normal after we cancel
            pass

    try:
        async with handshake_sem:
            ws = await websockets.connect(
                ws_url,
                open_timeout=30,
                additional_headers=[("Cookie", cookie_header_value)],
            )

        print(f"[{username}] WS connected for notifications")

        recv_task = asyncio.create_task(recv_loop())

        # just sit and listen
        await asyncio.sleep(TEST_DURATION)

        # stop recv loop
        recv_task.cancel()
        try:
            await recv_task
        except asyncio.CancelledError:
            pass

    except Exception as e:
        error_str = repr(e)
        print(f"[{username}] WS error: {error_str}")
    finally:
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass

    ok = error_str is None
    return {
        "ok": ok,
        "error": error_str,
        "notifications": notif_count,
    }

# ---------- orchestration ----------

async def main_async(users):
    handshake_sem = asyncio.Semaphore(MAX_PARALLEL_HANDSHAKES)
    tasks = []

    for i in range(NUM_USERS):
        cookies = users[i]
        await asyncio.sleep(USER_START_STAGGER)
        tasks.append(run_notif_user(i, cookies, handshake_sem))

    print("\n=== Notification WS phase started ===")
    print(f"Now, in another shell, trigger notifications for lt_user_0..lt_user_{NUM_USERS-1}")
    print(f"Listening for {TEST_DURATION} seconds...\n")

    results = await asyncio.gather(*tasks)

    print("\n=== Notification WS phase complete ===\n")

    total_users = NUM_USERS
    ok_users = sum(1 for r in results if r["ok"])
    error_counter = Counter(r["error"] for r in results if r["error"])

    print("========== NOTIFICATION LOAD SUMMARY ==========")
    print(f"Total users simulated:   {total_users}")
    print(f"Users connected OK:      {ok_users}")
    print(f"Users failed to connect: {total_users - ok_users}")
    print()
    print("Error types:")
    if not error_counter:
        print("  (none)")
    else:
        for err, count in error_counter.most_common():
            print(f"  {err}: {count}")
    print()

    # Per-user notification counts
    counts = [r["notifications"] for r in results]
    print("Notifications received:")
    print(f"  min:   {min(counts) if counts else 0}")
    print(f"  avg:   {sum(counts)/len(counts) if counts else 0:.2f}")
    print(f"  max:   {max(counts) if counts else 0}")
    print()
    for idx, r in enumerate(results):
        print(f"  lt_user_{idx}: {r['notifications']} notifications")
    print("===============================================")

def main():
    users = login_users_sync()
    asyncio.run(main_async(users))

if __name__ == "__main__":
    main()
