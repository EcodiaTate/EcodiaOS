# app.py
# FULLY UPGRADED FOR COMPLETE SYNAPSE & E-SERIES HEARTBEAT INTEGRATION
# --- CORRECTED IMMUNE SYSTEM WIRING ---
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
# highlight-start
from core.utils.net_api import init_net_api, close_http_client
# highlight-end
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
        try:
            await init_driver()
            await seed_initial_flags()
            await ensure_schema()
            print("🌱 Knowledge Graph: Online")
        except Exception as e:
            graph_ok = False
            print(f"🌱 Knowledge Graph: OFFLINE (cold start). Reason: {e}")

# highlight-start
        # Correctly initialize the network client and endpoint registry
        await init_net_api()
# highlight-end

        # --- IMMUNE SYSTEM (STEP 2): Activate global exception hooks ---
        await install_immune(
            component_resolver=lambda mod: mod.split(".")[0],
            include_packages=("systems", "core", "services", "api"),
            include_privates=False,
            exclude_predicate=lambda name: (
                name.startswith("api.middleware")
                or name.startswith("core.middleware")
                or name.endswith(".middleware.immune")
            ),
        )
        print("🛡️ Immune System: Activated. Global exception hooks will publish to the event bus.")

        # --- 2. Synapse Cognitive Engine Initialization ---
        print("🧠 Synapse: Initializing full cognitive stack...")
        await ensure_manifest("simula", code_root="D:/EcodiaOS")
        print("MANIFEST ONLINE")
        await arm_registry.initialize()
        await _embed_sanity_probe()
        await reward_arbiter.initialize()
        await meta_controller.initialize()
        await ood_detector.initialize_distribution()
        await skills_manager.initialize()
        try:
            await critic.fit_nightly()
        except Exception as e:
            print(f"[critic] WARNING: initial fit failed (continuing): {e}")
        start_background_flusher()
        print("🧠 Synapse: Core components online.")

        # --- 3. Start Synapse Autonomous Daemon ---
        print("🌀 Synapse: Starting autonomous self-improvement daemon...")
        background_tasks.append(asyncio.create_task(run_synapse_autonomous_loops()))
        print("🌀 Synapse: Daemon is active.")

        # --- 4. E-SERIES HEARTBEAT INTEGRATION ---
        print("❤️ Equor & Unity: heart is beating")
        async def run_global_workspace_cycle():
            while True:
                try:
                    await global_workspace.run_broadcast_cycle()
                except Exception as e:
                    logging.exception("[global_workspace] cycle error (continuing): %s", e)
                await asyncio.sleep(1)
        background_tasks.extend(
            [
                asyncio.create_task(run_global_workspace_cycle()),
            ]
        )
        print("❤️ E-Series: All cognitive heartbeats are online. System is live.")

        # --- 5. Start Event Bus Listeners ---
        try:
            if await sb.get("immune.conflict_ingestor.enabled", True):
                event_bus.subscribe("conflict_detected", on_conflict_detected)
                print("🚦 Conflict Ingestor: Online and listening for immune system events.")
            else:
                print("🚦 Conflict Ingestor: Disabled by switchboard gate.")
        except Exception:
            # If switchboard/graph are down, default to enabled for safety
            event_bus.subscribe("conflict_detected", on_conflict_detected)
            print("🚦 Conflict Ingestor: Online (fallback).")

        print("EcodiaOS: The Mind of the Future")
        yield

    except Exception as e:
        print(f"🔥 Lifespan startup failed: {e}")
        traceback.print_exc()
        raise
    finally:
        # --- 6. Graceful Shutdown ---
        print("🔌 Shutting down...")
        for task in background_tasks:
            task.cancel()
        stop_background_flusher()
        try:
# highlight-start
            # Gracefully close the shared HTTP client
            await close_http_client()
# highlight-end
            if graph_ok:
                await close_driver()
        except Exception:
            pass
        print("🔌 EcodiaOS is offline.")

