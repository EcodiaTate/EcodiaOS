from __future__ import annotations

# --- dotenv early load ---
from dotenv import find_dotenv, load_dotenv

load_dotenv(r"D:\EcodiaOS\config\.env") or load_dotenv(find_dotenv())

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

import typer
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

import systems.simula.nscs.agent_tools
from api.endpoints.app_health import health_router
from api.endpoints.atune import atune_router
from api.endpoints.axon import axon_router
from api.endpoints.bff.app_health import router as bff_app_health_router
from api.endpoints.bff.main import bff_router
from api.endpoints.contra import contra_router
from api.endpoints.equor import equor_router
from api.endpoints.evo import evo_router
from api.endpoints.llm import llm_router
from api.endpoints.meta import meta_router
from api.endpoints.nova import nova_router
from api.endpoints.qora import qora_router
from api.endpoints.simula import simula_router
from api.endpoints.synapse import synapse_router
from api.endpoints.synk import synk_router
from api.endpoints.unity import unity_router
from api.endpoints.voxis import voxis_router
from api.middleware.governance import AttestationMiddleware, constitutional_preamble

# --- Middleware ---
from api.middleware.timing_headers import TimingHeadersMiddleware
from api.middleware.ttl_gate import TTLMiddleware

# --- Routers ---
from api.status.register import attach_status_routers

# --- State File for Circular Import Prevention ---
from app_state import BOOTSTRAP_EVENT

# --- Core EcodiaOS Imports ---
from core.llm.bus import event_bus
from core.utils.neo.neo_driver import close_driver, init_driver
from core.utils.neo.seeding import seed_initial_flags
from core.utils.net_api import LIVE_ENDPOINTS, close_http_client, init_net_api
from scripts.seed_soul_node import seed_or_restore_soulnode
from systems.axon.dependencies import get_driver_registry
from systems.axon.loop.scheduler import run_sense_forever
from systems.qora.core.immune.conflict_ingestor import on_conflict_detected  # noqa: F401
from systems.simula.learning.daemon import DaemonConfig, SimulaDaemon
from systems.simula.runtime.ingestor import synchronize_simula_tool_catalog

# --- Synapse Full Stack ---
from systems.synapse.core.meta_controller import meta_controller
from systems.synapse.core.registry import arm_registry
from systems.synapse.core.registry_bootstrap import ensure_minimum_arms
from systems.synapse.core.reward import reward_arbiter
from systems.synapse.daemon import run_synapse_autonomous_loops
from systems.synapse.robust.ood import ood_detector
from systems.synapse.skills.manager import skills_manager
from systems.synapse.training.bandit_state import start_background_flusher, stop_background_flusher

# --- Other System Imports ---
from systems.synk.core.tools.schema_bootstrap import ensure_schema
from systems.voxis.core.result_store import get_result_store  # noqa: F401

# --- Tool Catalog Sync ---
from systems.voxis.runtime.ingestor import (
    synchronize_tool_catalog as synchronize_voxis_tool_catalog,
)

# app.py — add at top near other env reads
SKIP_ENSURE = os.getenv("ECODIA_SKIP_ENSURE", "0").lower() in ("1", "true", "yes")
# --- Silence asyncio slow-task spam ---
import asyncio as _asyncio
import logging as _logging


def _silence_asyncio_debug() -> None:
    try:
        loop = _asyncio.get_running_loop()
    except RuntimeError:
        loop = _asyncio.new_event_loop()
        _asyncio.set_event_loop(loop)

    # Hard-off: disable asyncio debug so it won't emit the slow-task warnings
    try:
        loop.set_debug(False)
    except Exception:
        pass

    # Belt-and-braces: filter the specific warning text in case some lib flips debug back on
    class _HideAsyncioSlow(_logging.Filter):
        def filter(self, rec: _logging.LogRecord) -> bool:
            msg = rec.getMessage()
            return "Executing <Task pending" not in msg

    _logging.getLogger("asyncio").addFilter(_HideAsyncioSlow())


# call immediately so it’s in effect before anything schedules tasks
_silence_asyncio_debug()

# ---- Basic Setup ----
APP_VERSION = os.getenv("APP_VERSION", "0.0.1")
DEFER_BOOTSTRAP = os.getenv("DEFER_BOOTSTRAP", "1").lower() not in ("0", "false", "off")
AXON_RSS_ENABLED = os.getenv("AXON_RSS_ENABLED", "1").lower() not in ("0", "false", "off")
AXON_SENSE_PERIOD_SEC = float(os.getenv("AXON_SENSE_PERIOD_SEC", "30"))

