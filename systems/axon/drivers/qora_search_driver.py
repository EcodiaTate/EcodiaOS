# systems/axon/drivers/qora_search_driver.py
from __future__ import annotations

import hashlib
import os
import time
import uuid
from typing import Any

from pydantic import BaseModel

from core.utils.net_api import ENDPOINTS, get_http_client
from systems.axon.mesh.sdk import CapabilitySpec, DriverInterface, HealthStatus, ReplayCapsule
from systems.axon.schemas import ActionResult, AxonIntent


class QoraSearchDriver(DriverInterface):
    NAME = "qora_search"
    VERSION = "1.0.0"
    CAPABILITY = "qora:search"

    def describe(self) -> CapabilitySpec:
        return CapabilitySpec(
            driver_name=self.NAME,
            driver_version=self.VERSION,
            supported_actions=[self.CAPABILITY],
            risk_profile={self.CAPABILITY: "normal"},
            budget_model={self.CAPABILITY: 1.0},
            auth_requirements=["api_key"],
        )

    async def self_test(self) -> HealthStatus:
        http = await get_http_client()
        try:
            r = await http.get(ENDPOINTS.QORA_ARCH_HEALTH)
            ok = (r.status_code // 100) == 2
            return HealthStatus(status="ok" if ok else "degraded", details=f"status={r.status_code}", dependencies={"qora": "ok" if ok else "error"})
        except Exception as e:
            return HealthStatus(status="error", details=str(e), dependencies={"qora": "error"})

    async def push(self, intent: AxonIntent) -> ActionResult:
        """
        Executes a search-then-execute against Qora. Respects constraints.dry_run.
        """
        http = await get_http_client()
        params = intent.params or {}
        body = {
            "query": params.get("query", ""),
            "safety_max": params.get("safety_max", 2),
            "top_k": params.get("top_k", 3),
            "system": params.get("system"),
        }
        # dry-run just returns a shaped stub
        if getattr(intent.constraints or {}, "dry_run", False):
            return ActionResult(status="dry_run", outputs={"preview": body}, side_effects=[], counterfactual_metrics={})

        r = await http.post(ENDPOINTS.QORA_ARCH_EXECUTE_BY_QUERY, json=body)
        r.raise_for_status()
        data = r.json()
        return ActionResult(status="ok", outputs=data, side_effects=[], counterfactual_metrics={})

    async def repro_bundle(self, *, id: str, kind: str) -> ReplayCapsule:
        """
        Build a deterministic capsule for the given item id (intent/event).
        We hash the relevant runtime environment + alias map to pin dependencies.
        """
        env_fingerprint = "|".join(
            [
                os.getenv("ECODIAOS_BASE_URL", ""),
                getattr(ENDPOINTS, "QORA_ARCH_EXECUTE_BY_QUERY", "/qora/arch/execute-by-query"),
                getattr(ENDPOINTS, "QORA_ARCH_HEALTH", "/qora/arch/health"),
                os.getenv("QORA_API_KEY", "dev")[:6],  # prefix only, avoids leaking full secret
            ]
        )
        env_hash = hashlib.blake2b(env_fingerprint.encode("utf-8"), digest_size=16).hexdigest()

        # In a full build we'd look up the original inputs/outputs from MEJ by id.
        # For now, package a minimal replay contract that can be executed directly.
        inputs = {"id": id, "kind": kind, "capability": self.CAPABILITY, "replay_howto": "POST ENDPOINTS.QORA_ARCH_EXECUTE_BY_QUERY with {query, safety_max, top_k, system}"}
        outputs: dict[str, Any] = {}

        return ReplayCapsule(
            id=str(uuid.uuid4()),
            type=kind,  # "intent" | "event"
            driver_version=self.VERSION,
            environment_hash=env_hash,
            inputs=inputs,
            outputs=outputs,
        )
