# systems/simula/format/autoformat.py
from __future__ import annotations

from pathlib import Path

from systems.simula.code_sim.sandbox.sandbox import DockerSandbox
from systems.simula.code_sim.sandbox.seeds import seed_config


async def autoformat_changed(paths: list[str]) -> dict[str, object]:
    """
    Best-effort, language-aware formatting for changed files.
    """
    exts = {Path(p).suffix for p in paths}
    cmds = []
    if any(e in {".py"} for e in exts):
        cmds += [
            "ruff check . --fix || true",
            "python -m black . || true",
            "python -m isort . || true",
        ]
    if any(e in {".js", ".jsx", ".ts", ".tsx", ".json", ".md", ".css"} for e in exts):
        cmds += ["npx -y prettier -w . || true"]
    if any(e in {".go"} for e in exts):
        cmds += ["gofmt -w . || true"]
    if any(e in {".java"} for e in exts):
        cmds += ["./gradlew spotlessApply || true || true"]
    if any(e in {".rs"} for e in exts):
        cmds += ["cargo fmt || true"]
    logs = []
    async with DockerSandbox(seed_config()).session() as sess:
        for cmd in cmds:
            logs.append(await sess._run_tool(["bash", "-lc", cmd]))
    return {"status": "success", "commands": cmds, "logs": logs}
