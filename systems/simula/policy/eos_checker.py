# systems/simula/policy/eos_checker.py  (extended loader)
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PolicyFinding:
    ok: bool
    rule_id: str
    message: str


@dataclass
class PolicyReport:
    ok: bool
    findings: list[PolicyFinding]

    def summary(self) -> dict[str, object]:
        return {"ok": self.ok, "findings": [f.__dict__ for f in self.findings]}


def load_policy_packs(paths: list[str] | None = None) -> list[dict[str, object]]:
    packs: list[dict[str, object]] = []
    roots = paths or ["systems/simula/policy/packs", ".simula/policies"]
    for r in roots:
        pr = Path(r)
        if not pr.exists():
            continue
        for p in pr.glob("*.json"):
            try:
                packs.extend(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                continue
    return packs


def check_diff_against_policies(diff_text: str, policies: list[dict[str, object]]) -> PolicyReport:
    findings: list[PolicyFinding] = []
    blocks = diff_text.splitlines()
    for pol in policies or []:
        rid = str(pol.get("id") or "rule")
        patt = re.compile(str(pol.get("pattern") or r"$^"), re.I | re.M)
        when = str(pol.get("when") or "added").lower()
        msg = str(pol.get("message") or f"Policy violation: {rid}")
        matched = False
        if when == "added":
            for ln in blocks:
                if ln.startswith("+") and not ln.startswith("+++"):
                    if patt.search(ln[1:]):
                        matched = True
                        break
        else:
            if patt.search(diff_text):
                matched = True
        if matched:
            findings.append(PolicyFinding(ok=False, rule_id=rid, message=msg))
    return PolicyReport(ok=(len(findings) == 0), findings=findings)
