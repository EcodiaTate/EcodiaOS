from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

auto_pipeline_router = APIRouter()

# Config roots
try:
    from systems.simula.config import settings  # type: ignore

    REPO = Path(getattr(settings, "repo_root", ".")).resolve()
    ART = Path(getattr(settings, "artifacts_root", REPO / ".simula")).resolve()
except Exception:  # pragma: no cover
    REPO = Path(".").resolve()
    ART = (REPO / ".simula").resolve()

# Reuse sibling endpoints without HTTP roundtrips
from .pr_bundle import proposal_bundle as _bundle  # type: ignore
from .proposal_verify import proposal_verify as _verify  # type: ignore
from .shadow_run import shadow_run as _shadow_run  # type: ignore


# ---------- helpers ----------
def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 900) -> dict[str, Any]:
    cp = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "rc": cp.returncode,
        "stdout": cp.stdout,
        "stderr": cp.stderr,
        "cmd": " ".join(cmd),
        "cwd": str(cwd or REPO),
    }


def _git(args: list[str]) -> dict[str, Any]:
    return _run(["git", *args], cwd=REPO, timeout=300)


def _slug_from_remote(url: str) -> str | None:
    # git@github.com:owner/repo.git -> owner/repo
    m = re.search(r"github\.com[:/](?P<slug>[^/]+/[^/\.]+)(?:\.git)?$", url.strip())
    return m.group("slug") if m else None


def _get_remote_slug() -> str | None:
    r = _git(["config", "--get", "remote.origin.url"])
    return _slug_from_remote((r["stdout"] or "").strip())


def _gh_api(
    path: str,
    payload: dict[str, Any],
    token: str | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    tok = token or os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN") or ""
    if not tok:
        return {"ok": False, "reason": "missing GH_TOKEN/GITHUB_TOKEN"}
    import json as _json
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        f"https://api.github.com{path}",
        data=_json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"token {tok}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "qora-auto-pipeline",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return {"ok": True, "status": resp.status, "json": json.loads(body) if body else {}}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "reason": e.read().decode("utf-8", "ignore")}
    except Exception as e:
        return {"ok": False, "reason": repr(e)}


# ---------- schema ----------
class AutoReq(BaseModel):
    proposal: dict[str, Any] = Field(..., description="Simula proposal: must include context.diff")
    branch_prefix: str = "simula/auto"
    base_ref: str = "origin/main"
    min_delta_cov: float = 0.0
    run_safety: bool = True
    use_xdist: bool = True
    open_pr: bool = True
    pr_title: str | None = None
    pr_body: str | None = None
    draft: bool = False
    reviewers: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=lambda: ["simula", "auto"])
    dry_run: bool = False


class AutoResp(BaseModel):
    ok: bool
    reason: str | None = None
    branch: str | None = None
    pr_url: str | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)
    gates: dict[str, Any] = Field(default_factory=dict)
    logs: dict[str, Any] = Field(default_factory=dict)


