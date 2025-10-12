# systems/equor/core/identity/homeostasis_helper.py
from __future__ import annotations

import logging
import time
from hashlib import sha256
from typing import Any, Dict, Optional, Tuple

try:
    # Optional; safe if missing
    from redis.asyncio import Redis
except Exception:  # pragma: no cover
    redis = None  # type: ignore

from core.utils.neo.cypher_query import cypher_query
from core.utils.net_api import ENDPOINTS, post_internal  # <-- your new helper

logger = logging.getLogger(__name__)

IMMUNE_HEADER_NAME = "x-ecodia-immune"
DEFAULT_HEADERS = {IMMUNE_HEADER_NAME: "1"}

# Tune these
COOLDOWN_SEC = 30  # don't re-compose within this window if state identical
IDEMPOTENCY_TTL_SEC = 300  # key lifetime for idempotency (Redis/Neo4j fallback)


def _fp(applied_patch_id: str | None, breaches: list[str] | None) -> str:
    key = f"{applied_patch_id or ''}|{','.join(sorted(breaches or []))}"
    return sha256(key.encode("utf-8")).hexdigest()[:32]


class HomeostasisHelper:
    """
    Gating helper to prevent compose/escalate/attest re-entrancy loops.

    Policy:
      - Only compose when (applied_patch_id, sorted(breaches)) changed for this episode, OR cooldown elapsed.
      - Use Redis key (preferred) or Neo4j relationship as idempotency ledger.
      - Always set immune header on internal compose to avoid governance recursion.
    """

    def __init__(self, redis: Redis | None = None):
        self.redis = redis
        # in-process fast-path cache: episode_id -> (fp, ts)
        self._mem: dict[str, tuple[str, int]] = {}

    async def should_compose(
        self,
        episode_id: str,
        applied_patch_id: str | None,
        breaches: list[str] | None,
    ) -> bool:
        fp = _fp(applied_patch_id, breaches)
        now = int(time.time())

        # 1) In-memory debounce
        last = self._mem.get(episode_id)
        if last:
            last_fp, last_ts = last
            if last_fp == fp and (now - last_ts) < COOLDOWN_SEC:
                logger.debug("Homeostasis: skip compose (debounce) ep=%s fp=%s", episode_id, fp)
                return False

        # 2) Redis idempotency key (preferred)
        if self.redis:
            try:
                key = f"equor:homeostasis:{episode_id}:{fp}"
                if not await self.redis.setnx(key, now):
                    logger.debug(
                        "Homeostasis: skip compose (redis idempotent) ep=%s fp=%s", episode_id, fp
                    )
                    return False
                await self.redis.expire(key, IDEMPOTENCY_TTL_SEC)
            except Exception as e:
                logger.warning("Homeostasis: redis unavailable (%s), falling back to Neo4j", e)

        # 3) Neo4j fallback idempotency (idempotent MERGE)
        if not self.redis:
            q = """
            MERGE (e:Episode {id:$eid})
            ON CREATE SET e.created_at = datetime()
            WITH e
            MERGE (s:HomeostasisState {fp:$fp})
            ON CREATE SET s.created_at = datetime()
            MERGE (e)-[r:HOMEOSTASIS_STATE]->(s)
            ON CREATE SET r.t_first = datetime()
            SET r.t_last = datetime()
            RETURN r.t_first IS NULL AS existed
            """
            try:
                rows = await cypher_query(q, {"eid": episode_id, "fp": fp}) or []
                # If relationship already existed, treat as duplicate within TTL window.
                existed = bool(rows and rows[0].get("existed") is False)
                if existed:
                    logger.debug(
                        "Homeostasis: skip compose (neo idempotent) ep=%s fp=%s", episode_id, fp
                    )
                    return False
            except Exception as e:
                # If graph is down, fall through to allow compose rather than fail silently.
                logger.warning("Homeostasis: neo fallback failed (%s); allowing compose", e)

        # Update in-memory cache and allow
        self._mem[episode_id] = (fp, now)
        return True

    async def maybe_compose(
        self,
        *,
        agent: str,
        episode_id: str,
        profile_name: str = "prod",
        context: dict[str, Any] | None = None,
        applied_patch_id: str | None = None,
        breaches: list[str] | None = None,
        decision_id: str | None = None,
    ) -> dict[str, Any] | None:
        """
        If gating allows, call /equor/compose internally with immune header and return JSON.
        Otherwise return None (no-op).
        """
        if not await self.should_compose(episode_id, applied_patch_id, breaches):
            return None

        headers = dict(DEFAULT_HEADERS)
        if decision_id:
            headers["x-decision-id"] = decision_id

        payload = {
            "agent": agent,
            "episode_id": episode_id,
            "profile_name": profile_name,
            "context": context or {},
        }

        r = await post_internal(
            ENDPOINTS.EQUOR_COMPOSE, json=payload, headers=headers, timeout=10.0
        )
        try:
            return r.json()
        except Exception:
            return {"ok": True}  # best-effort; callers usually just need the side-effect
