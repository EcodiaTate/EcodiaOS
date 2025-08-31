# systems/simula/code_sim/evaluators/security.py
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SecurityGateResult:
    ok: bool
    findings: list[str]

    def summary(self) -> dict[str, object]:
        return {"ok": self.ok, "findings": self.findings}


SECRET_RX = re.compile(
    r'(api[_-]?key|secret|token)\s*[:=]\s*[\'"][A-Za-z0-9_\-]{16,}[\'"]|Bearer\s+[A-Za-z0-9._\-]{20,}',
    re.I,
)
CREDENTIAL_FILE_HINT = re.compile(r"(id_rsa|aws_credentials|netrc|\.pypirc|\.npmrc)", re.I)
LICENSE_BLOCKLIST = {"AGPL-3.0", "SSPL-1.0"}  # extend per org policy


def scan_diff_for_secrets(diff_text: str) -> SecurityGateResult:
    findings: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("+") and SECRET_RX.search(line):
            findings.append(f"Potential secret in line: {line[:200]}")
    return SecurityGateResult(ok=(len(findings) == 0), findings=findings)


def scan_diff_for_disallowed_licenses(diff_text: str) -> SecurityGateResult:
    findings: list[str] = []
    for lic in LICENSE_BLOCKLIST:
        if lic in diff_text:
            findings.append(f"Disallowed license reference detected: {lic}")
    return SecurityGateResult(ok=(len(findings) == 0), findings=findings)


def scan_diff_for_credential_files(diff_text: str) -> SecurityGateResult:
    findings: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("+++ b/") and CREDENTIAL_FILE_HINT.search(line):
            findings.append(f"Suspicious file added/modified: {line[6:]}")
    return SecurityGateResult(ok=(len(findings) == 0), findings=findings)
