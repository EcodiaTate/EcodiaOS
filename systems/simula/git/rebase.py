# systems/simula/git/rebase.py
from __future__ import annotations

from systems.simula.code_sim.sandbox.sandbox import DockerSandbox
from systems.simula.code_sim.sandbox.seeds import seed_config


async def rebase_diff_onto_branch(
    diff_text: str,
    *,
    base: str = "origin/main",
) -> dict[str, object]:
    """
    Try to apply the diff on top of latest base via 3-way; return conflicts if any.
    """
    async with DockerSandbox(seed_config()).session() as sess:
        await sess._run_tool(["bash", "-lc", "git fetch --all --tags || true"])
        await sess._run_tool(
            [
                "bash",
                "-lc",
                f"git checkout -B simula-rebase {base} || git checkout -B simula-rebase || true",
            ],
        )
        ok = await sess.apply_unified_diff(diff_text, threeway=True)
        if ok:
            return {"status": "success", "conflicts": []}
        # try to detect conflicts
        out = await sess._run_tool(["bash", "-lc", "git diff --name-only --diff-filter=U || true"])
        files = (out.get("stdout") or "").strip().splitlines()
        return {"status": "conflicts", "conflicts": files}
