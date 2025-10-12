from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

recipes_router = APIRouter(prefix="/recipes", tags=["recipes"])

try:
    from systems.qora.recipes.registry import (  # type: ignore
        Recipe,
        find_recipe,
        list_recipes,
        write_recipe,
    )
except Exception:  # pragma: no cover
    Recipe = None
    list_recipes = write_recipe = find_recipe = None


class RecipeWrite(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., min_length=1)
    trigger: dict[str, Any]
    actions: list[dict[str, Any]] = Field(default_factory=list)
    notes: str | None = None


class RecipeFind(BaseModel):
    model_config = ConfigDict(extra="ignore")

    trigger: dict[str, Any]


def _to_dict(obj: Any) -> dict[str, Any]:
    """Best-effort object → dict for Pydantic or plain classes."""
    try:
        # Pydantic v2
        return obj.model_dump()  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        # Pydantic v1
        return obj.dict()  # type: ignore[attr-defined]
    except Exception:
        pass
    # Fallback
    return getattr(obj, "__dict__", {}) or {}


@recipes_router.get("/list")
async def recipes_list() -> dict[str, Any]:
    if not callable(list_recipes):
        raise HTTPException(status_code=501, detail="recipes registry unavailable")
    try:
        items = list_recipes()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"list failed: {e!r}")
    return {"recipes": [_to_dict(r) for r in (items or [])]}


@recipes_router.post("/write")
async def recipes_write(req: RecipeWrite) -> dict[str, Any]:
    if Recipe is None or not callable(write_recipe):
        raise HTTPException(status_code=501, detail="recipes registry unavailable")
    rid = f"rec_{uuid4().hex[:8]}"
    try:
        rec = Recipe(  # type: ignore[call-arg]
            id=rid,
            name=req.name,
            trigger=req.trigger,
            actions=req.actions,
            notes=req.notes,
            created_at=time.time(),
            hits=0,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid recipe payload: {e!r}")
    try:
        write_recipe(rec)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"write failed: {e!r}")
    return {"ok": True, "id": rid}


@recipes_router.post("/find")
async def recipes_find(req: RecipeFind) -> dict[str, Any]:
    if not callable(find_recipe) or not callable(write_recipe):
        raise HTTPException(status_code=501, detail="recipes registry unavailable")
    try:
        rec = find_recipe(req.trigger)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"find failed: {e!r}")

    if not rec:
        return {"ok": False, "reason": "no_match"}

    # bump usage counter; tolerate shapes without 'hits'
    try:
        hits = getattr(rec, "hits", 0) or 0
        setattr(rec, "hits", int(hits) + 1)
        write_recipe(rec)
    except Exception:
        # Non-fatal
        pass

    return {"ok": True, "recipe": _to_dict(rec)}
