# systems/simula/search/portfolio_runner.py
from __future__ import annotations

import copy

from systems.simula.code_sim.evaluators.coverage_delta import compute_delta_coverage
from systems.simula.code_sim.evaluators.impact import compute_impact
from systems.simula.code_sim.sandbox.sandbox import DockerSandbox
from systems.simula.code_sim.sandbox.seeds import seed_config
from systems.simula.policy.eos_checker import check_diff_against_policies, load_policy_packs
from systems.simula.scoring.score import composite_score


async def evaluate_candidate(diff_text: str) -> dict[str, object]:
    """
    Minimal local evaluation: apply → pytest -k impact or full → static → cov → policy → score.
    """
    ev = {"hygiene": {}, "coverage_delta": {}, "policy": {}, "mutation": {}}
    impact = compute_impact(diff_text)
    async with DockerSandbox(seed_config()).session() as sess:
        ok = await sess.apply_unified_diff(diff_text)
        if not ok:
            return {"status": "rejected", "reason": "git apply failed"}
        # tests
        ok1, logs1 = await sess.run_pytest_select(["tests"], impact.k_expr or "", timeout=900)
        if not ok1:
            ok2, logs2 = await sess.run_pytest(["tests"], timeout=1500)
            ok1, _logs1 = ok2, logs2
        ev["hygiene"]["tests"] = "success" if ok1 else "failed"
        # static (python assumed here; multi-lang flows routed by higher-level adapters)
        ruff = await sess.run_ruff(["."])
        mypy = await sess.run_mypy(["."])
        ev["hygiene"]["static"] = (
            "success"
            if ruff.get("returncode", 1) == 0 and mypy.get("returncode", 1) == 0
            else "failed"
        )
        # coverage delta (best effort)
        try:
            _ = await sess.run_pytest_coverage(
                ["tests"],
                include=impact.changed or None,
                timeout=900,
            )
            ev["coverage_delta"] = compute_delta_coverage(diff_text).summary()
        except Exception:
            ev["coverage_delta"] = {"pct_changed_covered": 0.0}
        # policy packs
        pols = load_policy_packs()
        rep = check_diff_against_policies(diff_text, pols)
        ev["policy"] = rep.summary()
    # score
    s = composite_score(ev)
    return {"status": "scored", "evidence": ev, "score": s}


async def rank_portfolio(
    candidates: list[dict[str, object]],
    top_k: int = 3,
) -> list[dict[str, object]]:
    scored: list[tuple[float, dict[str, object]]] = []
    for c in candidates:
        res = await evaluate_candidate(c.get("diff", ""))
        if res.get("status") != "scored":
            continue
        c2 = copy.deepcopy(c)
        c2["evidence"] = res["evidence"]
        c2["score"] = res["score"]
        scored.append((c2["score"], c2))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]
