from __future__ import annotations

from pydantic import BaseModel

from systems.nova.eval.cost import estimate_cost_ms
from systems.nova.eval.metrics import fae_composite, mechanism_complexity, risk_hint
from systems.nova.proof.pcc import ProofResult, ProofVM
from systems.nova.schemas import InventionCandidate


class EvalRunner(BaseModel):
    """
    SoC-compliant evaluator:
      - No selection or learning.
      - Attaches conservative, deterministic metrics if missing.
      - Runs PCC checks and records result in evidence (does not drop candidates).
      - Never mutates obligations/spec beyond adding evidence & missing scores.
    """

    _pcc: ProofVM = ProofVM()

    async def run_tests(self, candidates: list[InventionCandidate]) -> list[InventionCandidate]:
        out: list[InventionCandidate] = []
        for c in candidates:
            spec = dict(c.spec or {})
            mech = dict(spec.get("mechanism_graph") or {})
            scores = dict(c.scores or {})
            evidence = dict(c.evidence or {})

            # 1) PCC: annotate result (do not filter here)
            try:
                res: ProofResult = self._pcc.check(
                    capability_spec=spec.get("capability_spec", {}),
                    obligations=c.obligations or {},
                    evidence=evidence,
                )
                evidence["pcc"] = {"ok": res.ok, "violations": list(res.violations or [])}
            except Exception as e:
                # Robustness: record the failure without breaking evaluate
                evidence["pcc"] = {"ok": False, "error": str(e)}

            # 2) Metrics: only fill if caller/playbook did not set them
            if "fae" not in scores:
                scores["fae"] = fae_composite(mech)
            if "risk" not in scores:
                scores["risk"] = risk_hint(mech)
            if "complexity" not in scores:
                scores["complexity"] = mechanism_complexity(mech)
            if "cost_ms" not in scores or not scores["cost_ms"]:
                scores["cost_ms"] = float(estimate_cost_ms(mech))

            # 3) Persist back onto the candidate
            c.scores = scores
            c.evidence = evidence
            out.append(c)

        return out
