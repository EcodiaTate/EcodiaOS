# systems/axon/safety/contracts.py
from __future__ import annotations

from typing import Any, Callable, Iterable

from pydantic import BaseModel

from systems.axon.schemas import ActionResult, AxonIntent


class ContractVerdict(BaseModel):
    ok: bool
    reason: str = ""
    patches: dict[str, Any] = {}   # optional redactions/patches

PreRule = Callable[[AxonIntent], ContractVerdict]
PostRule = Callable[[AxonIntent, ActionResult], ContractVerdict]


class ContractsEngine:
    """
    Micro policy gates for pre/post conditions.
    Keep fully deterministic; zero-LLM.
    """
    def __init__(self, pre: Iterable[PreRule] | None = None, post: Iterable[PostRule] | None = None) -> None:
        self._pre = list(pre or [])
        self._post = list(post or [])

    # ------------ default rules (can be extended) ------------

    @staticmethod
    def _pre_require_rollback_for_high(intent: AxonIntent) -> ContractVerdict:
        tier = (getattr(intent, "risk_tier", "low") or "").lower()
        if tier in {"high", "extreme"} and not getattr(intent, "rollback_contract", None):
            return ContractVerdict(ok=False, reason="high_risk_requires_rollback")
        return ContractVerdict(ok=True)

    @staticmethod
    def _pre_budget_cap(intent: AxonIntent) -> ContractVerdict:
        cons = getattr(intent, "constraints", {}) or {}
        if isinstance(cons, dict) and cons.get("timeout_ms") and int(cons["timeout_ms"]) > 60_000:
            return ContractVerdict(ok=False, reason="timeout_exceeds_cap")
        return ContractVerdict(ok=True)

    @staticmethod
    def _post_require_outputs(_: AxonIntent, res: ActionResult) -> ContractVerdict:
        if not isinstance(res.outputs, dict):
            return ContractVerdict(ok=False, reason="outputs_not_dict")
        return ContractVerdict(ok=True)

    @staticmethod
    def _post_status_known(_: AxonIntent, res: ActionResult) -> ContractVerdict:
        if res.status not in {"ok", "fail", "blocked"}:
            return ContractVerdict(ok=False, reason="unknown_status")
        return ContractVerdict(ok=True)

    # ------------ API ------------

    def with_default_rules(self) -> "ContractsEngine":
        self._pre.extend([self._pre_require_rollback_for_high, self._pre_budget_cap])
        self._post.extend([self._post_require_outputs, self._post_status_known])
        return self

    def add_pre(self, rule: PreRule) -> None:
        self._pre.append(rule)

    def add_post(self, rule: PostRule) -> None:
        self._post.append(rule)

    def check_pre(self, intent: AxonIntent) -> ContractVerdict:
        for rule in self._pre:
            v = rule(intent)
            if not v.ok:
                return v
        return ContractVerdict(ok=True)

    def check_post(self, intent: AxonIntent, res: ActionResult) -> ContractVerdict:
        for rule in self._post:
            v = rule(intent, res)
            if not v.ok:
                return v
        return ContractVerdict(ok=True)
