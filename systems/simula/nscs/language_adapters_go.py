# systems/simula/nscs/language_adapters_go.py
from __future__ import annotations

from pathlib import Path

from systems.simula.code_sim.sandbox.sandbox import DockerSandbox
from systems.simula.code_sim.sandbox.seeds import seed_config


def is_go_repo() -> bool:
    return Path("go.mod").exists() or any(Path(".").rglob("*.go"))


async def go_static(paths: list[str]) -> dict[str, object]:
    async with DockerSandbox(seed_config()).session() as sess:
        # golangci-lint if available, else go vet
        out = await sess._run_tool(
            [
                "bash",
                "-lc",
                "command -v golangci-lint >/dev/null 2>&1 && golangci-lint run || go vet ./... || true",
            ],
        )
        ok = out.get("returncode", 0) == 0
        return {"status": "success" if ok else "failed", "lint": out}


async def go_tests(paths: list[str], *, timeout_sec: int = 1200) -> dict[str, object]:
    async with DockerSandbox(seed_config()).session() as sess:
        out = await sess._run_tool(
            ["bash", "-lc", "go test ./... -count=1 || true"],
            timeout=timeout_sec,
        )
        ok = out.get("returncode", 0) == 0 and "FAIL" not in (out.get("stdout") or "")
        return {"status": "success" if ok else "failed", "logs": out}
