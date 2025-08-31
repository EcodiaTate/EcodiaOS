# api/endpoints/spec_eval_run.py
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from systems.simula.agent import qora_adapters as _qora
from systems.simula.config import settings
from systems.simula.spec_eval.scoreboard import SPEC_EVAL_DIRNAME

router = APIRouter(tags=["simula"])


class Candidate(BaseModel):
    id: str
    prompt: dict[str, Any]
    meta: dict[str, Any] | None = None


class SpecEvalReq(BaseModel):
    candidates: list[Candidate]
    min_delta_cov: float = 0.0
    timeout_sec: int = 900
    max_parallel: int = 4
    score_weights: dict[str, float] | None = None
    emit_markdown: bool = True
    title: str | None = None
    notes: str | None = None


@router.post("/spec-eval/run")
async def spec_eval_run(req: SpecEvalReq) -> dict[str, Any]:
    if not req.candidates:
        raise HTTPException(status_code=400, detail="candidates must be non-empty")

    res = await _qora.qora_spec_eval_run(
        candidates=[c.model_dump() for c in req.candidates],
        min_delta_cov=req.min_delta_cov,
        timeout_sec=req.timeout_sec,
        max_parallel=req.max_parallel,
        score_weights=req.score_weights,
        emit_markdown=req.emit_markdown,
    )
    if res.get("status") != "success":
        raise HTTPException(status_code=500, detail=res.get("reason", "spec_eval failed"))

    # persist for scoreboard
    root = Path(settings.artifacts_root or (settings.repo_root or ".")) / SPEC_EVAL_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    run_id = res.get("result", {}).get("run_id") or datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    payload = {
        "run_id": run_id,
        "title": req.title,
        "notes": req.notes,
        "created_at": datetime.utcnow().isoformat() + "Z",
        **(res.get("result") or res),
    }
    (root / f"{run_id}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"status": "success", "result": payload}
