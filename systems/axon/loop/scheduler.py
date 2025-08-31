# systems/axon/loop/scheduler.py
from __future__ import annotations

import asyncio
import os

from systems.axon.loop.sense import SenseLoop


async def run_sense_forever(period_sec: float = 30.0) -> None:
    loop = SenseLoop()
    period = float(os.getenv("AXON_SENSE_PERIOD_SEC", str(period_sec)))
    while True:
        try:
            count = await loop.poll_once()
            if os.getenv("AXON_DEBUG", "0") == "1":
                print(f"[SenseLoop] produced={count}")
        except Exception as e:
            if os.getenv("AXON_DEBUG", "0") == "1":
                print(f"[SenseLoop] error: {e}")
        await asyncio.sleep(period)
