# systems/simula/daemon.py
from __future__ import annotations

import asyncio
import logging
import os
import signal
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Optional

from systems.simula.learning.advice_engine import AdviceEngine

log = logging.getLogger(__name__)


@dataclass
class DaemonConfig:
    # Intervals (seconds)
    t2_synth_interval_s: float = float(os.getenv("SIM_DAEMON_T2_SYNTH_INTERVAL_S", "1.0"))
    t3_merge_interval_s: float = float(os.getenv("SIM_DAEMON_T3_MERGE_INTERVAL_S", "1.0"))
    decay_interval_s: float = float(os.getenv("SIM_DAEMON_DECAY_INTERVAL_S", "3600"))  # hourly
    validate_interval_s: float = float(os.getenv("SIM_DAEMON_VALIDATE_INTERVAL_S", "900"))  # 15 min

    # Concurrency limits
    t2_parallel: int = int(os.getenv("SIM_DAEMON_T2_PARALLEL", "2"))
    t3_parallel: int = int(os.getenv("SIM_DAEMON_T3_PARALLEL", "1"))

    # Backpressure
    queue_maxsize: int = int(os.getenv("SIM_DAEMON_QUEUE_MAXSIZE", "1000"))

    # Optional: auto-harvest recent L1 items from Neo (disabled by default)
    auto_harvest_t1: bool = os.getenv("SIM_DAEMON_AUTO_HARVEST_T1", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    harvest_interval_s: float = float(os.getenv("SIM_DAEMON_HARVEST_INTERVAL_S", "120"))
    harvest_window_minutes: int = int(os.getenv("SIM_DAEMON_HARVEST_WINDOW_MIN", "10"))


class SimulaDaemon:
    """
    Async daemon that:
      - Consumes T1 IDs and synthesizes T2
      - Consumes T2 IDs and merges into T3
      - Periodically runs weight decay
      - Periodically runs advice validation (stub you can wire to repo checks)
      - (Optional) auto-harvests fresh T1 Advice nodes to seed T2 synthesis
    """

    def __init__(self, cfg: DaemonConfig | None = None):
        self.cfg = cfg or DaemonConfig()
        self.engine = AdviceEngine()

        # Work queues
        self._t1_to_t2: asyncio.Queue[str] = asyncio.Queue(maxsize=self.cfg.queue_maxsize)
        self._t2_to_t3: asyncio.Queue[str] = asyncio.Queue(maxsize=self.cfg.queue_maxsize)

        # Task handles
        self._tasks: list[asyncio.Task] = []
        self._stopping = asyncio.Event()

    # ----------------------- public API -----------------------

    async def start(self) -> None:
        """
        Launch background tasks. Idempotent if called once.
        """
        log.info("[SimulaDaemon] starting...")
        self._stopping.clear()

        # Consumers
        self._tasks.append(asyncio.create_task(self._t2_synth_loop(), name="sim-daemon:t2-synth"))
        self._tasks.append(asyncio.create_task(self._t3_merge_loop(), name="sim-daemon:t3-merge"))

        # Periodics
        self._tasks.append(asyncio.create_task(self._decay_periodic(), name="sim-daemon:decay"))
        self._tasks.append(
            asyncio.create_task(self._validate_periodic(), name="sim-daemon:validate"),
        )

        # Optional harvester
        if self.cfg.auto_harvest_t1:
            self._tasks.append(
                asyncio.create_task(self._harvest_periodic(), name="sim-daemon:harvest"),
            )

        # Graceful shutdown on SIGTERM/SIGINT (if running as a process)
        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, self._stopping.set)
        except NotImplementedError:
            # Signals may be unavailable on Windows or within some containers
            pass

        log.info("[SimulaDaemon] started with %d tasks", len(self._tasks))

    async def stop(self) -> None:
        """
        Signal tasks to stop, drain gracefully, and cancel lingering tasks.
        """
        log.info("[SimulaDaemon] stopping...")
        self._stopping.set()

        # Wake up sleepers by putting sentinels if queues are empty
        for _ in range(self.cfg.t2_parallel):
            await self._t1_to_t2.put("__STOP__")
        for _ in range(self.cfg.t3_parallel):
            await self._t2_to_t3.put("__STOP__")

        # Wait a bit for natural completion
        try:
            await asyncio.wait_for(asyncio.gather(*self._tasks, return_exceptions=True), timeout=10)
        except TimeoutError:
            log.warning("[SimulaDaemon] force-cancelling lingering tasks...")
            for t in self._tasks:
                t.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)

        await self._tasks.clear()
        log.info("[SimulaDaemon] stopped.")

    # Allow producers to enqueue work
    async def enqueue_t1(self, *advice_ids: str) -> int:
        count = 0
        for aid in advice_ids:
            await self._t1_to_t2.put(aid)
            count += 1
        return count

    async def enqueue_t2(self, *advice_ids: str) -> int:
        count = 0
        for aid in advice_ids:
            await self._t2_to_t3.put(aid)
            count += 1
        return count

    # Convenience for bulk ingestion from iterables
    async def enqueue_many_t1(self, ids: Iterable[str]) -> int:
        c = 0
        for i in ids:
            await self._t1_to_t2.put(i)
            c += 1
        return c

    async def enqueue_many_t2(self, ids: Iterable[str]) -> int:
        c = 0
        for i in ids:
            await self._t2_to_t3.put(i)
            c += 1
        return c

    # ----------------------- loops -----------------------

    async def _t2_synth_loop(self) -> None:
        """
        Consume T1 advice IDs and synthesize T2 documents.
        """
        log.info("[SimulaDaemon] T2 synth loop running (parallel=%d)", self.cfg.t2_parallel)

        sem = asyncio.Semaphore(self.cfg.t2_parallel)

        async def worker(aid: str):
            async with sem:
                try:
                    if aid == "__STOP__":
                        return
                    t2 = await self.engine.synthesize_t2(aid)
                    if t2:
                        # Immediately enqueue for T3 merge consideration
                        await self._t2_to_t3.put(t2)
                        log.info("[Daemon] T2 synthesized %s from T1 seed %s", t2, aid)
                except Exception as e:
                    log.exception("[Daemon] synth_t2 failed for %s: %r", aid, e)

        while not self._stopping.is_set():
            try:
                aid = await asyncio.wait_for(
                    self._t1_to_t2.get(),
                    timeout=self.cfg.t2_synth_interval_s,
                )
            except TimeoutError:
                continue
            # schedule but don't block the loop
            asyncio.create_task(worker(aid))

        log.info("[SimulaDaemon] T2 synth loop exiting")

    async def _t3_merge_loop(self) -> None:
        """
        Consume T2 advice IDs and attempt T3 merges.
        """
        log.info("[SimulaDaemon] T3 merge loop running (parallel=%d)", self.cfg.t3_parallel)

        sem = asyncio.Semaphore(self.cfg.t3_parallel)

        async def worker(aid: str):
            async with sem:
                try:
                    if aid == "__STOP__":
                        return
                    t3 = await self.engine.merge_t2_to_t3(aid)
                    if t3:
                        log.info("[Daemon] T3 merged %s from T2 seed %s", t3, aid)
                except Exception as e:
                    log.exception("[Daemon] merge_t2_to_t3 failed for %s: %r", aid, e)

        while not self._stopping.is_set():
            try:
                aid = await asyncio.wait_for(
                    self._t2_to_t3.get(),
                    timeout=self.cfg.t3_merge_interval_s,
                )
            except TimeoutError:
                continue
            asyncio.create_task(worker(aid))

        log.info("[SimulaDaemon] T3 merge loop exiting")

    async def _decay_periodic(self) -> None:
        """
        Periodically apply time-decay to advice weights.
        """
        log.info(
            "[SimulaDaemon] Decay periodic loop running (every %.1fs)",
            self.cfg.decay_interval_s,
        )
        while not self._stopping.is_set():
            try:
                await self.engine.decay()
                log.debug("[Daemon] Decay pass complete")
            except Exception as e:
                log.exception("[Daemon] Decay failed: %r", e)
            await asyncio.wait({self._stopping.wait()}, timeout=self.cfg.decay_interval_s)
        log.info("[SimulaDaemon] Decay loop exiting")

    async def _validate_periodic(self) -> None:
        """
        Periodically trigger validation of advice (stubbed job).
        Replace with repo-specific AST/pytest/integration checks.
        """
        log.info(
            "[SimulaDaemon] Validate periodic loop running (every %.1fs)",
            self.cfg.validate_interval_s,
        )
        while not self._stopping.is_set():
            try:
                # hook your validate job here (currently a stub)
                log.debug("[Daemon] Validate pass (stub)")
            except Exception as e:
                log.exception("[Daemon] Validate failed: %r", e)
            await asyncio.wait({self._stopping.wait()}, timeout=self.cfg.validate_interval_s)
        log.info("[SimulaDaemon] Validate loop exiting")

    async def _harvest_periodic(self) -> None:
        """
        (Optional) Periodically harvest recent L1 advice to seed T2 synthesis automatically.
        Requires the Neo4j vector index + Advice nodes being created by ingest_error().
        """
        from core.utils.neo.cypher_query import cypher_query

        log.info(
            "[SimulaDaemon] Harvest periodic loop running (every %.1fs)",
            self.cfg.harvest_interval_s,
        )
        while not self._stopping.is_set():
            try:
                rows = await cypher_query(
                    """
                    MATCH (a:Advice {level:1})
                    WHERE a.created_at IS NULL OR
                          (datetime().epochMillis - coalesce(a.last_seen, timestamp())) < $window_ms
                    RETURN a.id AS id
                    ORDER BY coalesce(a.last_seen, timestamp()) DESC
                    LIMIT 100
                    """,
                    {"window_ms": self.cfg.harvest_window_minutes * 60_000},
                )
                ids = [r["id"] for r in (rows or [])]
                if ids:
                    enq = await self.enqueue_many_t1(ids)
                    log.info("[Daemon] Harvested %d new T1 items (enqueued=%d)", len(ids), enq)
            except Exception as e:
                log.exception("[Daemon] Harvest failed: %r", e)

            await asyncio.wait({self._stopping.wait()}, timeout=self.cfg.harvest_interval_s)

        log.info("[SimulaDaemon] Harvest loop exiting")
