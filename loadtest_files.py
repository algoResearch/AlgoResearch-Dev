<<<<<<< HEAD
=======
import asyncio
>>>>>>> a8bb6d6b8d504d7d3bcdc8d880498c3fbb4ec232
import os
import json
import time
import math
<<<<<<< HEAD
import random
from collections import Counter

import websockets
import asyncio

BASE_WS = "ws://127.0.0.1:8000"
WS_FILE_PATH = "/ws/upload/"   # <-- matches your routing.py
LOADTEST_SECRET = os.environ.get("LOADTEST_SECRET", "super-secret-loadtest-key")

# --------- config ---------
NUM_UPLOADERS = 50
FILE_SIZE_BYTES = 5 * 1024 * 1024   # 5MB
CHUNK_SIZE = 64 * 1024              # 64KB
MAX_PARALLEL_HANDSHAKES = 20
USER_START_STAGGER = 0.02
ACK_TIMEOUT = 30

DEBUG_FRAMES = False

=======
from collections import Counter

import websockets

BASE_WS = "ws://127.0.0.1:8000"
WS_FILE_PATH = "/ws/upload/"

# --------- config ---------
NUM_UPLOADERS = 25                 # how many concurrent uploaders
FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB per upload
CHUNK_SIZE = 64 * 1024             # 64KB per WS binary frame
MAX_PARALLEL_HANDSHAKES = 20
USER_START_STAGGER = 0.02          # seconds


# ---------- helpers ----------
>>>>>>> a8bb6d6b8d504d7d3bcdc8d880498c3fbb4ec232

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


<<<<<<< HEAD
async def run_uploader(index: int, handshake_sem: asyncio.Semaphore):
    username = f"lt_user_{index}"

    ws_url = (
        f"{BASE_WS}{WS_FILE_PATH}"
        f"?lt_user={username}&lt_secret={LOADTEST_SECRET}"
    )
    filename = f"lt_upload_{index}.bin"
    upload_client_id = f"{username}-{int(time.time()*1000)}"

    print(f"[uploader_{index}] connecting to {ws_url} (file={filename})")

    ws = None
    error_str = None
    handshake_ms = None
    duration_s = None
    bytes_sent = 0

    # pre-generate bytes
    payload_bytes = os.urandom(FILE_SIZE_BYTES)

    try:
        # handshake timing (throttled)
        async with handshake_sem:
            hs_start = time.perf_counter()
            ws = await websockets.connect(ws_url, open_timeout=ACK_TIMEOUT)
            handshake_ms = (time.perf_counter() - hs_start) * 1000.0

        # 1) file_metadata
        meta_frame = {
            "type": "file_metadata",
            "metadata": {
                "filename": filename,
                "size": FILE_SIZE_BYTES,
            },
            "upload_client_id": upload_client_id,
        }
        await ws.send(json.dumps(meta_frame))

        # 2) wait for metadata ack
        try:
            ack = await asyncio.wait_for(ws.recv(), timeout=ACK_TIMEOUT)
        except asyncio.TimeoutError:
            raise RuntimeError("timeout waiting for file_metadata_ack")
        else:
            data = json.loads(ack)
            if DEBUG_FRAMES:
                print(f"[uploader_{index}] metadata ack: {data!r}")
            if data.get("type") != "file_metadata_ack" or data.get("status") != "ok":
                raise RuntimeError(f"unexpected metadata ack: {data!r}")

        # 3) send chunks
        up_start = time.perf_counter()
        offset = 0
        while offset < FILE_SIZE_BYTES:
            chunk = payload_bytes[offset: offset + CHUNK_SIZE]
            await ws.send(chunk)
            offset += len(chunk)
            bytes_sent += len(chunk)

        # 4) file_complete
        await ws.send(json.dumps({"type": "file_complete"}))

        # 5) wait for complete ack
        try:
            ack2 = await asyncio.wait_for(ws.recv(), timeout=ACK_TIMEOUT)
        except asyncio.TimeoutError:
            raise RuntimeError("timeout waiting for file_complete ack")
        else:
            data2 = json.loads(ack2)
            if DEBUG_FRAMES:
                print(f"[uploader_{index}] complete ack: {data2!r}")
            if data2.get("type") != "file_complete" or data2.get("status") != "success":
                raise RuntimeError(f"unexpected complete ack: {data2!r}")

        duration_s = time.perf_counter() - up_start

    except Exception as e:
        error_str = repr(e)
=======
# ---------- per-uploader task ----------

