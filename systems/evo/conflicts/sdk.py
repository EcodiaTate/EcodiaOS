# systems/evo/conflict/sdk.py
from hashlib import sha256
from time import time
from typing import Iterable
from core.utils.net_api import ENDPOINTS, get_http_client
import redis
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

IMMUNE_HEADER = "x-ecodia-immune"
ESC_TTL_SEC = 300  # tune

def _fp(agent: str, episode_id: str|None, patch_id: str|None, breaches: Iterable[str]|None) -> str:
    key = f"{agent}|{episode_id or ''}|{patch_id or ''}|{','.join(sorted(breaches or []))}"
    return sha256(key.encode("utf-8")).hexdigest()[:32]

async def escalate(agent: str, episode_id: str|None, patch_id: str|None, breaches: list[str]|None):
    fp = _fp(agent, episode_id, patch_id, breaches)

    # Prefer Redis; fallback to Neo4j gate if needed
    if redis.setnx(f"evo:escalate:{fp}", int(time())):
        redis.expire(f"evo:escalate:{fp}", ESC_TTL_SEC)
    else:
        logger.debug("ConflictSDK: idempotent skip for fp=%s", fp)
        return {"ok": True, "skipped": True, "reason": "idempotent"}

    async with get_http_client() as client:
        await client.post(
            "/evo/escalate",
            headers={IMMUNE_HEADER: "1"},     # avoid governance re-attest
            json={"agent": agent, "episode_id": episode_id, "patch_id": patch_id, "breaches": breaches or []},
            timeout=10.0,
        )
    return {"ok": True}
