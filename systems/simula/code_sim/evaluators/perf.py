# simula/code_sim/evaluators/perf.py
"""
Performance evaluator: enforce per-objective pytest runtime budgets.

Objective keys used
-------------------
objective.acceptance.perf.pytest_duration_seconds: "<=30"  (string or number)

Public API
----------
run(step, sandbox_session) -> dict
    {
      "duration_s": float,
      "rc": int,
      "score": float,   # 1.0 if within budget; linearly decays below 0
      "stdout": str,
      "selected": ["tests/..."],
    }
"""

from __future__ import annotations

import glob
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

# ------------------------------- helpers ------------------------------------


def _is_mapping(x) -> bool:
    return isinstance(x, dict)


def _get(obj: Any, key: str, default=None):
    """Dict-or-attr getter."""
    if _is_mapping(obj):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _get_path(obj: Any, path: Sequence[str], default=None):
    """Nested getter by path: ['acceptance','unit_tests','patterns']"""
    cur = obj
    for i, k in enumerate(path):
        if cur is None:
            return default
        cur = _get(cur, k, None if i < len(path) - 1 else default)
    return cur if cur is not None else default


def _extract_tests(step_or_objective: Any) -> list[str]:
    """
    Resolution order (works for dicts or objects):
      1) step.tests
      2) (step.objective or objective).acceptance.tests
      3) (..).acceptance.unit_tests.patterns
      4) (..).acceptance.unit_tests.paths
      -> default ['tests'] if nothing provided
    """
    tests = _get(step_or_objective, "tests", None)
    if not tests:
        carrier = _get(step_or_objective, "objective", None) or step_or_objective
        acc = _get(carrier, "acceptance", {}) or {}
        tests = (
            _get(acc, "tests", None)
            or _get_path(acc, ["unit_tests", "patterns"], None)
            or _get_path(acc, ["unit_tests", "paths"], None)
        )
    if isinstance(tests, str | Path | bytes):
        if isinstance(tests, bytes):
            return [tests.decode(errors="replace")]
        return [str(tests)]
    if not tests:
        # Sensible fallback if not specified anywhere
        return ["tests"]
    return [str(t) for t in tests]


def _expand_tests(patterns: list[str]) -> list[str]:
    """
    Expand globs so pytest has concrete inputs. If a pattern does not match,
    keep the token (pytest can still collect from a directory name).
    """
    out: list[str] = []
    for pat in patterns:
        matches = sorted(glob.glob(pat, recursive=True))
        if matches:
            out.extend(matches)
        else:
            out.append(pat)
    # Deduplicate while preserving order
    seen = set()
    uniq: list[str] = []
    for p in out:
        if p not in seen:
            uniq.append(p)
            seen.add(p)
    return uniq or ["tests"]


def _budget_seconds(objective: Any) -> float:
    """
    FIX: Parameter renamed to 'objective' for clarity.
    Reads acceptance.perf.pytest_duration_seconds.
    """
    perf = _get_path(objective, ["acceptance", "perf"], {}) or {}
    raw = _get(perf, "pytest_duration_seconds", "<=30")
    if isinstance(raw, int | float):
        return float(raw)
    try:
        s = str(raw).strip().lstrip("<=")
        return float(s)
    except Exception:
        return 30.0


def run(objective: dict, sandbox_session) -> dict[str, Any]:
    """
    FIX: Changed function signature from 'step' to 'objective' to match the caller.
    """
    tests = _expand_tests(_extract_tests(objective))
    budget = _budget_seconds(objective)

    cmd = ["pytest", "-q", "--disable-warnings", "--maxfail=1", *tests]

    t0 = time.time()
    rc, out = sandbox_session.run(cmd, timeout=max(60, int(budget * 5)))
    dur = time.time() - t0

    out_str = out.decode("utf-8", errors="replace") if isinstance(out, bytes) else str(out)
    score = 1.0 if dur <= budget else max(0.0, 1.0 - (dur - budget) / max(budget, 1.0))

    return {
        "duration_s": dur,
        "rc": int(rc),
        "score": round(float(score), 4),
        "stdout": out_str[-10000:],
        "selected": tests,
    }
