# systems/simula/agents/security.py  (upgrade)
from __future__ import annotations

from typing import Any

from systems.simula.code_sim.evaluators.security import (
    scan_diff_for_credential_files,
    scan_diff_for_disallowed_licenses,
    scan_diff_for_secrets,
)

from .base import BaseAgent


class SecurityAgent(BaseAgent):
    async def execute(self, task: dict[str, Any]) -> dict[str, Any]:
        diff = task.get("diff") or ""
        f1 = scan_diff_for_secrets(diff)
        f2 = scan_diff_for_disallowed_licenses(diff)
        f3 = scan_diff_for_credential_files(diff)
        ok = f1.ok and f2.ok and f3.ok
        return {
            "passed": ok,
            "findings": {"secrets": f1.summary(), "licenses": f2.summary(), "creds": f3.summary()},
        }
