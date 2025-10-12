# D:\EcodiaOS\api\endpoints\app_health.py
from __future__ import annotations

import os

from fastapi import APIRouter

# Get application version from environment variable, with a default
APP_VERSION = os.getenv("APP_VERSION", "0.0.1")

# Create a new router instance
health_router = APIRouter()


@health_router.get("/health", tags=["_health"])
async def health_check():
    """
    A simple health check endpoint that confirms the API is running.
    """
    return {"status": "ok", "version": APP_VERSION}
