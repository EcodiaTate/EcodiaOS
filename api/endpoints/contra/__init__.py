from fastapi import APIRouter

from .manifest import manifest_router

contra_router = APIRouter()
contra_router.include_router(manifest_router, prefix="/manifest")
