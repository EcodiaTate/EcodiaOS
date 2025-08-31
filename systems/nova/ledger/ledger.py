# file: systems/nova/ledger/ledger.py
from __future__ import annotations

from hashlib import blake2s
from typing import Any
from uuid import uuid4

from systems.nova.schemas import DesignCapsule, InnovationBrief, InventionArtifact


def _barcode(payload: dict[str, Any]) -> str:
    h = blake2s()
    h.update(repr(sorted(payload.items())).encode("utf-8"))
    return h.hexdigest()


def _as_dict(x: InventionArtifact | dict[str, Any]) -> dict[str, Any]:
    # Accept either a Pydantic model or a plain dict
    return x.dict() if hasattr(x, "dict") else dict(x)


class NovaLedger:
    """
    Minimal in-memory ledger for DesignCapsules.
    Persists:
      - capsule_id
      - brief (serialized)
      - artifacts (with barcodes)
      - playbook DAG & eval logs
      - env pins / seeds when provided
    """

    def __init__(self) -> None:
        self._capsules: dict[str, dict[str, Any]] = {}

    async def annotate_capsule(self, capsule_id: str, **fields) -> DesignCapsule:
        data = self._capsules.get(capsule_id)
        if not data:
            return await self.get_capsule(capsule_id)
        data.update({k: v for k, v in fields.items()})
        self._capsules[capsule_id] = data
        return DesignCapsule(**data)

    async def save_capsule(
        self,
        brief: InnovationBrief,
        artifacts: list[InventionArtifact | dict[str, Any]] | None = None,
        playbook_dag: dict[str, Any] | None = None,
        eval_logs: dict[str, Any] | None = None,
        counterfactuals: dict[str, Any] | None = None,
        costs: dict[str, Any] | None = None,
        env_pins: dict[str, Any] | None = None,
        seeds: dict[str, Any] | None = None,
    ) -> DesignCapsule:
        cap_id = f"dc_{uuid4().hex[:10]}"
        barcodes: dict[str, str] = {}
        art_dicts: list[dict[str, Any]] = []

        for i, a in enumerate(artifacts or []):
            d = _as_dict(a)
            b = _barcode({"i": i, "type": d.get("type"), "diffs": d.get("diffs", [])})
            barcodes[f"a{i}"] = b
            art_dicts.append(d)

        stored = {
            "capsule_id": cap_id,
            "brief": brief.dict(),
            "playbook_dag": playbook_dag or {},
            "artifacts": art_dicts,
            "eval_logs": eval_logs or {},
            "counterfactuals": counterfactuals or {},
            "costs": costs or {},
            "barcodes": barcodes,
            "env": {"pins": env_pins or {}, "seeds": seeds or {}},
        }
        self._capsules[cap_id] = stored
        return DesignCapsule(**stored)

    async def get_capsule(self, capsule_id: str) -> DesignCapsule:
        data = self._capsules.get(capsule_id)
        if not data:
            # Return an empty but well-formed capsule for robustness
            return DesignCapsule(
                capsule_id=capsule_id,
                brief=InnovationBrief(brief_id="unknown", source="system", problem="not found"),
                playbook_dag={},
                artifacts=[],
                eval_logs={},
                counterfactuals={},
                costs={},
                barcodes={},
            )
        return DesignCapsule(**data)
