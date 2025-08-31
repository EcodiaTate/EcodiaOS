# systems/unity/core/protocols/federated_consensus.py
from __future__ import annotations

import asyncio
import logging
from typing import Any

from systems.unity.core.room.orchestrator import DeliberationManager
from systems.unity.schemas import DeliberationSpec, RoomConfiguration, VerdictModel

logger = logging.getLogger(__name__)


def _to_verdict(obj: Any) -> VerdictModel:
    """Coerce various response shapes to a VerdictModel."""
    if isinstance(obj, VerdictModel):
        return obj
    # Pydantic-style
    if hasattr(obj, "model_dump"):
        return VerdictModel(**obj.model_dump())
    # dict-like
    if isinstance(obj, dict):
        # Sometimes the verdict is nested under 'verdict'
        if "outcome" in obj:
            return VerdictModel(**obj)
        if "verdict" in obj and isinstance(obj["verdict"], dict):
            return VerdictModel(**obj["verdict"])
    raise ValueError("Unrecognized verdict payload")


def _weighted_aggregate(verdicts: list[VerdictModel]) -> tuple[float, float, float]:
    """
    Returns (approval_ratio_weighted, confidence_avg_weighted, uncertainty_avg_weighted)
    using weights = confidence * (1 - uncertainty_clamped).
    """
    if not verdicts:
        return 0.0, 0.0, 1.0

    weights = []
    approves = []
    confs = []
    uncs = []
    for v in verdicts:
        w = float(max(0.0, min(1.0, v.confidence)) * (1.0 - max(0.0, min(1.0, v.uncertainty))))
        weights.append(w)
        approves.append(1.0 if str(v.outcome).upper() == "APPROVE" else 0.0)
        confs.append(float(v.confidence))
        uncs.append(float(v.uncertainty))

    wsum = sum(weights)
    if wsum <= 0:
        # Fallback to unweighted means
        approval_ratio = sum(approves) / len(approves)
        return approval_ratio, sum(confs) / len(confs), sum(uncs) / len(uncs)

    approval_ratio = sum(a * w for a, w in zip(approves, weights)) / wsum
    conf_avg = sum(c * w for c, w in zip(confs, weights)) / wsum
    unc_avg = sum(u * w for u, w in zip(uncs, weights)) / wsum
    return float(approval_ratio), float(conf_avg), float(unc_avg)


class FederatedConsensusProtocol:
    """
    H6 Federated Consensus: orchestrates multiple parallel deliberation rooms and
    aggregates their verdicts into a meta-verdict using confidence/uncertainty weights.
    """

    def __init__(
        self,
        base_spec: DeliberationSpec,
        room_configs: list[RoomConfiguration],
        quorum_threshold: float,
    ):
        self.base_spec = base_spec
        self.room_configs = room_configs
        self.quorum_threshold = float(quorum_threshold)
        self.deliberation_manager = DeliberationManager()

    async def _run_single_room(self, config: RoomConfiguration) -> VerdictModel:
        """Runs a single deliberation and returns its verdict."""
        try:
            # Clone and specialize the spec for this room
            room_spec = self.base_spec.copy(deep=True)
            room_spec.protocol_hint = (
                getattr(config, "protocol_id", None) or room_spec.protocol_hint
            )

            # Pass through optional per-room fields if present
            for attr in ("panel", "constraints", "topic", "timeout_s"):
                if hasattr(config, attr) and getattr(config, attr) is not None:
                    setattr(room_spec, attr, getattr(config, attr))

            result = await self.deliberation_manager.run_session(room_spec)
            # result may be a dict with 'verdict' or a DeliberationResponse-like object
            if isinstance(result, dict) and "verdict" in result:
                return _to_verdict(result["verdict"])
            return _to_verdict(result)
        except Exception as e:
            logger.exception(
                "[Federated] Sub-room deliberation failed for protocol_id=%s",
                getattr(config, "protocol_id", "unknown"),
            )
            # Treat failure as a high-uncertainty reject so it does not inflate confidence
            return VerdictModel(
                outcome="REJECT",
                confidence=0.0,
                uncertainty=1.0,
                dissent=f"Room execution failed: {e!r}",
            )

    async def run(self) -> dict[str, Any]:
        """Runs all deliberation rooms in parallel and computes the meta-verdict."""
        if not self.room_configs:
            empty = VerdictModel(
                outcome="REJECT",
                confidence=0.0,
                uncertainty=1.0,
                dissent="No rooms configured.",
            )
            return {"meta_verdict": empty, "room_verdicts": []}

        # Limit concurrency to avoid resource contention
        sem = asyncio.Semaphore(min(8, max(1, len(self.room_configs))))

        async def guarded_run(cfg: RoomConfiguration) -> VerdictModel:
            async with sem:
                return await self._run_single_room(cfg)

        tasks = [asyncio.create_task(guarded_run(cfg)) for cfg in self.room_configs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        room_verdicts: list[VerdictModel] = []
        for r in results:
            if isinstance(r, Exception):
                logger.exception("[Federated] Room task raised:", exc_info=r)
                room_verdicts.append(
                    VerdictModel(
                        outcome="REJECT",
                        confidence=0.0,
                        uncertainty=1.0,
                        dissent="Task error.",
                    ),
                )
            else:
                room_verdicts.append(r)

        approve_weighted, conf_avg, unc_avg = _weighted_aggregate(room_verdicts)
        meta_outcome = "APPROVE" if approve_weighted >= self.quorum_threshold else "REJECT"

        meta_verdict = VerdictModel(
            outcome=meta_outcome,
            confidence=round(conf_avg, 4),
            uncertainty=round(unc_avg, 4),
            dissent=(
                f"Federated consensus: weighted approval={approve_weighted:.3f} "
                f"over {len(room_verdicts)} rooms (quorum={self.quorum_threshold:.3f})."
            ),
        )

        return {
            "meta_verdict": meta_verdict,
            "room_verdicts": room_verdicts,
        }
