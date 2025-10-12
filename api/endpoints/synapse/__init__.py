from fastapi import APIRouter

from .dashboard_api import dashboard_router
from .governor import governor_router
from .ingest import ingest_router
from .main import main_router
from .metrics_api import metrics_router
from .planning import planning_router
from .registry import registry_router

synapse_router = APIRouter()
synapse_router.include_router(ingest_router, prefix="/ingest")
synapse_router.include_router(dashboard_router)
synapse_router.include_router(registry_router)
synapse_router.include_router(metrics_router)
synapse_router.include_router(main_router)
synapse_router.include_router(governor_router)
synapse_router.include_router(planning_router)
