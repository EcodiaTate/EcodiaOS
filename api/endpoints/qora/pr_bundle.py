from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

pr_bundle_router = APIRouter()

try:
    from systems.simula.config import settings  # type: ignore

    REPO = Path(getattr(settings, "repo_root", ".")).resolve()
    ART = Path(getattr(settings, "artifacts_root", REPO / ".simula")).resolve()
except Exception:  # pragma: no cover
    REPO = Path(".").resolve()
    ART = (REPO / ".simula").resolve()

# Soft deps (graceful if missing)
try:
    from systems.simula.code_sim.evaluators.coverage_delta import compute_delta_coverage
    from systems.simula.code_sim.evaluators.impact import compute_impact
except Exception:  # pragma: no cover
    compute_delta_coverage = None
    compute_impact = None


class BundleReq(BaseModel):
    proposal: dict[str, Any] = Field(
        ...,
        description="Simula proposal object (includes context.diff, evidence)",
    )
    include_snapshot: bool = True
    min_delta_cov: float = 0.0
    add_safety_summary: bool = True


class BundleResp(BaseModel):
    ok: bool
    files: dict[str, str]  # {"markdown": path, "json": path, "snapshot": path?}


def _write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def _md_escape(s: str) -> str:
    return s.replace("```", "\\`\\`\\`")


@pr_bundle_router.post("/proposal/bundle", response_model=BundleResp)
async def proposal_bundle(req: BundleReq) -> BundleResp:
    prop = req.proposal or {}
    diff = ((prop.get("context") or {}).get("diff") or "").strip()
    if not diff:
        raise HTTPException(status_code=400, detail="proposal.context.diff missing")

    # Compute impact + delta coverage (best-effort)
    k_expr = None
    changed = []
    cov_summary = {"pct_changed_covered": 0.0}
    if compute_impact:
        try:
            imp = compute_impact(diff, workspace_root=".")
            k_expr = imp.k_expr or None
            changed = imp.changed or []
        except Exception:
            pass
    if compute_delta_coverage:
        try:
            cov_summary = compute_delta_coverage(diff).summary()
        except Exception:
            pass

    # Safety summary best-effort (copy through if already present)
    safety = (
        ((prop.get("evidence") or {}).get("safety") or None) if req.add_safety_summary else None
    )

    # Build JSON payload
    payload = {
        "proposal": prop,
        "impact": {"k_expr": k_expr, "changed": changed},
        "coverage_delta": cov_summary,
        "safety": safety,
        "meta": {"created_at": int(time.time()), "min_delta_cov": req.min_delta_cov},
    }

    # Markdown report
    title = prop.get("proposal_id", "proposal")
    md = []
    md.append(f"# Proposal Bundle — {title}\n")
    md.append("## Impact\n")
    md.append(f"- Focus `-k`: `{k_expr or ''}`\n- Changed paths: `{', '.join(changed)}`\n")
    md.append("## Delta Coverage\n")
    md.append(f"- Changed lines covered: **{cov_summary.get('pct_changed_covered', 0.0):.2f}%**\n")
    if req.min_delta_cov:
        md.append(
            f"- Gate: {'PASS ✅' if cov_summary.get('pct_changed_covered', 0.0) >= req.min_delta_cov else 'FAIL ❌'} (≥ {req.min_delta_cov}%)\n",
        )
    if safety:
        md.append("## Safety (summary)\n")
        md.append("```json\n" + _md_escape(json.dumps(safety, indent=2)) + "\n```\n")
    md.append("## Diff\n```diff\n" + _md_escape(diff[:500000]) + "\n```\n")
    if prop.get("evidence"):
        md.append(
            "## Evidence\n```json\n"
            + _md_escape(json.dumps(prop["evidence"], indent=2))
            + "\n```\n",
        )

    # Paths
    out_dir = ART / "bundles"
    stamp = int(time.time())
    jpath = out_dir / f"{title}-{stamp}.json"
    mpath = out_dir / f"{title}-{stamp}.md"
    files: dict[str, str] = {}
    files["json"] = _write(jpath, json.dumps(payload, indent=2))
    files["markdown"] = _write(mpath, "".join(md))

    # Optional snapshot (using subset by diff)
    if req.include_snapshot:
        try:
            from .workspace_snapshot import snapshot as _snap  # reuse endpoint impl

            snap = await _snap.__wrapped__(
                {  # bypass FastAPI deps
                    "paths": [],
                    "diff": diff,
                    "include_tests": True,
                    "label": title,
                },
            )  # type: ignore
            if isinstance(snap, dict) and snap.get("file"):
                files["snapshot"] = snap["file"]
        except Exception:
            pass

    return BundleResp(ok=True, files=files)
