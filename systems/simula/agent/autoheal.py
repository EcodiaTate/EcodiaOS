# systems/simula/agent/autoheal.py
# --- PROJECT SENTINEL UPGRADE ---
from __future__ import annotations

from typing import Any

from systems.simula.code_sim.sandbox.sandbox import DockerSandbox
from systems.simula.code_sim.sandbox.seeds import seed_config


async def _git_diff(sess) -> str:
    """Captures the git diff from within a sandbox session."""
    out = await sess._run_tool(["git", "diff", "--unified=2", "--no-color"])
    return out.get("stdout") or ""


async def auto_heal_after_static(changed_paths: list[str]) -> dict[str, Any]:
    """
    A best-effort, sandboxed auto-healing and diagnostics tool.
    It runs formatters/fixers and returns a proposed diff, along with mypy diagnostics.
    """
    cfg = seed_config()
    async with DockerSandbox(cfg).session() as sess:
        # Run fixers. These tools modify files in place inside the sandbox.
        await sess._run_tool([sess.python_exe, "-m", "ruff", "check", *changed_paths, "--fix"])
        await sess._run_tool([sess.python_exe, "-m", "black", *changed_paths])

        # Capture the changes made by the fixers as a diff.
        diff = await _git_diff(sess)

        # Run mypy to get type-checking diagnostics to inform the LLM.
        # This does not block or change the diff.
        mypy_result = await sess.run_mypy(changed_paths)

    if diff.strip():
        return {"status": "proposed", "diff": diff, "diagnostics": {"mypy": mypy_result}}

    return {"status": "noop", "diagnostics": {"mypy": mypy_result}}