# ---- FastAPI App Instance ----
app = FastAPI(
    title="EcodiaOS",
    description="The mind of the future.",
    version=APP_VERSION,
    lifespan=lifespan,
)

# ---- UI Static File Serving ----
ui_path = pathlib.Path(__file__).parent / "systems/synapse/ui/static"
if ui_path.exists():
    app.mount("/ui", StaticFiles(directory=ui_path), name="ui")

# ---- Middleware (order matters: first added = outermost) ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "*").split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AttestationMiddleware)
app.add_middleware(TimingHeadersMiddleware)

# ---- HTTP Immune Middleware (logs 5xx + exceptions) ----
@app.middleware("http")
async def immune_http_middleware(request: Request, call_next):
    try:
        async with immune_section():
            response: Response = await call_next(request)
        if response.status_code >= 500 and not request.url.path.startswith("/evo/escalate"):
            synthetic = RuntimeError(f"HTTP {response.status_code} on {request.url.path}")
            ctx: dict[str, Any] = {
                "route": request.url.path, "env": APP_ENV, "method": request.method,
                "query": dict(request.query_params), "status_code": response.status_code,
            }
            try:
                await log_conflict(exc=synthetic, component="http.middleware.immune", severity="high", version=APP_VERSION, context=ctx)
            except Exception:
                traceback.print_exc()
        return response
    except Exception as e:
        if request.url.path.startswith("/evo/escalate"):
            raise
        ctx = {
            "route": request.url.path, "env": APP_ENV, "method": request.method,
            "query": dict(request.query_params),
            "traceback": "".join(traceback.format_exception(type(e), e, e.__traceback__)),
        }
        try:
            await log_conflict(exc=e, component="http.middleware.immune", severity="high", version=APP_VERSION, context=ctx)
        except Exception:
            traceback.print_exc()
        raise

# ---- Routers ----
governed_dependency = Depends(constitutional_preamble)
app.include_router(simula_router, prefix="/simula", tags=["simula"], dependencies=[governed_dependency])
app.include_router(nova_router,   prefix="/nova",   tags=["nova"],   dependencies=[governed_dependency])
app.include_router(evo_router,    prefix="/evo",    tags=["evo"],    dependencies=[governed_dependency])

# All other routers
app.include_router(atune_router,   prefix="/atune",   tags=["atune"] )
app.include_router(contra_router,  prefix="/contra",  tags=["contra"])
app.include_router(synk_router,    prefix="/synk",    tags=["synk"]  )
app.include_router(unity_router,   prefix="/unity",   tags=["unity"] )
app.include_router(axon_router,    prefix="/axon",    tags=["axon"]  )
app.include_router(voxis_router,   prefix="/voxis",   tags=["voxis"] )
app.include_router(dev_telemetry_router)
app.include_router(equor_router,   prefix="/equor",   tags=["equor"] )
app.include_router(synapse_router, prefix="/synapse", tags=["synapse"])
app.include_router(llm_router,     prefix="/llm",     tags=["llm"]   )
app.include_router(qora_router,    prefix="/qora",    tags=["qora"]  )
app.include_router(meta_router)
attach_status_routers(app)
app.include_router(bff_app_health_router)
app.include_router(bff_router)

from scripts.log_middleware import LogBodiesOnError
app.add_middleware(LogBodiesOnError)

from fastapi.openapi.utils import get_openapi
try:
    get_openapi(title="EcodiaOS", version="dev", routes=app.routes)
    print("[OPENAPI] OK", flush=True)
except Exception as e:
    print(f"[OPENAPI] FAILED: {e!r}", flush=True)
    raise

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
    @app.get("/metrics")
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
except Exception:
    pass

cli = typer.Typer(help="EcodiaOS command-line utilities.")

@cli.command()
def seed_phrase():
    """Interactively creates a new, secure SoulPhrase for a user."""
    async def main():
        print("Connecting to database...")
        await init_driver()
        try:
            await run_interactive_seeding()
        finally:
            print("Closing database connection...")
            await close_driver()
    asyncio.run(main())

if __name__ == "__main__":
    cli()