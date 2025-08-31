# api/endpoints/spec_eval.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from systems.simula.spec_eval.scoreboard import load_scoreboard

router = APIRouter(tags=["simula"])


@router.get("/spec-eval/scoreboard")
async def spec_eval_scoreboard() -> dict[str, Any]:
    sb = load_scoreboard()
    return {"status": "success", "result": sb}
