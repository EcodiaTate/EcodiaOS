# api/status/register.py
from fastapi import FastAPI
from api.status.common import SERVICE_CHECKS, router_for

def attach_status_routers(app: FastAPI):
    for name in SERVICE_CHECKS.keys():
        app.include_router(router_for(name))
