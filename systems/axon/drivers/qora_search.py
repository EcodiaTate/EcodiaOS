from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from systems.axon.mesh.registry import DriverInterface
from systems.synk.core.tools.neo import semantic_graph_search

log = logging.getLogger("QoraSearch")

# SAFE graph labels (fixed; not user-selectable)
SAFE_LABELS: list[str] = [
    "MEvent",
    "Event",
    "SystemEval",
    "SystemResponse",
    "IdentityState",
    "Conflict",
    "SystemMessage",
    "IdentityFacet",
    "UnityRoom",
    "EvoQuestion",
    "Consensus",
]


class _Spec(BaseModel):
    driver_name: str
    version: str
    supported_actions: list[str]
    summary: str


class _Args(BaseModel):
    # Natural-language retrieval cue (e.g., “when did we discuss planner guardrails?”)
    query: str = Field(..., min_length=1, description="Natural language memory/search cue.")
    top_k: int = Field(5, ge=1, le=50, description="Max results (1–50).")


class QoraSearch(DriverInterface):
    """
    Ecodia inward lookup: semantic retrieval over SAFE in-graph memory/history.
    Endpoint: qora.semantic_search
    """

    NAME: str = "qora"
    VERSION: str = "1.0.1"
    ACTION: Literal["semantic_search"] = "semantic_search"

    def describe(self) -> _Spec:
        return _Spec(
            driver_name=self.NAME,
            version=self.VERSION,
            supported_actions=[self.ACTION],
            # Tuned so it reads as “internal memory search” without being heavy-handed
            summary="Ecodia semantic memory search across SAFE graph artifacts (events, responses, identity states, etc.).",
        )

    async def semantic_search(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            args = _Args(**params)
        except ValidationError as e:
            return {"status": "error", "message": f"Invalid parameters: {e}"}

        try:
            rows = await semantic_graph_search(
                query_text=args.query,
                top_k=args.top_k,
                labels=SAFE_LABELS,  # fixed scope; not exposed to callers
            )
            # Results: [{ "n": props, "labels": [...], "score": float }]
            return {
                "status": "ok",
                "mode": "introspect",  # small hint for planners/critics
                "query": args.query,
                "top_k": args.top_k,
                "results": rows,
            }
        except Exception as e:
            log.exception("[Qora.semantic_search] failure")
            return {"status": "error", "message": str(e)}

    async def self_test(self) -> dict[str, Any]:
        try:
            probe = await self.semantic_search({"query": "identity continuity", "top_k": 3})
            if probe.get("status") != "ok":
                raise RuntimeError(probe.get("message", "Unknown error"))
            return {
                "status": "ok",
                "message": f"Qora semantic search healthy ({len(probe.get('results', []))} results).",
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def repro_bundle(self) -> dict[str, Any]:
        return {
            "driver_name": self.NAME,
            "version": self.VERSION,
            "labels": SAFE_LABELS,
        }
