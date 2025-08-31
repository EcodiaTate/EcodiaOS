from __future__ import annotations


class SpecValidators:
    """
    Static checks that proposals must satisfy before EVO will publish a bid.
    These are not learnable rules; just guard-rails for safety and clarity.
    """

    REQUIRED_OBLIGATIONS = ("temporal", "resource")

    def check_obligation_presence(self, obligations: dict[str, list[dict]]) -> list[str]:
        issues: list[str] = []
        for k in self.REQUIRED_OBLIGATIONS:
            if k not in obligations or len(obligations[k]) == 0:
                issues.append(f"missing_obligation_kind:{k}")
        return issues

    def check_rollback_contract(self, rollback: dict[str, str]) -> list[str]:
        issues: list[str] = []
        if rollback.get("strategy") not in {"patch_reversal_and_config_restore"}:
            issues.append("rollback.strategy.unsupported")
        if not rollback.get("checks"):
            issues.append("rollback.checks.missing")
        return issues
