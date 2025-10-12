# simula/code_sim/evaluators/static.py
"""
Static suite: ruff (lint), mypy (types), bandit (security).

Public API
----------
run(objective, sandbox_session) -> dict
    {
      "ruff_ok": bool, "mypy_ok": bool, "bandit_ok": bool,
      "outputs": {"ruff": str, "mypy": str, "bandit": str}
    }
"""

from __future__ import annotations


def _run(sess, args, timeout):
    rc, out = sess.run(args, timeout=timeout)
    return (rc == 0), out


def run(objective, sandbox_session) -> dict:
    r_ok, r_out = _run(sandbox_session, ["ruff", "check", "."], timeout=1200)
    m_ok, m_out = _run(
        sandbox_session,
        ["mypy", "--hide-error-context", "--pretty", "."],
        timeout=1800,
    )
    b_ok, b_out = _run(sandbox_session, ["bandit", "-q", "-r", "."], timeout=1800)
    # Treat any High severity finding as a failure even if rc=0 (some bandit configs do that)
    if "SEVERITY: High" in b_out:
        b_ok = False
    return {
        "ruff_ok": r_ok,
        "mypy_ok": m_ok,
        "bandit_ok": b_ok,
        "outputs": {"ruff": r_out[-10000:], "mypy": m_out[-10000:], "bandit": b_out[-10000:]},
    }
