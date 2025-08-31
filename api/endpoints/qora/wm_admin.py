# api/endpoints/qora/wm_admin.py
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Response, status
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from systems.qora.core.code_graph.ingestor import patrol_and_ingest
from systems.simula.agent import qora_adapters as _qora

logger = logging.getLogger(__name__)
wm_admin_router = APIRouter(tags=["qora"])

IMMUNE_HEADER = "x-ecodia-immune"
DECISION_HEADER = "x-decision-id"


class ReindexReq(BaseModel):
    root: str = Field(default=".", description="Repo root to index")
    force: bool = Field(default=False, description="Force a full rebuild if supported")
    dry_run: bool = Field(default=False, description="Plan only; do not write")
    # room for future: namespaces: list[str] = Field(default_factory=list)


async def _run_reindex(req: ReindexReq) -> dict[str, Any]:
    """
    Actual reindex work. Extend this if patrol_and_ingest grows options.
    """
    try:
         # Now threads options into the ingestor
        result = await patrol_and_ingest(
            root_dir=req.root,
            force=req.force,
            dry_run=req.dry_run,
            changed_only=not req.force,   # force = full rebuild
        )
        return {"ok": True, "result": result}
    except Exception as e:
        logger.exception("[WM Admin] Code Graph ingestion failed: %s", e)
        return {"ok": False, "error": str(e)}


@wm_admin_router.post("/reindex", status_code=status.HTTP_202_ACCEPTED)
async def wm_reindex(
    body: Optional[ReindexReq] = Body(default=None),
    response: Response = None,
) -> dict[str, Any]:
    """
    Kick off a repository reindex. Returns 202 immediately; work continues in background.
    Immune header is added on the way out to avoid governance loops in any downstream internal calls.
    """
    req = body or ReindexReq()  # default root="."
    # Mark the *response* immune (helps chained internal calls read context, though request has already passed middleware)
    if response is not None:
        response.headers[IMMUNE_HEADER] = "1"
        # mirror any decision id provided by caller or mint a trace id
        response.headers.setdefault(DECISION_HEADER, "admin-reindex")

    # Schedule background task
    async def _bg():
        res = await _run_reindex(req)
        if not res.get("ok"):
            logger.error("[WM Admin] Reindex failed in background: %s", res.get("error"))

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_bg())
    except RuntimeError:
        # Fallback: run inline (should be rare in ASGI context)
        await _bg()

    return {
        "accepted": True,
        "root": req.root,
        "force": req.force,
        "dry_run": req.dry_run,
        "message": "Reindex started",
    }


@wm_admin_router.get("/export")
async def wm_export(fmt: str = "dot") -> dict[str, Any]:
    """
    Export the current Code Graph. `fmt` may be 'dot', 'json', etc (supported by _qora adaptor).
    """
    res = await _qora.qora_wm_graph_export(fmt=fmt)
    if res.get("status") != "success":
        raise HTTPException(status_code=500, detail=res.get("reason", "export failed"))
    return {"status": "success", "result": res.get("result")}
