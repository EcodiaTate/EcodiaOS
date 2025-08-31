from fastapi import APIRouter

from .meta_endpoints import meta_router
from .meta_status import meta_status_router
from .route_event import route_router
from .trace import trace_router
from .unity_bridge import bridge

atune_router = APIRouter()
atune_router.include_router(route_router)
atune_router.include_router(trace_router)
atune_router.include_router(bridge)
atune_router.include_router(meta_status_router)
atune_router.include_router(meta_router)