# +++ FIX: New environment variable for development optimization +++
DEV_FOCUS_MODE = os.getenv("DEV_FOCUS_MODE")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _tick(label: str, start: float | None = None) -> float:
    now = time.monotonic()
    if start is not None:
        logger.info("[Bootstrap] %s took %.3fs", label, now - start)
    return now


# app.py — _bootstrap_heavy()
async def _bootstrap_heavy(app: FastAPI) -> None:
    logger.info("[Bootstrap] Starting heavy tasks...")
    try:
        t_total = _tick("start")

        # 1) Schema + flags (SKIPPABLE)
        t = _tick("start")
        if SKIP_ENSURE:
            logger.warning(
                "[Bootstrap] SKIPPING ensure_schema() and seed_initial_flags() (ECODIA_SKIP_ENSURE=1).",
            )
        else:
            await ensure_schema()
            await seed_initial_flags()
            _tick("ensure schema + seed flags", t)

        # 2) Ensure arms (SKIPPABLE)
        t = _tick("start")
        if SKIP_ENSURE:
            logger.warning("[Bootstrap] SKIPPING ensure_minimum_arms() (ECODIA_SKIP_ENSURE=1).")
        else:
            await ensure_minimum_arms()
            _tick("ensure_minimum_arms", t)

        # 3) Hydrate in-memory registry (REQUIRED)
        t = _tick("start")
        await arm_registry.initialize()
        _tick("arm registry initialization", t)

        try:
            modes = arm_registry.list_modes()
            counts = {m: len(arm_registry.get_arms_for_mode(m)) for m in modes}
            logger.info("[ArmRegistry] Hydrated modes: %s", counts)
        except Exception:
            pass

        # 3b) Tool catalogs (lightweight; safe to keep)
        try:
            await synchronize_simula_tool_catalog()
        except Exception as e:
            logger.error(f"Startup tool sync error (non-fatal): {e}", exc_info=True)

        # 4) AXON & tool catalogs (optional)
        t = _tick("start")
        await asyncio.to_thread(get_driver_registry)
        await synchronize_voxis_tool_catalog()
        await synchronize_simula_tool_catalog()
        _tick("driver registry + tool catalog sync", t)

        # 5) Synapse subsystems (REQUIRED for runtime)
        t = _tick("start")
        await reward_arbiter.initialize()
        await meta_controller.initialize()
        await ood_detector.initialize_distribution()
        await skills_manager.initialize()

        loop = asyncio.get_running_loop()
        start_background_flusher(loop=loop)
        _tick("synapse subsystems + bandit flusher", t)

        # 6) Daemons (optional)
        t = _tick("start")
        if os.getenv("DISABLE_BACKGROUND_LOOPS", "0").lower() in ("1", "true", "yes"):
            logger.warning("[Synapse Daemon] Background loops disabled.")
        else:
            asyncio.create_task(run_synapse_autonomous_loops())
            if AXON_RSS_ENABLED:
                asyncio.create_task(run_sense_forever(AXON_SENSE_PERIOD_SEC))
        _tick("spawn daemons", t)

        # Signal ready
        BOOTSTRAP_EVENT.set()
        _tick("total bootstrap time", t_total)
        logger.info("[Bootstrap] Completed; service is READY.")

    except Exception as e:
        logger.exception("[Bootstrap] FAILED during heavy tasks: %r", e)
        BOOTSTRAP_EVENT.set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- early Windows policy (best-effort, prior to spawning tasks) ---
    if os.name == "nt":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            # Non-fatal: keep default policy if unavailable
            logger.debug("WindowsProactorEventLoopPolicy not applied.", exc_info=True)

    # --- loop + debug info ---
    loop = asyncio.get_running_loop()
    logger.info("asyncio debug? %s", getattr(loop, "get_debug", lambda: False)())

    print("--- STARTING ECODIAOS LIFESPAN ---")

    # --- EventBus: start with a short timeout so we don't hang on boot ---
    try:
        await asyncio.wait_for(event_bus.start(), timeout=5.0)
        logger.info("[LIFESPAN] EventBus listener started.")
    except TimeoutError:
        logger.warning("[LIFESPAN] EventBus start timed out (continuing).")
    except Exception:
        logger.warning("[LIFESPAN] EventBus failed to start (continuing).", exc_info=True)

    # --- Start Simula daemon early (so it can process advice during boot) ---
    daemon = SimulaDaemon(DaemonConfig())
    app.state.simula_daemon = None
    try:
        await daemon.start()
        app.state.simula_daemon = daemon
        logger.info("[LIFESPAN] SimulaDaemon started.")
    except Exception:
        logger.error("[LIFESPAN] SimulaDaemon failed to start.", exc_info=True)

    # --- Core deps (HTTP client, DB, route map) ---
    try:
        await init_driver()
        await init_net_api()
        LIVE_ENDPOINTS.populate_from_app_routes(app.routes)
        logger.info("[Startup] Core dependencies initialized.")
    except Exception:
        logger.error("[Startup] Core dependency initialization failed.", exc_info=True)

    # --- Defer heavy bootstrap to background task; keep a handle for clean shutdown ---
    app.state.bootstrap_task = loop.create_task(_bootstrap_heavy(app))
    logger.info("[Startup] Deferred heavy bootstrap to background task.")

    try:
        # Hand control back to FastAPI
        yield
    finally:
        # --- cancel/bootstrap cleanup ---
        bt = getattr(app.state, "bootstrap_task", None)
        if bt and not bt.done():
            bt.cancel()
            try:
                await bt
            except asyncio.CancelledError:
                logger.info("[LIFESPAN] Bootstrap task cancelled.")

        # --- Stop Simula daemon if it started ---
        try:
            d = getattr(app.state, "simula_daemon", None)
            if d is not None:
                await d.stop()
                logger.info("[LIFESPAN] SimulaDaemon stopped.")
        except Exception:
            logger.warning("[LIFESPAN] SimulaDaemon stop raised.", exc_info=True)

        print("\n🔌 Shutting down EcodiaOS…")

        # --- flushers / clients / drivers ---
        try:
            stop_background_flusher()
        except Exception:
            logger.warning("Background flusher stop raised.", exc_info=True)

        try:
            await close_http_client()
        except Exception:
            logger.warning("close_http_client raised.", exc_info=True)

        try:
            await close_driver()
        except Exception:
            logger.warning("close_driver raised.", exc_info=True)

        # --- EventBus shutdown last, after subscribers had a chance to flush ---
        try:
            await event_bus.shutdown()
            logger.info("[LIFESPAN] EventBus shut down.")
        except Exception:
            logger.warning("[LIFESPAN] EventBus shutdown raised.", exc_info=True)

        print("🔌 EcodiaOS is offline.")