# ---------- route ----------
@auto_pipeline_router.post("/auto/pipeline", response_model=AutoResp)
async def auto_pipeline(req: AutoReq) -> AutoResp:
    prop = req.proposal or {}
    diff = ((prop.get("context") or {}).get("diff") or "").strip()
    if not diff:
        raise HTTPException(status_code=400, detail="proposal.context.diff missing")

    # 1) shadow run (gated)
    try:
        shadow_res = await _shadow_run.__wrapped__(
            {  # type: ignore
                "diff": diff,
                "min_delta_cov": req.min_delta_cov,
                "timeout_sec": 1200,
                "run_safety": req.run_safety,
                "use_xdist": req.use_xdist,
            },
        )
    except Exception as e:
        return AutoResp(ok=False, reason=f"shadow_run failed: {e!r}")

    if isinstance(shadow_res, dict):  # FastAPI can accept dict; normalize
        gates = shadow_res.get("gates", {})
        logs = shadow_res.get("logs", {})
        ok = bool(shadow_res.get("ok"))
    else:
        gates = getattr(shadow_res, "gates", {})
        logs = getattr(shadow_res, "logs", {})
        ok = bool(getattr(shadow_res, "ok", False))

    if not ok:
        return AutoResp(ok=False, reason="gates_failed_in_shadow", gates=gates, logs=logs)

    # 2) deeper verify (aggregated static/tests/Δcov)
    try:
        v = await _verify.__wrapped__(
            {  # type: ignore
                "diff": diff,
                "min_delta_cov": req.min_delta_cov,
                "run_safety": req.run_safety,
                "semgrep_config": "auto",
                "timeout_sec": 1200,
            },
        )
    except Exception as e:
        return AutoResp(ok=False, reason=f"proposal_verify failed: {e!r}", gates=gates, logs=logs)
    if isinstance(v, dict):
        ok2 = bool(v.get("ok"))
    else:
        ok2 = bool(getattr(v, "ok", False))
    if not ok2:
        return AutoResp(ok=False, reason="verify_failed", gates=gates, logs={"verify": v})

    # 3) build PR bundle artifacts
    try:
        b = await _bundle.__wrapped__(
            {  # type: ignore
                "proposal": prop,
                "include_snapshot": True,
                "min_delta_cov": req.min_delta_cov,
                "add_safety_summary": True,
            },
        )
        artifacts = (b if isinstance(b, dict) else b.__dict__).get("files", {})
    except Exception:
        artifacts = {}

    # 4) branch, apply, commit, push
    ts = int(time.time())
    branch = f"{req.branch_prefix}/{prop.get('proposal_id', 'prop')}-{ts}"
    logs = {"shadow": logs, "verify": v, "bundle": artifacts}

    if req.dry_run:
        cmds = [
            f"git fetch --all --prune",
            f"git checkout -b {branch} {req.base_ref}",
            f"git apply -p0 <<'PATCH'\n{diff}\nPATCH",
            f'git add -A && git commit -m "{req.pr_title or "Simula proposal"}"',
            f"git push -u origin {branch}",
        ]
        return AutoResp(
            ok=True,
            branch=branch,
            artifacts=artifacts,
            gates=gates,
            logs={"dry_run_cmds": cmds},
        )

    _ = _git(["fetch", "--all", "--prune"])
    c1 = _git(["checkout", "-b", branch, req.base_ref])
    if c1["rc"] != 0:
        return AutoResp(
            ok=False,
            reason=f"git checkout failed: {c1['stderr'] or c1['stdout']}",
            logs={"git_checkout": c1},
        )

    # Apply diff
    ap = _run(["git", "apply", "--index", "--whitespace=fix", "-p0"], cwd=REPO)
    if ap["rc"] != 0:
        ap2 = _run(["git", "apply", "--whitespace=fix", "-p0"], cwd=REPO)
        if ap2["rc"] != 0:
            return AutoResp(ok=False, reason="git apply failed", logs={"apply1": ap, "apply2": ap2})

    # Commit
    msg = req.pr_title or f"Simula proposal {prop.get('proposal_id', '')}".strip()
    cm = _git(["commit", "-m", msg])
    if cm["rc"] != 0:
        return AutoResp(
            ok=False,
            reason=f"git commit failed: {cm['stderr'] or cm['stdout']}",
            logs={"commit": cm},
        )

    # Push
    ps = _git(["push", "-u", "origin", branch])
    if ps["rc"] != 0:
        return AutoResp(
            ok=False,
            reason=f"git push failed: {ps['stderr'] or ps['stdout']}",
            logs={"push": ps},
        )

    pr_url: str | None = None
    if req.open_pr:
        # Try GitHub API (preferred), fallback to `gh` cli.
        slug = _get_remote_slug()
        title = msg
        body = req.pr_body or "Automated change proposed by Simula/Qora auto pipeline."
        if slug:
            api = _gh_api(
                f"/repos/{slug}/pulls",
                {
                    "title": title,
                    "head": branch,
                    "base": re.sub(r"^origin/", "", req.base_ref),
                    "body": body,
                    "draft": req.draft,
                },
            )
            if api.get("ok") and api.get("json", {}).get("html_url"):
                pr_url = api["json"]["html_url"]
                # reviewers & labels (best-effort)
                if req.reviewers:
                    _gh_api(
                        f"/repos/{slug}/pulls/{api['json']['number']}/requested_reviewers",
                        {"reviewers": req.reviewers},
                    )
                if req.labels:
                    _gh_api(
                        f"/repos/{slug}/issues/{api['json']['number']}/labels",
                        {"labels": req.labels},
                    )
            else:
                # fallback to gh cli if available
                if shutil.which("gh"):
                    args = [
                        "gh",
                        "pr",
                        "create",
                        "--title",
                        title,
                        "--body",
                        body,
                        "--base",
                        re.sub(r"^origin/", "", req.base_ref),
                        "--head",
                        branch,
                    ]
                    if req.draft:
                        args.append("--draft")
                    if req.labels:
                        args += sum([["--label", lb] for lb in req.labels], [])
                    res = _run(args, cwd=REPO, timeout=120)
                    if res["rc"] == 0 and "https://" in res["stdout"]:
                        pr_url = re.search(r"(https://\S+)", res["stdout"]).group(1)
                # if still no PR, just return success with branch
        # no slug → likely non-GitHub; caller can surface branch
    return AutoResp(
        ok=True,
        branch=branch,
        pr_url=pr_url,
        artifacts=artifacts,
        gates=gates,
        logs=logs,
    )
