from fastapi import APIRouter

from .feedback import feedback_router
from .generate_soul import generate_router
from .interface_mood import mood_router
from .match_soul import match_router
from .profile import profile_router
from .talk import talk_router
from .tts import tts_router

voxis_router = APIRouter()
voxis_router.include_router(generate_router)
voxis_router.include_router(match_router)
voxis_router.include_router(talk_router)
voxis_router.include_router(mood_router)
voxis_router.include_router(tts_router, prefix="/tts")
voxis_router.include_router(feedback_router)
voxis_router.include_router(profile_router)
