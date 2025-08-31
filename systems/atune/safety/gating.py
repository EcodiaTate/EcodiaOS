# systems/atune/safety/gating.py
from __future__ import annotations

from dataclasses import dataclass

try:
    # Optional: prefer your existing hints client if present
    from systems.synapse.sdk.hints_client import SynapseHintsClient  # type: ignore
except Exception:
    SynapseHintsClient = None  # type: ignore


@dataclass(frozen=True)
class EscalationReason:
    code: str
    detail: str


@dataclass
class GateVerdict:
    ok: bool
    escalate: bool
    reason: EscalationReason | None
    alpha_used: float
    per_head_alpha: dict[str, float]
    head_pvals: dict[str, float]


class ConformalGate:
    """
    Wraps per-head p-values (already computed by your salience heads) and applies
    Synapse-hinted thresholds to decide whether to escalate to Unity.
    """

    def __init__(self, default_alpha: float = 0.1) -> None:
        self.default_alpha = max(1e-6, min(0.5, float(default_alpha)))

    async def _fetch_head_alphas(self, context: dict | None = None) -> dict[str, float]:
        """
        Pull per-head alphas from Synapse hints if available:
          domain: "conformal", key: "alpha_per_head" -> {head_name: alpha}
        Fallback: empty dict.
        """
        if SynapseHintsClient is None:
            return {}
        try:
            h = await SynapseHintsClient().get_hint(
                "conformal",
                "alpha_per_head",
                context=context or {},
            )
            m = h.get("value") or h  # tolerate either {"value":{...}} or plain dict
            return {str(k): max(1e-6, min(0.5, float(v))) for k, v in dict(m or {}).items()}
        except Exception:
            return {}

    async def decide(
        self,
        head_pvals: dict[str, float],
        context: dict | None = None,
    ) -> GateVerdict:
        """
        Inputs:
          head_pvals: {"RiskHead": 0.07, "NoveltyHead": 0.25, ...}
        Output:
          GateVerdict with escalate True if any p < alpha for that head.
        """
        per_head_alpha = await self._fetch_head_alphas(context=context)
        alpha_used = self.default_alpha

        # apply gating: any head with p < alpha(head) triggers escalation
        for head, p in head_pvals.items():
            a = per_head_alpha.get(head, self.default_alpha)
            if p < a:
                return GateVerdict(
                    ok=False,
                    escalate=True,
                    reason=EscalationReason(
                        code="OOD_CONFORMAL_HEAD",
                        detail=f"{head}: p={p:.4f} < alpha={a:.4f}",
                    ),
                    alpha_used=alpha_used,
                    per_head_alpha=per_head_alpha,
                    head_pvals=head_pvals,
                )

        return GateVerdict(
            ok=True,
            escalate=False,
            reason=None,
            alpha_used=alpha_used,
            per_head_alpha=per_head_alpha,
            head_pvals=head_pvals,
        )
