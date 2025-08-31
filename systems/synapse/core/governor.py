# systems/synapse/core/governor.py
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

from core.llm.bus import event_bus
from core.utils.neo.cypher_query import cypher_query
from core.utils.net_api import ENDPOINTS, get_http_client
from systems.simula.code_sim.sandbox.sandbox import DockerSandbox
from systems.simula.code_sim.sandbox.seeds import seed_config
from systems.synapse.safety.sentinels import sentinel_manager

logger = logging.getLogger(__name__)
PatchProposal = dict[str, Any]


def _proposal_id(proposal: PatchProposal) -> str:
    pid = str(proposal.get("id") or "")
    if pid:
        return pid
    diff = proposal.get("diff", "")
    h = hashlib.sha256(diff.encode("utf-8")).hexdigest()[:24]
    return f"pp_{h}"


async def _record_verification(
    proposal_id: str,
    summary: str,
    steps: dict[str, dict[str, Any]],
    status: str,
) -> None:
    """
    Persist a full audit trail for this verification attempt.
    """
    await cypher_query(
        """
        MERGE (p:UpgradeProposal {id:$pid})
        ON CREATE SET p.created_at = datetime(), p.summary = $summary
        ON MATCH  SET p.summary = coalesce($summary, p.summary), p.last_seen = datetime()
        CREATE (v:UpgradeVerification {
            id: $vid,
            status: $status,
            steps: $steps,
            at: datetime()
        })
        MERGE (p)-[:HAS_VERIFICATION]->(v)
        """,
        {
            "pid": proposal_id,
            "summary": summary,
            "vid": f"ver_{hashlib.sha256((proposal_id + str(time.time())).encode()).hexdigest()[:16]}",
            "status": status,
            "steps": json.dumps(steps, separators=(",", ":"), ensure_ascii=False),
        },
    )


class Governor:
    """
    Verifiable Self-Upgrade Pipeline.
    Runs regression → historical replay → sentinel checks,
    records an audit in the graph, and emits an approval event on success.
    """

    _instance: Governor | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def _run_regression_suite(self, patch: str) -> tuple[bool, dict[str, Any]]:
        t0 = time.time()
        sandbox_cfg = seed_config()
        sandbox_cfg["network"] = "bridge"
        try:
            async with DockerSandbox(sandbox_cfg).session() as sess:
                applied = await sess.apply_unified_diff(patch)
                if not applied:
                    msg = "Patch could not be applied in sandbox."
                    logger.error("[Governor] %s", msg)
                    return False, {"ok": False, "reason": msg, "dur_s": time.time() - t0}

                rc, out = await sess.run(["pytest", "-q"], timeout=3600)
                ok = rc == 0
                if not ok:
                    logger.error("[Governor] Regression suite failed rc=%s", rc)
                else:
                    logger.info("[Governor] Regression suite passed.")
                return ok, {"ok": ok, "rc": rc, "output": out[-20_000:], "dur_s": time.time() - t0}
        except Exception as e:
            logger.exception("[Governor] Regression suite exception.")
            return False, {"ok": False, "exception": str(e), "dur_s": time.time() - t0}

    async def _run_historical_replay(self, patch: str) -> tuple[bool, dict[str, Any]]:
        t0 = time.time()
        try:
            http = await get_http_client()
            resp = await http.post(
                ENDPOINTS.SIMULA_HISTORICAL_REPLAY,
                json={"patch_diff": patch},
                timeout=3600.0,
            )
            resp.raise_for_status()
            data = resp.json()
            ok = bool(data.get("passed"))
            if not ok:
                logger.error("[Governor] Historical replay failed: %s", data.get("reason"))
            else:
                logger.info("[Governor] Historical replay passed.")
            return ok, {"ok": ok, "response": data, "dur_s": time.time() - t0}
        except Exception as e:
            logger.exception("[Governor] Historical replay exception.")
            return False, {"ok": False, "exception": str(e), "dur_s": time.time() - t0}

    async def _run_sentinel_checks(self, patch: str) -> tuple[bool, dict[str, Any]]:
        t0 = time.time()
        try:
            alert = await sentinel_manager.analyze_patch_for_risks(patch)
            if alert:
                logger.error("[Governor] Sentinel alert: %s", alert.get("type", "unknown"))
                return False, {"ok": False, "alert": alert, "dur_s": time.time() - t0}
            logger.info("[Governor] Sentinel checks passed.")
            return True, {"ok": True, "dur_s": time.time() - t0}
        except Exception as e:
            logger.exception("[Governor] Sentinel checks exception.")
            return False, {"ok": False, "exception": str(e), "dur_s": time.time() - t0}

    async def verify_and_apply_upgrade(self, proposal: PatchProposal) -> dict[str, Any]:
        """
        Orchestrate full verification. On success, publish an approval event
        for CI/CD and persist an audit trail in the graph.
        """
        patch = proposal.get("diff", "")
        if not patch:
            return {"status": "rejected", "reason": "Proposal contains no diff."}

        proposal_id = _proposal_id(proposal)
        summary = str(proposal.get("summary", "upgrade"))

        steps: dict[str, dict[str, Any]] = {}

        ok, result = await self._run_regression_suite(patch)
        steps["regression"] = result
        if not ok:
            await _record_verification(proposal_id, summary, steps, status="rejected")
            return {
                "status": "rejected",
                "reason": "Failed regression test suite.",
                "proposal_id": proposal_id,
            }

        ok, result = await self._run_historical_replay(patch)
        steps["historical_replay"] = result
        if not ok:
            await _record_verification(proposal_id, summary, steps, status="rejected")
            return {
                "status": "rejected",
                "reason": "Failed historical replay simulation.",
                "proposal_id": proposal_id,
            }

        ok, result = await self._run_sentinel_checks(patch)
        steps["sentinels"] = result
        if not ok:
            await _record_verification(proposal_id, summary, steps, status="rejected")
            return {
                "status": "rejected",
                "reason": "Failed sentinel checks.",
                "proposal_id": proposal_id,
            }

        # All checks passed → persist success + emit event
        await _record_verification(proposal_id, summary, steps, status="approved")
        await event_bus.publish(
            {
                "topic": "synapse.meta.optimized",
                "payload": {"strategy_map": strategy_map, "models": models_info},
            },
        )
        logger.info("[Governor] Approval event published for %s.", proposal_id)

        return {
            "status": "approved",
            "reason": "All verification checks passed; deployment triggered.",
            "proposal_id": proposal_id,
        }


# Singleton export
governor = Governor()
