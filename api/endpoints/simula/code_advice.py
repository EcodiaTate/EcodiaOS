# api/routes/simula.py
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

code_advice_router = APIRouter(tags=["simula"])


class EnqueueT1Body(BaseModel):
    ids: list[str]


class EnqueueT2Body(BaseModel):
    ids: list[str]


@code_advice_router.post("/t1")
async def enqueue_t1(body: EnqueueT1Body, request: Request):
    daemon = request.app.state.simula_daemon
    added = await daemon.enqueue_many_t1(body.ids)
    return {"enqueued": added}


@code_advice_router.post("/t2")
async def enqueue_t2(body: EnqueueT2Body, request: Request):
    daemon = request.app.state.simula_daemon
    added = await daemon.enqueue_many_t2(body.ids)
    return {"enqueued": added}
