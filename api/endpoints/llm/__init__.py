from fastapi import APIRouter

from .call import call_router

llm_router = APIRouter()
llm_router.include_router(call_router)
