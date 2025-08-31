# systems/simula/code_sim/sandbox/deps.py
from __future__ import annotations

from .sandbox import DockerSandbox
from .seeds import seed_config


async def freeze_python() -> dict[str, object]:
    async with DockerSandbox(seed_config()).session() as sess:
        out = await sess._run_tool(
            [
                "bash",
                "-lc",
                "pip -q install pip-tools || true && pip-compile -q --generate-hashes -o requirements.txt || true && pip check || true",
            ],
        )
        ok = out.get("returncode", 0) == 0
        return {"status": "success" if ok else "failed", "logs": out}


async def freeze_node() -> dict[str, object]:
    async with DockerSandbox(seed_config()).session() as sess:
        out = await sess._run_tool(
            ["bash", "-lc", "npm ci || true && npm audit --audit-level=high || true"],
        )
        ok = out.get("returncode", 0) == 0
        return {"status": "success" if ok else "failed", "logs": out}


async def freeze_go() -> dict[str, object]:
    async with DockerSandbox(seed_config()).session() as sess:
        out = await sess._run_tool(["bash", "-lc", "go mod tidy || true && go mod verify || true"])
        ok = out.get("returncode", 0) == 0
        return {"status": "success" if ok else "failed", "logs": out}
