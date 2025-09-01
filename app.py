# app.py
from __future__ import annotations
from dotenv import load_dotenv, find_dotenv
load_dotenv(r"D:\EcodiaOS\config\.env") or load_dotenv(find_dotenv())

import asyncio
import logging
import os
import pathlib
import traceback
from contextlib import asynccontextmanager
from typing import Any
import typer

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# --- Middleware ---
from api.middleware.timing_headers import TimingHeadersMiddleware
from api.middleware.governance import AttestationMiddleware, constitutional_preamble

# --- Core EcodiaOS Imports ---
from core.llm.bus import event_bus
from core.utils.neo.neo_driver import close_driver, init_driver
from core.utils.net_api import init_net_api, close_http_client
from systems.contra.manifest import ensure_manifest
from systems.equor.core.identity.homeostasis import HomeostasisMonitor

# --- E-Series Heartbeat Imports (Equor & Unity Autonomous Loops) ---
from systems.unity.core.workspace.global_workspace import global_workspace

# --- Immune System + Conflict/Evo wiring ---
from systems.qora.core.immune.auto_instrument import install_immune, immune_section
from systems.qora.core.immune.conflict_sdk import log_conflict
from systems.qora.core.immune.conflict_ingestor import on_conflict_detected

# --- Synapse Full Stack Initialization ---
from systems.synapse.core.meta_controller import meta_controller
from systems.synapse.core.registry import arm_registry
from systems.synapse.core.reward import reward_arbiter
from systems.synapse.critic.offpolicy import critic
from systems.synapse.daemon import run_synapse_autonomous_loops
from systems.synapse.robust.ood import ood_detector
from systems.synapse.skills.manager import skills_manager
from systems.synapse.training.bandit_state import start_background_flusher, stop_background_flusher

# --- SynK / Graph schema / Switchboard ---
from systems.synk.core.switchboard.runtime import sb
from systems.synk.core.tools.schema_bootstrap import ensure_schema

# --- Routers ---
from api.status.register import attach_status_routers
from api.endpoints.atune import atune_router
from api.endpoints.axon import axon_router
from api.endpoints.contra import contra_router
from api.endpoints.equor import equor_router
from api.endpoints.evo import evo_router
from api.endpoints.llm import llm_router
from api.endpoints.nova import nova_router
from api.endpoints.qora import qora_router
from api.endpoints.simula import simula_router
from api.endpoints.synapse import synapse_router
from api.endpoints.synk import synk_router
from api.endpoints.telemetry_smoke import dev_telemetry_router
from api.endpoints.unity import unity_router
from api.endpoints.voxis import voxis_router
from api.endpoints.meta import meta_router
from api.endpoints.bff.app_health import router as bff_app_health_router
from api.endpoints.bff.main import bff_router
from core.utils.neo.seeding import seed_initial_flags
from core.llm.embeddings_gemini import _embed_sanity_probe
from scripts.seed_soul_phrase import run_interactive_seeding

# ---- Environment Bootstrap ----
for candidate in ("D:/EcodiaOS/config/.env", ".env"):
    if pathlib.Path(candidate).exists():
        load_dotenv(candidate)
        break

