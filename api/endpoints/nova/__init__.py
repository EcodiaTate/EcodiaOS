# file: api/endpoints/nova/__init__.py
from __future__ import annotations

from fastapi import APIRouter

from .core import router as core_router
from .handoff import router as handoff_router
from .policy import router as policy_router

nova_router = APIRouter(tags=["nova"])
nova_router.include_router(core_router)
nova_router.include_router(handoff_router)
nova_router.include_router(policy_router)

__all__ = ["nova_router"]
