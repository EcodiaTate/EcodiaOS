from __future__ import annotations

import inspect
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, Field

# Graph-backed dossier builder
from systems.qora.core.code_graph.dossier_service import (
    get_multi_modal_dossier as build_dossier_from_graph,
)

dossier_router = APIRouter(tags=["qora", "dossier"])


class DossierRequest(BaseModel):
    # accept either "target_fqname" (new) or "symbol" (legacy)
    target_fqname: str = Field(
        ...,
        validation_alias=AliasChoices("target_fqname", "symbol"),
        description="Fully-qualified symbol, e.g. pkg/mod.py::Class::func",
    )
    intent: str = Field(
        default="implement",
        description="High-level intent for dossier assembly (e.g. 'refactor', 'implement').",
    )
    top_k: int | None = Field(
        default=None,
        ge=1,
        le=50,
        description="Optional cap on related items/citations.",
    )


async def _maybe_await(x: Any) -> Any:
    if callable(x):
        x = x()
    if hasattr(x, "__await__"):
        return await x
    return x


@dossier_router.post("/build", response_model=dict)
async def dossier_build(req: DossierRequest) -> dict:
    tfqn = (req.target_fqname or "").strip()
    if not tfqn:
        raise HTTPException(status_code=400, detail="target_fqname must not be empty")

    intent = (req.intent or "").strip() or "implement"

    # Build kwargs only for parameters the function actually supports
    sig = inspect.signature(build_dossier_from_graph)
    kwargs: dict[str, Any] = {"target_fqn": tfqn, "intent": intent}
    if "top_k" in sig.parameters and req.top_k is not None:
        kwargs["top_k"] = req.top_k

    try:
        data = await _maybe_await(lambda: build_dossier_from_graph(**kwargs))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"dossier_builder_error[{e.__class__.__name__}]: {e!s}",
        )

    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Dossier service returned non-dict")

    # Normalize common error shapes
    if data.get("status") == "error" or "error" in data:
        reason = data.get("reason") or data.get("error") or "Not found"
        raise HTTPException(status_code=404, detail=str(reason))

    return {"ok": True, "dossier": data}
