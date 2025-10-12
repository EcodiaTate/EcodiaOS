# api/endpoints/simula/__init__.py
from __future__ import annotations

from fastapi import APIRouter

# Feature routers (now all relative too)
from .artifacts import artifacts_router
from .code_advice import code_advice_router
from .github import router as github_router

# Core Simula endpoints (all define relative paths)
from .health import sim_health_router
from .jobs_codegen import codegen_router
from .jobs_codegen_guarded import router as codegen_guarded_router
from .policy_validate import router as policy_validate_router
from .replay import replay_router
from .risk import router as risk_router
from .spec_eval import router as spec_eval_router
from .twin_eval import twin_eval_router

# This router gets the "/simula" system prefix in app.py
simula_router = APIRouter()

# Order is roughly: health → jobs → analysis → integrations
simula_router.include_router(sim_health_router, tags=["simula", "health"])
simula_router.include_router(codegen_router, tags=["simula", "jobs"])
simula_router.include_router(replay_router, tags=["simula", "replay"])
simula_router.include_router(policy_validate_router, tags=["simula", "policy"])
simula_router.include_router(code_advice_router)

simula_router.include_router(artifacts_router, tags=["simula", "artifacts"])
simula_router.include_router(risk_router, tags=["simula", "risk"])
simula_router.include_router(spec_eval_router, tags=["simula", "spec-eval"])
simula_router.include_router(github_router, tags=["integrations", "github"])
simula_router.include_router(codegen_guarded_router, tags=["integrations", "github"])
simula_router.include_router(twin_eval_router)

__all__ = ["simula_router"]
