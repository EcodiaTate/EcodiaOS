# systems/simula/code_sim/evaluators/coverage_delta.py
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from core.utils.diff import changed_paths_from_unified_diff


@dataclass
class DeltaCoverage:
    changed_files: list[str]
    changed_lines: dict[str, set[int]]
    covered_changed_lines: dict[str, set[int]]
    pct_changed_covered: float

    def summary(self) -> dict[str, object]:
        total_changed = sum(len(v) for v in self.changed_lines.values()) or 0
        total_cov = sum(len(v) for v in self.covered_changed_lines.values()) or 0
        pct = 100.0 * (total_cov / total_changed) if total_changed else 0.0
        return {
            "changed_files": self.changed_files,
            "changed_lines_total": total_changed,
            "covered_changed_lines_total": total_cov,
            "pct_changed_covered": round(pct, 2),
        }


_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.M)


def _changed_lines_from_unified_diff(diff: str) -> dict[str, set[int]]:
    """
    Extract changed line numbers per file from a unified diff (for the 'b/' side).
    """
    changed: dict[str, set[int]] = {}
    current_file: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:].strip()
            changed.setdefault(current_file, set())
            continue
        if current_file is None:
            # Wait for file header first
            continue
        m = _HUNK_HEADER.match(line)
        if m:
            start = int(m.group(1))
            int(m.group(2) or "1")
            cur = start
            continue  # move to next lines; adds come next
        if line.startswith("+") and not line.startswith("+++"):
            # added line in new file; record then increment counter
            try:
                changed[current_file].add(cur)
                cur += 1
            except Exception:
                # cur not initialized yet (malformed diff) — ignore
                pass
        elif line.startswith("-") and not line.startswith("---"):
            # removed line in old file; new-file line number does not advance
            pass
        else:
            # context line advances both sides
            try:
                cur += 1
            except Exception:
                pass
    return changed


def load_coverage_json(path: str = "coverage.json") -> dict[str, object]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def compute_delta_coverage(
    diff_text: str,
    coverage_json_path: str = "coverage.json",
) -> DeltaCoverage:
    """
    Compute coverage over *changed lines only* using coverage.py JSON.
    """
    changed_files = [p for p in changed_paths_from_unified_diff(diff_text) if p.endswith(".py")]
    changed_lines = _changed_lines_from_unified_diff(diff_text)

    cov = load_coverage_json(coverage_json_path)
    files = (cov.get("files") or {}) if isinstance(cov, dict) else {}
    covered_changed: dict[str, set[int]] = {f: set() for f in changed_files}

    for f in changed_files:
        rec = files.get(str(Path(f).resolve()))
        if not rec:
            # coverage.py sometimes stores paths as relative; try both
            rec = files.get(f)
        if not rec:
            continue
        executed = set(rec.get("executed_lines") or [])
        for ln in changed_lines.get(f, set()):
            if ln in executed:
                covered_changed.setdefault(f, set()).add(ln)

    total_changed = sum(len(v) for v in changed_lines.values()) or 0
    total_cov = sum(len(v) for v in covered_changed.values()) or 0
    pct = (100.0 * total_cov / total_changed) if total_changed else 0.0

    return DeltaCoverage(
        changed_files=changed_files,
        changed_lines=changed_lines,
        covered_changed_lines=covered_changed,
        pct_changed_covered=pct,
    )
