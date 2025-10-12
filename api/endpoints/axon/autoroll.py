# api/endpoints/axon/autoroll.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

# highlight-start
from systems.axon.dependencies import (
    get_driver_registry,
    get_journal,
    get_lifecycle_manager,
    get_scorecard_manager,
)
from systems.axon.journal.mej import MerkleJournal
from systems.axon.mesh.autoroller import AutoRoller
from systems.axon.mesh.lifecycle import DriverLifecycleManager

# highlight-end
from systems.axon.mesh.registry import DriverRegistry
from systems.axon.mesh.scorecard import ScorecardManager


class AutorollConfig(BaseModel):
    """
    Accepts arbitrary key-value pairs for updating the autoroller configuration.
    This provides basic validation that the request body is a valid JSON object.
    """

    class Config:
        extra = "allow"


class RunAutorollRequest(BaseModel):
    """Defines the optional list of capabilities for an autoroll run."""

    capabilities: list[str] | None = None


autoroll_router = APIRouter()
ROLLER = AutoRoller()


@autoroll_router.get("/config")
async def get_config() -> dict[str, Any]:
    return ROLLER.cfg.__dict__


@autoroll_router.post("/config")
async def set_config(
    cfg: AutorollConfig,
) -> dict[str, Any]:
    for k, v in cfg.model_dump().items():
        if hasattr(ROLLER.cfg, k):
            setattr(ROLLER.cfg, k, v)
    return ROLLER.cfg.__dict__


@autoroll_router.post("/run")
async def run_autoroll(
    request: RunAutorollRequest,
    journal: MerkleJournal = Depends(get_journal),
    driver_registry: DriverRegistry = Depends(get_driver_registry),
    scorecards: ScorecardManager = Depends(get_scorecard_manager),
    # highlight-start
    lifecycle: DriverLifecycleManager = Depends(get_lifecycle_manager),
    # highlight-end
) -> dict[str, Any]:
    caps = request.capabilities or driver_registry.list_capabilities()
    out: dict[str, Any] = {"results": []}
    # highlight-start
    for cap in caps:
        live_driver = driver_registry.get_live_driver_for_capability(cap)
        if not live_driver:
            continue

        live_name = live_driver.describe().driver_name
        shadow_drivers = driver_registry.get_shadow_drivers_for_capability(cap)

        for shadow_driver in shadow_drivers:
            shadow_name = shadow_driver.describe().driver_name
            result = await ROLLER.evaluate_and_act(
                capability=cap,
                shadow_name=shadow_name,
                live_name=live_name,
                scorecards=scorecards,
                lifecycle=lifecycle,
                journal=journal,
            )
            out["results"].append(result)
    # highlight-end
    return out
