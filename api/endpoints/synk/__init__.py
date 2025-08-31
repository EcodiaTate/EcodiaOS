from fastapi import APIRouter

from .switchboard import router as flag_router

synk_router = APIRouter()
synk_router.include_router(flag_router)
