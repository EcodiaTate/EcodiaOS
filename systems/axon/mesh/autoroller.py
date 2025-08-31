# systems/axon/mesh/autoroller.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from systems.axon.dependencies import get_scorecard_manager, get_lifecycle_manager, get_journal
# highlight-start
from systems.axon.journal.mej import MerkleJournal
from systems.axon.mesh.lifecycle import DriverLifecycleManager, DriverStatus
from systems.axon.mesh.scorecard import ScorecardManager
# highlight-end
from systems.axon.security.attestation import verify_driver_attestation


@dataclass
class AutoRollConfig:
    window_n: int = 200
    min_success: float = 0.90
    sr_margin: float = 0.02
    p95_factor: float = 1.05
    min_uplift_delta: float = 0.00
    cooldown_sec: int = 300
    require_attestation: bool = True


class _AutoRollDecision(BaseModel):
    type: str = "autoroll_decision"
    capability: str
    action: str
    live_before: str
    live_after: str | None
    meta: dict[str, Any]
    ts: float


class AutoRoller:
    def __init__(self, cfg: AutoRollConfig | None = None) -> None:
        self.cfg = cfg or AutoRollConfig()
        self._last_roll_ts: dict[str, float] = {}

    def _cooldown_ok(self, capability: str) -> bool:
        last = self._last_roll_ts.get(capability, 0.0)
        return (time.time() - last) >= self.cfg.cooldown_sec

    def _journal(self, *, capability: str, action: str, live_before: str, live_after: str | None, meta: dict[str, Any]) -> None:
        try:
            get_journal().write_entry(_AutoRollDecision(
                capability=capability, action=action, live_before=live_before, live_after=live_after, meta=meta, ts=time.time()
            ))
        except Exception:
            pass

    async def evaluate_and_act(
        self,
        capability: str,
        *,
        shadow_name: str,
        live_name: str,
        scorecards: ScorecardManager,
        lifecycle: DriverLifecycleManager,
        journal: MerkleJournal,
    ) -> dict[str, Any]:
        detail: dict[str, Any] = {"capability": capability, "shadow": shadow_name, "live": live_name, "decisions": []}

        if not self._cooldown_ok(capability):
            detail["cooldown"] = True
            return detail

        live_m = scorecards.get_window_metrics(live_name, self.cfg.window_n) or {}
        sh_m = scorecards.get_window_metrics(shadow_name, self.cfg.window_n) or {}

        # basic gates
        if (sh_m.get("success_rate", 0.0) < self.cfg.min_success) or (sh_m.get("success_rate", 0.0) < (live_m.get("success_rate", 0.0) - self.cfg.sr_margin)):
            detail["gate"] = "success_rate"
            return detail
        if sh_m.get("p95_ms", 9e9) > (live_m.get("p95_ms", 9e9) * self.cfg.p95_factor):
            detail["gate"] = "p95_latency"
            return detail
        if (sh_m.get("avg_uplift", 0.0) - live_m.get("avg_uplift", 0.0)) < self.cfg.min_uplift_delta:
            detail["gate"] = "uplift"
            return detail

        # attestation (optional)
        shadow_state = lifecycle.get_driver_state(shadow_name)
        if self.cfg.require_attestation and (not shadow_state or not verify_driver_attestation(shadow_state.spec)):
            detail["gate"] = "attestation"
            return detail

        # promote
        try:
            lifecycle.update_driver_status(live_name, DriverStatus.shadow)
            lifecycle.update_driver_status(shadow_name, DriverStatus.live)
            self._last_roll_ts[capability] = time.time()
            self._journal(
                capability=capability,
                action="promote",
                live_before=live_name,
                live_after=shadow_name,
                meta={"live_metrics": live_m, "shadow_metrics": sh_m},
            )
            detail["decisions"].append({"action": "promote_shadow_to_live", "driver": shadow_name})
        except Exception as e:
            detail["error"] = f"promote_failed: {e}"
        return detail