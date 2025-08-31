from fastapi import APIRouter

from .deliberate import router

unity_router = APIRouter()
unity_router.include_router(router)
