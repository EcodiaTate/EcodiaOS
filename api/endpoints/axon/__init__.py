from fastapi import APIRouter

from .ab import ab_router
from .autoroll import autoroll_router
from .capabilities import mesh_router
from .core_routes import core_router
from .probecraft import probecraft_router
from .promote import promoter_router
from .sense import sense_router
from .telemetry_hint import telemetry_router

axon_router = APIRouter()
axon_router.include_router(sense_router)
axon_router.include_router(promoter_router)
axon_router.include_router(core_router, prefix="/core")
axon_router.include_router(autoroll_router, prefix="/autoroll")
axon_router.include_router(ab_router, prefix="/ab")
axon_router.include_router(probecraft_router, prefix="/probecraft")
axon_router.include_router(mesh_router, prefix="/mesh")
axon_router.include_router(telemetry_router)
