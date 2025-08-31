# systems/simula/vcs/pr_manager.py
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from systems.simula.code_sim.sandbox.sandbox import DockerSandbox
from systems.simula.code_sim.sandbox.seeds import seed_config
from systems.simula.review.pr_templates import render_pr_body


@dataclass
class PROpenResult:
    status: str
    branch: str
    title: str
    body: str
    web_url: str | None


async def open_pr(
    diff_text: str,
    *,
    title: str,
    evidence: dict[str, object] | None = None,
    base: str = "main",
) -> PROpenResult:
    branch = f"simula/{uuid.uuid4().hex[:8]}"
    async with DockerSandbox(seed_config()).session() as sess:
        await sess._run_tool(
            ["bash", "-lc", f"git checkout -B {branch} {base} || git checkout -B {branch} || true"],
        )
        ok = await sess.apply_unified_diff(diff_text)
        if not ok:
            return PROpenResult(status="failed", branch=branch, title=title, body="", web_url=None)
        await sess._run_tool(
            ["bash", "-lc", f"git add -A && git commit -m {json.dumps(title)} || true"],
        )
        # push best-effort (might be a dry-run sandbox)
        await sess._run_tool(["bash", "-lc", "git push -u origin HEAD || true"])
    body = render_pr_body(title=title, evidence=evidence or {})
    # return a dry-run result; actual URL may be created by CI bot
    return PROpenResult(status="created", branch=branch, title=title, body=body, web_url=None)
