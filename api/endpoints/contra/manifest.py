from __future__ import annotations

from fastapi import APIRouter, Query

from systems.contra.manifest.engine import run_checks  # async
from systems.contra.manifest.selector import select_pairs  # sync
from systems.qora.manifest.builder import build_manifest  # async

manifest_router = APIRouter(tags=["manifest"])


@manifest_router.post("/check")
async def check(system: str = Query(...), code_root: str = Query("./")) -> dict:
    m = await build_manifest(system, code_root)  # <-- await
    diags = await run_checks(m)  # <-- await
    return {"diagnostics": [d.model_dump() for d in diags], "manifest_hash": m.manifest_hash}


@manifest_router.post("/cycle")
async def cycle(
    system: str = Query(...),
    code_root: str = Query("./"),
    max_pairs: int = Query(200),
) -> dict:
    m = await build_manifest(system, code_root)  # <-- await
    pairs = select_pairs(m, max_pairs=max_pairs)  # selector expects a manifest object
    diags = await run_checks(m)  # <-- await
    return {
        "pairs": pairs,
        "diagnostics": [d.model_dump() for d in diags],
        "manifest_hash": m.manifest_hash,
    }
