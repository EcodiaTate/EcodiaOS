from __future__ import annotations

import json
from hashlib import blake2s

from systems.evo.schemas import (
    ConflictNode,
    Hypothesis,
    ObviousnessReport,
    ReplayCapsule,
)


def _stable_barcode(payload: dict) -> str:
    # Deterministic, order-independent content hash.
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return blake2s(data).hexdigest()


class ReplayCapsuleBuilder:
    """
    Creates reproducible ReplayCapsule objects with a stable content barcode.
    This isolates construction (what goes *in* a capsule) from storage concerns.
    """

    def __init__(
        self,
        evo_engine_version: str = "2.0",
        default_hypothesis_model: str = "hypothesis.factory.v1",
    ) -> None:
        self._evo_engine_version = evo_engine_version
        self._default_hypothesis_model = default_hypothesis_model

    def build(
        self,
        decision_id: str,
        initial_conflicts: list[ConflictNode],
        obviousness_report: ObviousnessReport,
        hypotheses: list[Hypothesis],
        *,
        obviousness_model_version: str | None = None,
        hypothesis_model_version: str | None = None,
    ) -> ReplayCapsule:
        """
        Assemble a capsule. The barcode is computed over *all* content fields
        except the barcode itself, ensuring integrity/replayability.
        """

        versions = ReplayCapsule.Versions(
            evo_engine=self._evo_engine_version,
            obviousness_model=obviousness_model_version or obviousness_report.model_version,
            hypothesis_model=hypothesis_model_version or self._default_hypothesis_model,
        )

        inputs = ReplayCapsule.Inputs(
            conflict_ids=[c.conflict_id for c in initial_conflicts],
            initial_conflicts=initial_conflicts,
        )

        artifacts = ReplayCapsule.Artifacts(
            obviousness_report=obviousness_report,
            hypotheses=hypotheses,
        )

        # Compose the body *without* the barcode to hash deterministically.
        body_wo_barcode = {
            "capsule_id": decision_id,
            "inputs": inputs.model_dump(),
            "versions": versions.model_dump(),
            "artifacts": artifacts.model_dump(),
        }
        barcode = _stable_barcode(body_wo_barcode)

        return ReplayCapsule(
            capsule_id=decision_id,
            barcode=barcode,
            inputs=inputs,
            versions=versions,
            artifacts=artifacts,
        )
