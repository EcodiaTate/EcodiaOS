# systems/simula/risk/estimator.py
from __future__ import annotations

import re
from typing import Any

# Very light-weight heuristics. 0 (low) → 1 (high).
# Inputs: diff text + optional booleans/results from quick checks.

_DIFF_FILE_RE = re.compile(r"^\+\+\+ b/(.+)$", re.M)


def _changed_files(diff_text: str) -> list[str]:
    return sorted(set(_DIFF_FILE_RE.findall(diff_text or "")))


def _diff_magnitude(diff_text: str) -> tuple[int, int]:
    adds = sum(
        1 for ln in diff_text.splitlines() if ln.startswith("+") and not ln.startswith("+++")
    )
    dels = sum(
        1 for ln in diff_text.splitlines() if ln.startswith("-") and not ln.startswith("---")
    )
    return adds, dels


def estimate_risk(
    *,
    diff_text: str,
    policy_ok: bool | None = None,
    static_ok: bool | None = None,
    tests_ok: bool | None = None,
    delta_cov_pct: float | None = None,
    simulate_p_success: float | None = None,
) -> dict[str, Any]:
    files = _changed_files(diff_text)
    adds, dels = _diff_magnitude(diff_text)
    size = adds + dels

    # Feature scalers
    f_size = min(size / 2000.0, 1.0)  # >2000 lines ~ max risk contribution
    f_files = min(len(files) / 50.0, 1.0)  # >50 files ~ max
    f_cov = 0.0 if (delta_cov_pct is None) else max(0.0, (50.0 - float(delta_cov_pct)) / 50.0)
    f_policy = 0.5 if policy_ok is False else 0.0
    f_static = 0.3 if static_ok is False else 0.0
    f_tests = 0.6 if tests_ok is False else 0.0
    f_sim = 0.0
    if simulate_p_success is not None:
        # If the simulator predicted low success, raise risk
        f_sim = max(0.0, (0.7 - float(simulate_p_success)) / 0.7)  # p<0.7 ramps up

    # Weighted sum (tuned conservatively)
    risk = (
        0.30 * f_size
        + 0.20 * f_files
        + 0.20 * f_cov
        + 0.15 * f_tests
        + 0.10 * f_static
        + 0.10 * f_policy
        + 0.15 * f_sim
    )
    risk = max(0.0, min(1.0, risk))

    grade = (
        "low"
        if risk < 0.25
        else "moderate"
        if risk < 0.5
        else "elevated"
        if risk < 0.75
        else "high"
    )

    return {
        "risk": risk,
        "grade": grade,
        "features": {
            "size_lines": size,
            "files_changed": len(files),
            "delta_cov_pct": delta_cov_pct,
            "policy_ok": policy_ok,
            "static_ok": static_ok,
            "tests_ok": tests_ok,
            "simulate_p_success": simulate_p_success,
        },
        "files_sample": files[:20],
    }
