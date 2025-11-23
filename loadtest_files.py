# loadtest_files.py
import asyncio
import os
import json
import time
import math
import random
from collections import Counter

import websockets

BASE_WS = "ws://127.0.0.1:8000"
WS_FILE_PATH = "/ws/files/"  # adjust if your routing is different

# --------- config ---------
NUM_UPLOADERS = 50          # how many concurrent uploaders
FILE_SIZE_BYTES = 5 * 1024 * 1024   # 5MB per upload
CHUNK_SIZE = 64 * 1024             # 64KB per WS binary frame
MAX_PARALLEL_HANDSHAKES = 20
USER_START_STAGGER = 0.02  # seconds

# ---------- helpers ----------

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

# ---------- per-uploader task ----------

async def run_uploader(index: int, handshake_sem: asyncio.Semaphore):
    """
    Single uploader:
      - open ws
      - send metadata
      - send file chunks
      - send file_complete
      - wait for ack
    Returns dict with:
      ok: bool
      error: str | None
      duration: float (seconds) or None
    """
    ws_url = f"{BASE_WS}{WS_FILE_PATH}"
    filename = f"lt_upload_{index}.bin"
    print(f"[uploader_{index}] connecting to {ws_url} (file={filename})")

    ws = None
    start_ts = time.perf_counter()
    end_ts = None
    error_str = None

    # pre-generate bytes (random-ish)
    data = os.urandom(FILE_SIZE_BYTES)

    try:
        async with handshake_sem:
            ws = await websockets.connect(
                ws_url,
                open_timeout=30,
            )

        # 1) send metadata
        meta_frame = json.dumps({
            "type": "file_metadata",
            "metadata": {
                "filename": filename,
            },
        })
        await ws.send(meta_frame)

        # 2) send chunks
        offset = 0
        while offset < FILE_SIZE_BYTES:
            chunk = data[offset: offset + CHUNK_SIZE]
            await ws.send(chunk)
            offset += len(chunk)

        # 3) send file_complete
        complete_frame = json.dumps({
            "type": "file_complete",
        })
        await ws.send(complete_frame)

        # 4) wait for ack
        #    expect something like:
        #    {"type": "file_complete", "status": "success", "file_path": "..."}
        try:
            ack = await asyncio.wait_for(ws.recv(), timeout=30)
        except asyncio.TimeoutError:
            error_str = "timeout waiting for file_complete ack"
        else:
            try:
                data = json.loads(ack)
            except Exception:
                error_str = f"invalid JSON ack: {ack!r}"
            else:
                if data.get("type") != "file_complete" or data.get("status") != "success":
                    error_str = f"unexpected ack: {data!r}"

        end_ts = time.perf_counter()

    except Exception as e:
        error_str = repr(e)
    finally:
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass

    ok = error_str is None
    duration = (end_ts - start_ts) if (end_ts is not None) else None
    if ok:
        print(f"[uploader_{index}] upload COMPLETE in {duration:.2f}s")
    else:
        print(f"[uploader_{index}] upload ERROR: {error_str}")

    return {
        "ok": ok,
        "error": error_str,
        "duration": duration,
    }

# ---------- main orchestration ----------

async def main_async():
    handshake_sem = asyncio.Semaphore(MAX_PARALLEL_HANDSHAKES)
    tasks = []

    for i in range(NUM_UPLOADERS):
        # slow ramp
        await asyncio.sleep(USER_START_STAGGER)
        tasks.append(run_uploader(i, handshake_sem))

    results = await asyncio.gather(*tasks)

    # summarize
    total = len(results)
    ok = sum(1 for r in results if r["ok"])
    failed = total - ok
    error_counter = Counter(r["error"] for r in results if r["error"])

    durations = [r["duration"] for r in results if r["duration"] is not None]

    print("\n========== FILE LOAD TEST SUMMARY ==========")
    print(f"Total uploads attempted:  {total}")
    print(f"Successful uploads:       {ok}")
    print(f"Failed uploads:           {failed}")
    print()
    print("Error types:")
    if not error_counter:
        print("  (none)")
    else:
        for err, count in error_counter.most_common():
            print(f"  {err}: {count}")
    print()

    if durations:
        print("Upload duration (seconds):")
        print(f"  samples: {len(durations)}")
        print(f"  min:     {min(durations):.2f}")
        print(f"  avg:     {sum(durations)/len(durations):.2f}")
        print(f"  p95:     {percentile(durations, 95):.2f}")
        print(f"  p99:     {percentile(durations, 99):.2f}")
        print(f"  max:     {max(durations):.2f}")
    else:
        print("Upload duration: no successful samples")
    print("============================================\n")

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
