# file: api/endpoints/evo/__init__.py
from __future__ import annotations

from fastapi import APIRouter

from .conflicts import conflicts_router
from .core import core_router
from .escalate import escalate_router
from .evidence import evidence_router
from .hypotheses import hypotheses_router
from .obviousness import obviousness_router
from .proposals import proposals_router
from .repair import repair_router
from .replay import replay_router
from .scorecards import scorecards_router

evo_router = APIRouter(tags=["evo"])
evo_router.include_router(core_router)
evo_router.include_router(conflicts_router, prefix="/conflicts")
evo_router.include_router(hypotheses_router, prefix="/hypotheses")
evo_router.include_router(proposals_router, prefix="/proposals")
evo_router.include_router(replay_router, prefix="/replay")
evo_router.include_router(evidence_router, prefix="/evidence")
evo_router.include_router(obviousness_router, prefix="/conflicts")
evo_router.include_router(scorecards_router, prefix="/scorecards")
evo_router.include_router(repair_router, prefix="/repair")
evo_router.include_router(escalate_router)

__all__ = ["evo_router"]
