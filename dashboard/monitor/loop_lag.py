# dashboard/monitor/loop_lag.py
import asyncio, time, logging
log = logging.getLogger(__name__)

def start_loop_lag_monitor(threshold_ms=50):
    async def monitor():
        while True:
            start = time.perf_counter()
            await asyncio.sleep(0.05)
            lag_ms = (time.perf_counter() - start - 0.05) * 1000
            if lag_ms > threshold_ms:
                log.warning("Event loop lag %.1f ms", lag_ms)
    asyncio.get_running_loop().create_task(monitor())
