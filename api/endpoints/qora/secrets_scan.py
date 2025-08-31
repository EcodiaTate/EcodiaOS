from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

secrets_scan_router = APIRouter()

try:
    from systems.simula.config import settings  # type: ignore

    ROOT = Path(getattr(settings, "repo_root", ".")).resolve()
except Exception:  # pragma: no cover
    ROOT = Path(".").resolve()


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(cmd: list[str], timeout: int = 300) -> dict[str, Any]:
    try:
        cp = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        return {"rc": cp.returncode, "stdout": cp.stdout, "stderr": cp.stderr}
    except subprocess.TimeoutExpired:
        return {"rc": -1, "stdout": "", "stderr": "timeout"}


# Lightweight regex rules (fallback)
_RULES = [
    ("aws_access_key_id", re.compile(r"(?i)AKIA[0-9A-Z]{16}")),
    (
        "aws_secret_key",
        re.compile(r"(?i)aws(.{0,20})?(secret|access).{0,20}?['\"][A-Za-z0-9\/+]{40}['\"]"),
    ),
    ("gh_token", re.compile(r"ghp_[A-Za-z0-9]{36,}")),
    (
        "generic_api_key",
        re.compile(r"(?i)(api|token|secret|key).{0,8}['\"][A-Za-z0-9_\-]{20,}['\"]"),
    ),
    ("private_key", re.compile(r"-----BEGIN (?:RSA|DSA|EC|OPENSSH) PRIVATE KEY-----")),
]


class SecretsScanReq(BaseModel):
    paths: list[str] = Field(default_factory=lambda: ["."])
    use_heavy: bool = True  # try gitleaks/trufflehog if present
    limit: int = 5000


class SecretHit(BaseModel):
    rule: str
    path: str
    line: int
    excerpt: str


class SecretsScanResp(BaseModel):
    ok: bool
    hits: list[SecretHit] = Field(default_factory=list)
    tools: dict[str, Any] = Field(default_factory=dict)


@secrets_scan_router.post("/scan", response_model=SecretsScanResp)
async def secrets_scan(req: SecretsScanReq) -> SecretsScanResp:
    tools: dict[str, Any] = {}

    # Heavy scanners (best-effort)
    if req.use_heavy and _have("gitleaks"):
        out = _run(
            ["gitleaks", "detect", "--no-git", "--report-format", "json", "--report-path", "-"]
            + req.paths,
            timeout=300,
        )
        try:
            report = json.loads(out["stdout"] or "[]")
        except Exception:
            report = []
        tools["gitleaks"] = {"rc": out["rc"], "findings": len(report)}
        if report:
            # Flatten a few into hits
            hits = []
            for f in report:
                if len(hits) >= req.limit:
                    break
                hits.append(
                    SecretHit(
                        rule=f.get("Rule", "gitleaks"),
                        path=f.get("File", ""),
                        line=int(f.get("StartLine", 0)),
                        excerpt=(f.get("Match", "") or "")[:240],
                    ),
                )
            return SecretsScanResp(ok=True, hits=hits, tools=tools)

    if req.use_heavy and _have("trufflehog"):
        out = _run(["trufflehog", "filesystem", "--no-update", "--json", *req.paths], timeout=300)
        hits = []
        for line in (out["stdout"] or "").splitlines():
            try:
                j = json.loads(line)
                if (
                    j.get("SourceMetadata", {})
                    .get("Data", {})
                    .get("Filesystem", {})
                    .get("file", "")
                ):
                    path = j["SourceMetadata"]["Data"]["Filesystem"]["file"]
                    part = (j.get("Raw", "") or "")[:240]
                    hits.append(
                        SecretHit(
                            rule=j.get("DetectorName", "trufflehog"),
                            path=path,
                            line=0,
                            excerpt=part,
                        ),
                    )
                    if len(hits) >= req.limit:
                        break
            except Exception:
                continue
        if hits:
            tools["trufflehog"] = {"rc": out["rc"], "findings": len(hits)}
            return SecretsScanResp(ok=True, hits=hits, tools=tools)

    # Fallback regex sweep (fast)
    hits: list[SecretHit] = []
    for p, _, files in os.walk(ROOT):
        if ".git" in p or ".venv" in p or "node_modules" in p:
            continue
        for fn in files:
            try:
                full = Path(p, fn)
                txt = full.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for i, ln in enumerate(txt.splitlines(), 1):
                for name, pat in _RULES:
                    if pat.search(ln):
                        hits.append(
                            SecretHit(
                                rule=name,
                                path=str(full.relative_to(ROOT)),
                                line=i,
                                excerpt=ln.strip()[:240],
                            ),
                        )
                        if len(hits) >= req.limit:
                            return SecretsScanResp(ok=True, hits=hits, tools=tools)
    return SecretsScanResp(ok=True, hits=hits, tools=tools)
