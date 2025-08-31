# systems/simula/policy/packs.py
from __future__ import annotations

import fnmatch
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # YAML optional; JSON works too.

_DIFF_PATH_RE = re.compile(r"^\+\+\+\s+b/(.+)$", re.M)


@dataclass
class PolicyFinding:
    rule: str
    severity: str
    message: str
    data: dict[str, Any]


@dataclass
class PolicyReport:
    ok: bool
    findings: list[PolicyFinding]

    def summary(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "findings": [asdict(f) for f in self.findings],
        }


@dataclass
class PolicyPack:
    name: str
    block_paths: list[str]
    require_tests_modified_on_code_change: bool
    max_changed_files: int | None = None
    max_hunk_size: int | None = None  # per @@ block (approx via +/- lines)


def _repo_root() -> Path:
    try:
        from systems.simula.config import settings  # type: ignore

        root = getattr(settings, "repo_root", None)
        if root:
            return Path(root).resolve()
    except Exception:
        pass
    for env in ("SIMULA_WORKSPACE_ROOT", "SIMULA_REPO_ROOT", "PROJECT_ROOT"):
        p = os.getenv(env)
        if p:
            return Path(p).resolve()
    return Path(".").resolve()


def _policy_dir() -> Path:
    return _repo_root() / ".simula" / "policy"


def _load_one(path: Path) -> PolicyPack:
    data: dict[str, Any]
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml") and yaml:
        data = yaml.safe_load(text) or {}
    else:
        data = json.loads(text)
    return PolicyPack(
        name=str(data.get("name") or path.stem),
        block_paths=list(data.get("block_paths") or []),
        require_tests_modified_on_code_change=bool(
            data.get("require_tests_modified_on_code_change", True),
        ),
        max_changed_files=data.get("max_changed_files"),
        max_hunk_size=data.get("max_hunk_size"),
    )


def load_policy_packs() -> list[PolicyPack]:
    d = _policy_dir()
    if not d.exists():
        return []
    packs: list[PolicyPack] = []
    for p in sorted(d.glob("**/*")):
        if p.is_file() and p.suffix.lower() in (".yaml", ".yml", ".json"):
            try:
                packs.append(_load_one(p))
            except Exception:
                # Skip malformed files
                continue
    return packs


def _paths_from_diff(diff_text: str) -> list[str]:
    return sorted(set(_DIFF_PATH_RE.findall(diff_text or "")))


def _hunks_from_diff(diff_text: str) -> list[list[str]]:
    hunks: list[list[str]] = []
    current: list[str] = []
    for ln in (diff_text or "").splitlines():
        if ln.startswith("@@ "):
            if current:
                hunks.append(current)
                current = []
        current.append(ln)
    if current:
        hunks.append(current)
    return hunks


def check_diff_against_policies(diff_text: str, packs: list[PolicyPack]) -> PolicyReport:
    paths = _paths_from_diff(diff_text)
    hunks = _hunks_from_diff(diff_text)

    findings: list[PolicyFinding] = []
    code_changed = any(
        p.endswith((".py", ".ts", ".js", ".java", ".go", ".rs", ".cpp", ".c", ".cs")) for p in paths
    )
    tests_changed = any(("tests/" in p) or p.endswith(("_test.py", "Test.java")) for p in paths)

    for pack in packs:
        # 1) Blocked paths
        for pat in pack.block_paths:
            banned = [p for p in paths if fnmatch.fnmatch(p, pat)]
            if banned:
                findings.append(
                    PolicyFinding(
                        rule=f"{pack.name}.block_paths",
                        severity="high",
                        message=f"Blocked paths matched pattern '{pat}'",
                        data={"paths": banned},
                    ),
                )

        # 2) Require tests modified if code changed
        if pack.require_tests_modified_on_code_change and code_changed and not tests_changed:
            findings.append(
                PolicyFinding(
                    rule=f"{pack.name}.require_tests_modified_on_code_change",
                    severity="medium",
                    message="Code changed but no tests were modified.",
                    data={"paths": paths},
                ),
            )

        # 3) Max changed files
        if isinstance(pack.max_changed_files, int) and pack.max_changed_files >= 0:
            if len(paths) > pack.max_changed_files:
                findings.append(
                    PolicyFinding(
                        rule=f"{pack.name}.max_changed_files",
                        severity="medium",
                        message=f"Changed files ({len(paths)}) exceed limit ({pack.max_changed_files}).",
                        data={"paths": paths, "limit": pack.max_changed_files},
                    ),
                )

        # 4) Max hunk size (approx: count +/- lines in each hunk)
        if isinstance(pack.max_hunk_size, int) and pack.max_hunk_size > 0:
            for idx, h in enumerate(hunks):
                changes = sum(1 for ln in h if ln.startswith("+") or ln.startswith("-"))
                if changes > pack.max_hunk_size:
                    findings.append(
                        PolicyFinding(
                            rule=f"{pack.name}.max_hunk_size",
                            severity="low",
                            message=f"Hunk {idx} has {changes} changed lines (limit {pack.max_hunk_size}).",
                            data={"hunk_index": idx, "changed_lines": changes},
                        ),
                    )

    return PolicyReport(ok=(len(findings) == 0), findings=findings)
