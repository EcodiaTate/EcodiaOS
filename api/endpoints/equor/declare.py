# api/endpoints/equor/declare.py
from __future__ import annotations

import hashlib
import hmac
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request

from core.llm.bus import event_bus
from core.utils.neo.cypher_query import cypher_query
from systems.equor.core.neo import graph_writes
from systems.equor.schemas import ConstitutionRule, Facet, Profile
from systems.synk.core.switchboard.gatekit import route_gate

declare_router = APIRouter()
logger = logging.getLogger(__name__)


# ----------------------------
# Governance permission check
# ----------------------------
async def _lookup_actor(id_or_email: str) -> dict | None:
    rows = await cypher_query(
        """
        MATCH (a:Actor)
        WHERE a.id = $x OR a.email = $x
        OPTIONAL MATCH (a)-[:HAS_ROLE]->(r:Role {name:'governance'})
        RETURN a.id AS id, a.token_hash AS token_hash, COALESCE(a.active, true) AS active,
               any(rr IN collect(r.name) WHERE rr='governance') AS has_role
        """,
        {"x": id_or_email},
    )
    return rows[0] if rows else None


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


async def get_governance_permission(request: Request) -> None:
    """
    Authorizes governance actions via either:
      1) Actor identity + token matched in graph, with :HAS_ROLE(:Role{name:'governance'})
         Headers:
           - X-Ecodia-Actor: <actor id or email>
           - X-Actor-Token: <opaque secret issued to this actor>
      2) Bootstrap token (env) for controlled automation:
           - Header: X-Governance-Token
           - Env: ECODIA_GOVERNANCE_BOOT_TOKEN (sha256 compared)
    Raises HTTPException on failure.
    """
    actor = request.headers.get("X-Ecodia-Actor", "").strip()
    actor_token = request.headers.get("X-Actor-Token", "").strip()
    boot_hdr = request.headers.get("X-Governance-Token", "").strip()
    boot_env = os.getenv("ECODIA_GOVERNANCE_BOOT_TOKEN", "").strip()

    # Path 2: bootstrap token
    if boot_hdr and boot_env:
        ok = hmac.compare_digest(_sha256_hex(boot_hdr), _sha256_hex(boot_env))
        if ok:
            return
        # continue to actor path if bootstrap mismatch

    # Path 1: actor + token + role
    if not actor or not actor_token:
        raise HTTPException(status_code=401, detail="Missing governance credentials.")

    rec = await _lookup_actor(actor)
    if not rec or not rec.get("active", True):
        raise HTTPException(status_code=403, detail="Actor inactive or not found.")

    token_hash = rec.get("token_hash") or ""
    if not token_hash:
        raise HTTPException(status_code=403, detail="Actor has no token registered.")

    # constant-time compare
    if not hmac.compare_digest(token_hash, _sha256_hex(actor_token)):
        raise HTTPException(status_code=403, detail="Invalid actor token.")

    if not rec.get("has_role", False):
        raise HTTPException(status_code=403, detail="Actor lacks 'governance' role.")

    return  # authorized


# ----------------------------
# Endpoints
# ----------------------------
@declare_router.post(
    "/identity/declare",
    status_code=202,
    dependencies=[
        route_gate("equor.identity.declare.enabled", True),
        Depends(get_governance_permission),
    ],
    summary="Declare or update an Identity Facet or Profile (Gated)",
)
async def declare_identity(items: list[Facet | Profile]):
    """
    Declares new versions of Identity Facets or Profiles.
    Creates versioned nodes (no in-place edits) and emits an event.
    """
    if not items:
        raise HTTPException(status_code=400, detail="Item list cannot be empty.")

    updated_ids: list[str] = []
    try:
        for item in items:
            if isinstance(item, Facet):
                rid = await graph_writes.upsert_facet(item)
                if rid:
                    updated_ids.append(str(rid))
            elif isinstance(item, Profile):
                rid = await graph_writes.upsert_profile(item)
                if rid:
                    updated_ids.append(str(rid))
            else:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unsupported item type: {type(item).__name__}",
                )

        await event_bus.publish(
            {
                "topic": "equor.identity.updated",
                "payload": {"count": len(updated_ids), "ids": updated_ids},
            },
        )
        return {
            "status": "accepted",
            "message": f"{len(updated_ids)} identity items updated.",
            "ids": updated_ids,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to declare identity items.")
        raise HTTPException(status_code=500, detail=f"Failed to declare identity: {e}") from e


@declare_router.post(
    "/constitution/update",
    status_code=202,
    dependencies=[
        route_gate("equor.constitution.update.enabled", True),
        Depends(get_governance_permission),
    ],
    summary="Update the Constitution with new Rules (Gated)",
)
async def update_constitution(rules: list[ConstitutionRule]):
    """
    Adds new versions of constitutional rules and maintains
    SUPERSEDES / CONFLICTS_WITH relationships for coherence and auditability.
    """
    if not rules:
        raise HTTPException(status_code=400, detail="Rule list cannot be empty.")

    try:
        updated_ids = await graph_writes.upsert_rules(rules)
        await event_bus.publish(
            {
                "topic": "equor.constitution.updated",
                "payload": {"rule_ids": updated_ids, "count": len(updated_ids)},
            },
        )
        return {
            "status": "accepted",
            "message": f"{len(updated_ids)} constitutional rules updated.",
            "ids": updated_ids,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to update constitution.")
        raise HTTPException(status_code=500, detail=f"Failed to update constitution: {e}") from e