app = FastAPI(title="EcodiaOS", version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AttestationMiddleware)
app.add_middleware(TTLMiddleware)
app.add_middleware(TimingHeadersMiddleware)


@app.get("/health", tags=["system"])
def health():
    return {"ok": True, "version": APP_VERSION}


@app.get("/ready", tags=["system"])
def ready():
    return {"ready": BOOTSTRAP_EVENT.is_set()}


governed_dependency = Depends(constitutional_preamble)
app.include_router(
    simula_router,
    prefix="/simula",
    tags=["simula"],
    dependencies=[governed_dependency],
)
app.include_router(nova_router, prefix="/nova", tags=["nova"], dependencies=[governed_dependency])
app.include_router(evo_router, prefix="/evo", tags=["evo"], dependencies=[governed_dependency])
app.include_router(atune_router, prefix="/atune", tags=["atune"])
app.include_router(contra_router, prefix="/contra", tags=["contra"])
app.include_router(synk_router, prefix="/synk", tags=["synk"])
app.include_router(unity_router, prefix="/unity", tags=["unity"])
app.include_router(axon_router, prefix="/axon", tags=["axon"])
app.include_router(voxis_router, prefix="/voxis", tags=["voxis"])
app.include_router(equor_router, prefix="/equor", tags=["equor"])
app.include_router(synapse_router, prefix="/synapse", tags=["synapse"])
app.include_router(llm_router, prefix="/llm", tags=["llm"])
app.include_router(qora_router, prefix="/qora", tags=["qora"])
app.include_router(meta_router)
app.include_router(health_router)
attach_status_routers(app)
app.include_router(bff_app_health_router)
app.include_router(bff_router)

cli = typer.Typer(help="EcodiaOS command-line utilities.")


@cli.command()
def seed_soul():
    """Interactively creates a new, secure SoulNode for a user."""

    async def main():
        await init_driver()
        try:
            await seed_or_restore_soulnode()
        finally:
            await close_driver()

    asyncio.run(main())


if __name__ == "__main__":
    cli()
