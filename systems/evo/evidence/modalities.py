from __future__ import annotations

from typing import Any

from core.utils.neo.cypher_query import cypher_query


class EvidenceModality:
    name: str = "base"

    async def run(self, **kwargs) -> dict[str, Any]:
        raise NotImplementedError


class DiffRiskModality(EvidenceModality):
    name = "diff_risk"

    async def run(self, *, patch_diff: str = "") -> dict[str, Any]:
        lines = patch_diff.splitlines()
        added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
        risky_patterns = int(any("except:" in l or "eval(" in l for l in lines))
        return {"loc_added": added, "loc_removed": removed, "risky_patterns": risky_patterns}


class InvariantsCheckModality(EvidenceModality):
    name = "invariants"

    async def run(
        self,
        *,
        obligations: dict[str, list[dict[str, dict[str, str]]]],
    ) -> dict[str, Any]:
        # Stub: mark obligations as "covered" if we have any rule per target.
        covered = sum(len(v) for v in obligations.values())
        return {"obligations_count": covered, "status": "neutral" if covered == 0 else "ok"}


class ForecastBacktestModality(EvidenceModality):
    name = "forecast"

    async def run(self, *, module: str, metric: str = "p95_latency_ms") -> dict[str, Any]:
        # Pull last N samples for naive AR(1)-like bound (minimal, offline)
        q = """
        MATCH (m:Module {name: $name})-[:HAS_METRIC]->(s:Sample)
        WHERE s.metric = $metric
        RETURN s.value AS v
        ORDER BY s.t ASC
        LIMIT 50
        """
        rows = await cypher_query(q, {"name": module, "metric": metric})
        vals = [float(r["v"]) for r in rows or []]
        if len(vals) < 5:
            return {"status": "insufficient_data"}
        mu = sum(vals) / len(vals)
        last = vals[-1]
        # crude mean-reversion window; just enough for dossier context
        bound = 0.5 * last + 0.5 * mu
        return {"status": "ok", "forecast_point": bound, "samples": len(vals)}
