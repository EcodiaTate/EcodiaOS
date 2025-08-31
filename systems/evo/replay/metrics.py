# file: systems/evo/telemetry/metrics.py
from __future__ import annotations


class EvoTelemetry:
    """Emit telemetry about Evo internals (no-op MVP)."""

    def record_event(self, name: str, payload: dict) -> None:
        return None

    def proposal_emitted(self, proposal_id: str) -> None:
        return None

    def replay_verified(self, capsule_id: str, ok: bool) -> None:
        return None
