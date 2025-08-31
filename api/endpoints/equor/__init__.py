from fastapi import APIRouter

from .attest import attest_router
from .compose import compose_router
from .declare import declare_router
from .drift import drift_router
from .invariants import invariants_router

equor_router = APIRouter()
equor_router.include_router(attest_router)
equor_router.include_router(compose_router)
equor_router.include_router(declare_router)
equor_router.include_router(drift_router)
equor_router.include_router(invariants_router)