APP_VERSION = os.getenv("APP_VERSION", "0.0.1")
APP_ENV = os.getenv("APP_ENV", "dev")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---- Application Lifespan (Startup & Shutdown) ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    background_tasks: list[asyncio.Task] = []
    graph_ok = True
    try:
        # --- 1. Core Infrastructure Startup ---
        print("--- STARTING LIFESPAN ---")
        try:
            await init_driver()
            await seed_initial_flags()
            await ensure_schema()
            print("✅ Step 1: Knowledge Graph Online")
        except Exception as e:
            graph_ok = False
            print(f"🌱 Knowledge Graph: OFFLINE. Reason: {e}")

        # --- IMMUNE SYSTEM: Activate global exception hooks ---
        await install_immune(
            component_resolver=lambda mod: mod.split(".")[0],
            include_packages=("systems", "core", "services", "api"),
            exclude_predicate=lambda name: name.startswith("api.middleware"),
        )
        print("🛡️ Immune System: Activated.")

        # --- 2. Synapse Cognitive Engine Initialization ---
        print("⏳ Step 2: Initializing Synapse...")
        await ensure_manifest("simula", code_root="D:/EcodiaOS")

        # (A) Initialize the registry as before
        await arm_registry.initialize()

        # (B) Load the cold-start bootstrap (safe import; no crash if missing)
        try:
            # ensures the bootstrap hook is registered
            import systems.synapse.core.registry_bootstrap  # noqa: F401
            print("[synapse] registry_bootstrap loaded.")
        except Exception as e:
            print(f"[synapse] registry_bootstrap not available (ok): {e}")

        # (C) Ensure cold-start arms exist and are aligned to Simula tools
        try:
            ensure_async = getattr(arm_registry, "ensure_cold_start_async", None)
            if callable(ensure_async):
                await ensure_async()
            else:
                ensure_sync = getattr(arm_registry, "ensure_cold_start", None)
                if callable(ensure_sync):
                    ensure_sync()
            print("✅ [synapse] Arm cold-start ensured.")
        except Exception as e:
            print(f"⚠️ [synapse] Arm cold-start skipped: {e}")

        # Remaining Synapse stack
        await _embed_sanity_probe()
        await reward_arbiter.initialize()
        await meta_controller.initialize()
        await ood_detector.initialize_distribution()
        await skills_manager.initialize()
        try:
            await critic.fit_nightly()
        except Exception as e:
            print(f"[critic] WARNING: initial fit failed: {e}")
        start_background_flusher()
        print("✅ Step 2: Synapse Core Online.")

        # --- 3. Start Synapse Autonomous Daemon ---
        print("⏳ Step 3: Starting Daemons...")
        background_tasks.append(asyncio.create_task(run_synapse_autonomous_loops()))
        # ... (other heartbeat tasks would go here)
        print("✅ Step 3: Daemons Active.")

        # --- 5. Start Event Bus Listeners ---
        try:
            if await sb.get("immune.conflict_ingestor.enabled", True):
                event_bus.subscribe("conflict_detected", on_conflict_detected)
                print("🚦 Conflict Ingestor: Online.")
        except Exception:
            event_bus.subscribe("conflict_detected", on_conflict_detected)
            print("🚦 Conflict Ingestor: Online (fallback).")

        print("\n--- EcodiaOS STARTUP COMPLETE ---\n")
        yield

    except Exception as e:
        print(f"🔥 LIFESPAN STARTUP FAILED: {e}")
        traceback.print_exc()
        raise
    finally:
        # --- 6. Graceful Shutdown ---
        print("🔌 Shutting down...")
        for task in background_tasks:
            task.cancel()
        stop_background_flusher()
        try:
            await close_http_client()
            if graph_ok:
                await close_driver()
        except Exception:
            pass
        print("🔌 EcodiaOS is offline.")

# ---- FastAPI App Instance ----
app = FastAPI(title="EcodiaOS", description="The mind of the future.", version=APP_VERSION, lifespan=lifespan)
ui_path = pathlib.Path(__file__).parent / "systems/synapse/ui/static"
if ui_path.exists():
    app.mount("/ui", StaticFiles(directory=ui_path), name="ui")

# ---- Middleware ----
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(AttestationMiddleware)
app.add_middleware(TimingHeadersMiddleware)

# ---- Routers ----
governed_dependency = Depends(constitutional_preamble)
app.include_router(simula_router, prefix="/simula", tags=["simula"], dependencies=[governed_dependency])
app.include_router(nova_router, prefix="/nova", tags=["nova"], dependencies=[governed_dependency])
app.include_router(evo_router, prefix="/evo", tags=["evo"], dependencies=[governed_dependency])
app.include_router(atune_router, prefix="/atune", tags=["atune"])
app.include_router(contra_router, prefix="/contra", tags=["contra"])
app.include_router(synk_router, prefix="/synk", tags=["synk"])
app.include_router(unity_router, prefix="/unity", tags=["unity"])
app.include_router(axon_router, prefix="/axon", tags=["axon"])
app.include_router(voxis_router, prefix="/voxis", tags=["voxis"])
app.include_router(dev_telemetry_router)
app.include_router(equor_router, prefix="/equor", tags=["equor"])
app.include_router(synapse_router, prefix="/synapse", tags=["synapse"])
app.include_router(llm_router, prefix="/llm", tags=["llm"])
app.include_router(qora_router, prefix="/qora", tags=["qora"])
app.include_router(meta_router)
attach_status_routers(app)
app.include_router(bff_app_health_router)
app.include_router(bff_router)

# --- Final Setup ---
from core.utils.net_api import LIVE_ENDPOINTS 
LIVE_ENDPOINTS.populate_from_app_routes(app.routes)

from fastapi.openapi.utils import get_openapi
try:
    get_openapi(title="EcodiaOS", version="dev", routes=app.routes)
    print("[OPENAPI] OK", flush=True)
except Exception as e:
    print(f"[OPENAPI] FAILED: {e!r}", flush=True)

try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    @app.get("/metrics", response_model=None)
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
except Exception:
    pass

cli = typer.Typer(help="EcodiaOS command-line utilities.")
@cli.command()
def seed_phrase():
    """Interactively creates a new, secure SoulPhrase for a user."""
    async def main():
        await init_driver()
        try:
            await run_interactive_seeding()
        finally:
            await close_driver()
    asyncio.run(main())

if __name__ == "__main__":
    cli()
