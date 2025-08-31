from __future__ import annotations

import copy
from typing import Any
from uuid import uuid4

from systems.nova.dsl.lint import LintIssue, lint_mechanism
from systems.nova.schemas import InventionArtifact, InventionCandidate


def _is_number(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


def _jiggle_number(v: float, pct: float = 0.1) -> float:
    # ±pct jitter, bounded >= 0 for safety
    delta = abs(v) * pct
    return max(0.0, v + (delta if (hash((v, pct)) & 1) else -delta))


def _clone_mech(mech: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(mech or {"nodes": [], "edges": []})


class MechanismMutator:
    """
    Safe, SoC-friendly mechanism mutator.
    Guarantees: returns None or a *lint-valid* DAG.
    Mutations (conservative):
      - Numeric param jiggle (±10%)
      - Insert a 'batch' op after the first node if absent (simple edge)
      - Insert a 'critique' then 'repair' pair if none exist (linear suffix)
    """

    def _jiggle_params(self, mech: dict[str, Any]) -> dict[str, Any]:
        nodes = mech.get("nodes", [])
        changed = False
        for nx in nodes:
            params = nx.get("params") or {}
            for k, v in list(params.items()):
                if _is_number(v):
                    params[k] = _jiggle_number(float(v), 0.1)
                    changed = True
        return mech if changed else mech

    def _ensure_batch_after_first(self, mech: dict[str, Any]) -> dict[str, Any]:
        nodes = mech.get("nodes", [])
        if not nodes:
            return mech
        names = [str(n.get("name", "")).lower() for n in nodes]
        if "batch" in names:
            return mech
        # Add a batch node and edge from first node -> batch
        nodes.append({"name": "batch", "params": {"size": 3}})
        mech["edges"] = list(mech.get("edges", []))
        mech["edges"].append([0, len(nodes) - 1])
        return mech

    def _ensure_critique_repair_suffix(self, mech: dict[str, Any]) -> dict[str, Any]:
        nodes = mech.get("nodes", [])
        names = [str(n.get("name", "")).lower() for n in nodes]
        if "critique" in names and "repair" in names:
            return mech
        start_idx = len(nodes)
        nodes.append({"name": "critique", "params": {"mode": "socratic"}})
        nodes.append({"name": "repair", "params": {"strategy": "patch"}})
        # Append linear edges from last existing node (if any)
        edges = list(mech.get("edges", []))
        if start_idx >= 2:
            edges.append([start_idx - 1, start_idx])  # prev -> critique
            edges.append([start_idx, start_idx + 1])  # critique -> repair
        mech["edges"] = edges
        return mech

    def mutate_mechanism(self, mech: dict[str, Any]) -> dict[str, Any] | None:
        m = _clone_mech(mech)
        m = self._jiggle_params(m)
        m = self._ensure_batch_after_first(m)
        m = self._ensure_critique_repair_suffix(m)
        # Validate; if invalid, return None
        try:
            _ = lint_mechanism(m)
            return m
        except LintIssue:
            return None

    def augment_candidate(self, cand: InventionCandidate) -> InventionCandidate | None:
        spec = dict(cand.spec or {})
        mech = dict(spec.get("mechanism_graph") or {})
        mutated = self.mutate_mechanism(mech)
        if mutated is None:
            return None

        spec["mechanism_graph"] = mutated
        variant = cand.copy(deep=True)
        variant.candidate_id = f"{cand.candidate_id}_m{uuid4().hex[:6]}"
        variant.spec = spec
        variant.provenance = dict(variant.provenance or {})
        variant.provenance["augmented_from"] = cand.candidate_id
        variant.artifact = InventionArtifact(type="dsl", diffs=[])
        # Scores: keep conservative baseline; auction will decide later
        variant.scores = dict(variant.scores or {})
        variant.scores.setdefault("novelty", 0.8)
        return variant
