# systems/simula/agent/tools_extra.py
from __future__ import annotations

from typing import Any

from systems.simula.artifacts.package import create_artifact_bundle
from systems.simula.ci.pipelines import render_ci
from systems.simula.ops.glue import quick_impact_and_cov, quick_policy_gate
from systems.simula.vcs.commit_msg import render_conventional_commit, title_from_evidence
from systems.simula.vcs.pr_manager import open_pr


async def tool_open_pr(params: dict[str, Any]) -> dict[str, Any]:
    diff: str = params.get("diff") or ""
    title: str = params.get("title") or "Simula Proposal"
    evidence: dict[str, Any] = params.get("evidence") or {}
    base: str = params.get("base") or "main"
    res = await open_pr(diff, title=title, evidence=evidence, base=base)
    return {
        "status": res.status,
        "branch": res.branch,
        "title": res.title,
        "body": res.body,
        "web_url": res.web_url,
    }


async def tool_package_artifacts(params: dict[str, Any]) -> dict[str, Any]:
    pid: str = params.get("proposal_id") or "unknown"
    evidence: dict[str, Any] = params.get("evidence") or {}
    extra: list[str] = params.get("extra_paths") or []
    out = create_artifact_bundle(proposal_id=pid, evidence=evidence, extra_paths=extra)
    return {
        "status": "success",
        "bundle": {"path": out.path, "manifest": out.manifest_path, "sha256": out.sha256},
    }


async def tool_policy_gate(params: dict[str, Any]) -> dict[str, Any]:
    diff: str = params.get("diff") or ""
    return quick_policy_gate(diff)


async def tool_impact_cov(params: dict[str, Any]) -> dict[str, Any]:
    diff: str = params.get("diff") or ""
    return quick_impact_and_cov(diff)


async def tool_render_ci(params: dict[str, Any]) -> dict[str, Any]:
    provider: str = params.get("provider") or "github"
    use_xdist: bool = bool(params.get("use_xdist", True))
    return {"status": "success", "yaml": render_ci(provider, use_xdist=use_xdist)}


async def tool_commit_title(params: dict[str, Any]) -> dict[str, Any]:
    evidence: dict[str, Any] = params.get("evidence") or {}
    title = title_from_evidence(evidence)
    return {"status": "success", "title": title}


async def tool_conventional_commit(params: dict[str, Any]) -> dict[str, Any]:
    type_ = params.get("type") or "chore"
    scope = params.get("scope")
    subject = params.get("subject") or "update"
    body = params.get("body")
    return {
        "status": "success",
        "message": render_conventional_commit(type_=type_, scope=scope, subject=subject, body=body),
    }
