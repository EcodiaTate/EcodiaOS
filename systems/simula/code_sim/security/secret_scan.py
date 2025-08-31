# systems/simula/code_sim/security/secret_scan.py
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Finding:
    path: str
    line: int
    snippet: str
    rule: str


AWS = re.compile(r"AKIA[0-9A-Z]{16}")
GH_PAT = re.compile(r"ghp_[A-Za-z0-9]{36}")
GENERIC_KEY = re.compile(r"(secret|token|api[_-]?key)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]", re.I)


def scan_text(path: str, text: str) -> list[Finding]:
    out: list[Finding] = []
    for i, ln in enumerate(text.splitlines(), start=1):
        if AWS.search(ln):
            out.append(Finding(path, i, ln.strip()[:120], "aws_key"))
        if GH_PAT.search(ln):
            out.append(Finding(path, i, ln.strip()[:120], "gh_pat"))
        if GENERIC_KEY.search(ln):
            out.append(Finding(path, i, ln.strip()[:120], "generic_key"))
    return out


def scan_diff_for_secrets(diff_text: str) -> dict[str, object]:
    findings: list[Finding] = []
    cur = ""
    for ln in diff_text.splitlines():
        if ln.startswith("+++ b/"):
            cur = ln[6:].strip()
        if ln.startswith("+") and not ln.startswith("+++"):
            findings.extend(scan_text(cur or "UNKNOWN", ln[1:]))
    return {
        "ok": len(findings) == 0,
        "findings": [f.__dict__ for f in findings],
        "summary": {"count": len(findings)},
    }