async def run_uploader(index: int, handshake_sem: asyncio.Semaphore, retries: int = 3):
    """
    Single uploader:
      - open ws (with handshake retries)
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

    # --- handshake with retries ---
    for attempt in range(1, retries + 1):
        try:
            async with handshake_sem:
                ws = await websockets.connect(
                    ws_url,
                    open_timeout=30,
                )
            # success: break out of retry loop
            break
        except Exception as e:
            if attempt == retries:
                error_str = f"handshake failed after {retries} attempts: {e!r}"
                print(f"[uploader_{index}] upload ERROR: {error_str}")
                return {
                    "ok": False,
                    "error": error_str,
                    "duration": None,
                }
            # backoff before next attempt
            await asyncio.sleep(0.5 * attempt)

    # --- main send/recv path ---
    try:
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

>>>>>>> a8bb6d6b8d504d7d3bcdc8d880498c3fbb4ec232
    finally:
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass

    ok = error_str is None
<<<<<<< HEAD
    if ok:
        mb = bytes_sent / (1024 * 1024)
        rate = mb / duration_s if duration_s else 0
        print(f"[uploader_{index}] upload COMPLETE in {duration_s:.2f}s ({rate:.2f} MB/s)")
=======
    duration = (end_ts - start_ts) if (end_ts is not None) else None

    if ok:
        print(f"[uploader_{index}] upload COMPLETE in {duration:.2f}s")
>>>>>>> a8bb6d6b8d504d7d3bcdc8d880498c3fbb4ec232
    else:
        print(f"[uploader_{index}] upload ERROR: {error_str}")

    return {
        "ok": ok,
        "error": error_str,
<<<<<<< HEAD
        "duration": duration_s,
        "handshake_ms": handshake_ms,
        "bytes_sent": bytes_sent,
    }


=======
        "duration": duration,
    }


# ---------- main orchestration ----------

>>>>>>> a8bb6d6b8d504d7d3bcdc8d880498c3fbb4ec232
async def main_async():
    handshake_sem = asyncio.Semaphore(MAX_PARALLEL_HANDSHAKES)
    tasks = []

    for i in range(NUM_UPLOADERS):
<<<<<<< HEAD
=======
        # slow ramp
>>>>>>> a8bb6d6b8d504d7d3bcdc8d880498c3fbb4ec232
        await asyncio.sleep(USER_START_STAGGER)
        tasks.append(run_uploader(i, handshake_sem))

    results = await asyncio.gather(*tasks)

<<<<<<< HEAD
=======
    # summarize
>>>>>>> a8bb6d6b8d504d7d3bcdc8d880498c3fbb4ec232
    total = len(results)
    ok = sum(1 for r in results if r["ok"])
    failed = total - ok
    error_counter = Counter(r["error"] for r in results if r["error"])

    durations = [r["duration"] for r in results if r["duration"] is not None]
<<<<<<< HEAD
    handshakes = [r["handshake_ms"] for r in results if r["handshake_ms"] is not None]
    throughputs = [
        (r["bytes_sent"] / (1024 * 1024)) / r["duration"]
        for r in results
        if r["duration"]
    ]
=======
>>>>>>> a8bb6d6b8d504d7d3bcdc8d880498c3fbb4ec232

    print("\n========== FILE LOAD TEST SUMMARY ==========")
    print(f"Total uploads attempted:  {total}")
    print(f"Successful uploads:       {ok}")
    print(f"Failed uploads:           {failed}")
    print()
<<<<<<< HEAD

=======
>>>>>>> a8bb6d6b8d504d7d3bcdc8d880498c3fbb4ec232
    print("Error types:")
    if not error_counter:
        print("  (none)")
    else:
        for err, count in error_counter.most_common():
            print(f"  {err}: {count}")
    print()

<<<<<<< HEAD
    if handshakes:
        print("Handshake latency (ms):")
        print(f"  samples: {len(handshakes)}")
        print(f"  min:     {min(handshakes):.2f}")
        print(f"  avg:     {sum(handshakes)/len(handshakes):.2f}")
        print(f"  p95:     {percentile(handshakes, 95):.2f}")
        print(f"  p99:     {percentile(handshakes, 99):.2f}")
        print(f"  max:     {max(handshakes):.2f}")
        print()

=======
>>>>>>> a8bb6d6b8d504d7d3bcdc8d880498c3fbb4ec232
    if durations:
        print("Upload duration (seconds):")
        print(f"  samples: {len(durations)}")
        print(f"  min:     {min(durations):.2f}")
        print(f"  avg:     {sum(durations)/len(durations):.2f}")
        print(f"  p95:     {percentile(durations, 95):.2f}")
        print(f"  p99:     {percentile(durations, 99):.2f}")
        print(f"  max:     {max(durations):.2f}")
<<<<<<< HEAD
        print()

    if throughputs:
        print("Throughput (MB/s):")
        print(f"  samples: {len(throughputs)}")
        print(f"  min:     {min(throughputs):.2f}")
        print(f"  avg:     {sum(throughputs)/len(throughputs):.2f}")
        print(f"  p95:     {percentile(throughputs, 95):.2f}")
        print(f"  p99:     {percentile(throughputs, 99):.2f}")
        print(f"  max:     {max(throughputs):.2f}")
    else:
        print("Throughput: no successful samples")

=======
    else:
        print("Upload duration: no successful samples")
>>>>>>> a8bb6d6b8d504d7d3bcdc8d880498c3fbb4ec232
    print("============================================\n")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
<<<<<<< HEAD
    main()
=======
    main()
>>>>>>> a8bb6d6b8d504d7d3bcdc8d880498c3fbb4ec232
