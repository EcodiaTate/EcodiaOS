# simula/code_sim/evaluators/tests.py
"""
Tests evaluator: discover + run unit/integration suites with structured output.

Public API
----------
run(step_or_objective, sandbox_session) -> dict
    {
      "ok": bool,                 # True iff all selected tests passed
      "unit": {"passed": int, "failed": int, "errors": int, "skipped": int, "ratio": float},
      "integration": {"..."}      # reserved (mirrors unit); may be empty
      "coverage_delta": float,    # heuristic bump if all pass
      "per_file_coverage": {str: float},
      "duration_s": float,
      "rc": int,
      "stdout": str,              # trimmed output
      "selected": ["tests/..."],  # what we actually ran
    }
"""

from __future__ import annotations

import glob
import os
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from pathlib import Path
from typing import Any

COV_XML = Path("/app/coverage.xml")

# ------------------------------- helpers ------------------------------------


def _is_mapping(x) -> bool:
    return isinstance(x, dict)


def _get(obj: Any, key: str, default=None):
    """Dict-or-attr getter."""
    if _is_mapping(obj):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _get_path(obj: Any, path: Sequence[str], default=None):
    """Nested dict-or-attr getter by path: ['acceptance','unit_tests','patterns']"""
    cur = obj
    for i, k in enumerate(path):
        if cur is None:
            return default
        cur = _get(cur, k, None if i < len(path) - 1 else default)
    return cur if cur is not None else default


def _extract_tests(step_or_objective: Any) -> list[str]:
    """
    Resolution order:
      1) step.tests
      2) (step.objective or objective).acceptance.tests
      3) (..).acceptance.unit_tests.patterns
      4) (..).acceptance.unit_tests.paths
    """
    # step override
    tests = _get(step_or_objective, "tests", None)
    if not tests:
        carrier = _get(step_or_objective, "objective", None) or step_or_objective
        acc = _get(carrier, "acceptance", {}) or {}
        tests = (
            _get(acc, "tests", None)
            or _get_path(acc, ["unit_tests", "patterns"], None)
            or _get_path(acc, ["unit_tests", "paths"], None)
            or []
        )
    # normalize to list[str]
    if isinstance(tests, str | Path):
        tests = [str(tests)]
    elif not isinstance(tests, list):
        tests = list(tests) if tests else []
    return [str(t) for t in tests if t]


def _expand_test_selection(patterns: list[str]) -> list[str]:
    """
    Expand globs so pytest receives concrete paths. If nothing expands, keep the
    original token (pytest can still collect from a directory name).
    """
    selected: list[str] = []
    for pat in patterns:
        matches = sorted(glob.glob(pat, recursive=True))
        if matches:
            selected.extend(matches)
        else:
            selected.append(pat)

    # Sensible fallback if selection still empty
    if not selected:
        for candidate in ("tests", "test", "src/tests"):
            if os.path.exists(candidate):
                selected.append(candidate)
                break
        if not selected:
            selected = ["tests"]
    return selected


def _coverage_per_file() -> dict[str, float]:
    if not COV_XML.exists():
        return {}
    try:
        root = ET.fromstring(COV_XML.read_text(encoding="utf-8"))
        out: dict[str, float] = {}
        for cls in root.findall(".//class"):
            fname = cls.attrib.get("filename", "")
            lines = cls.findall("./lines/line")
            if not lines:
                continue
            total = len(lines)
            hit = sum(1 for l in lines if l.attrib.get("hits", "0") != "0")
            out[fname] = (hit / total) if total else 0.0
        return out
    except Exception:
        return {}


_SUMMARY = re.compile(
    r"(?:(?P<passed>\d+)\s+passed)|"
    r"(?:(?P<failed>\d+)\s+failed)|"
    r"(?:(?P<errors>\d+)\s+errors?)|"
    r"(?:(?P<skipped>\d+)\s+skipped)",
    re.IGNORECASE,
)


def _parse_counts(txt: str) -> dict[str, int]:
    d = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    for m in _SUMMARY.finditer(txt or ""):
        for k in d:
            v = m.group(k)
            if v:
                d[k] += int(v)
    return d


def _ratio(passed: int, total: int) -> float:
    return 1.0 if total == 0 else max(0.0, min(1.0, passed / total))


# --------------------------------- API --------------------------------------


def run(step_or_objective: Any, sandbox_session) -> dict[str, Any]:
    """
    Execute pytest inside the provided sandbox session.

    - Accepts either a `step` or an `objective` (dict or object).
    - Selects tests per resolution order above.
    - Produces coverage.xml and parses per-file coverage.

    Returns the structured dict documented in the module docstring.
    """
    tests = _expand_test_selection(_extract_tests(step_or_objective))

    # Pytest invocation:
    # - quiet
    # - stop at first failure (fast signal for iter loops)
    # - disable warnings clutter
    # - coverage xml written to /app/coverage.xml (COV_XML)
    cmd = [
        "pytest",
        "-q",
        "--maxfail=1",
        "--disable-warnings",
        "--cov=.",
        f"--cov-report=xml:{COV_XML}",
        *tests,
    ]

    t0 = time.time()
    # NOTE: sandbox_session.run is assumed to be synchronous here.
    # If your sandbox API is async, wrap with anyio/run_sync or adjust call sites.
    rc, out = sandbox_session.run(cmd, timeout=1800)
    dur = time.time() - t0

    # Normalize output to str
    if isinstance(out, bytes | bytearray):
        try:
            out = out.decode("utf-8", errors="replace")
        except Exception:
            out = str(out)

    counts = _parse_counts(out)
    total = counts["passed"] + counts["failed"] + counts["errors"]
    ratio = _ratio(counts["passed"], total)
    ok = (rc == 0) and (ratio == 1.0)

    # Simple heuristic coverage bump if everything green and non-trivial
    cov_delta = 0.05 if ok and total > 0 else 0.0
    per_file = _coverage_per_file()

    return {
        "ok": ok,
        "unit": {**counts, "ratio": ratio},
        "integration": {},
        "coverage_delta": cov_delta,
        "per_file_coverage": per_file,
        "duration_s": dur,
        "rc": rc,
        "stdout": (out or "")[-20000:],  # trim to keep artifacts small
        "selected": tests,
    }
