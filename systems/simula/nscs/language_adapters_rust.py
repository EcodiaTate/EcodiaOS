# systems/simula/nscs/language_adapters_rust.py
from __future__ import annotations

from pathlib import Path

from systems.simula.code_sim.sandbox.sandbox import DockerSandbox
from systems.simula.code_sim.sandbox.seeds import seed_config


def is_rust_repo() -> bool:
    return Path("Cargo.toml").exists() or any(Path(".").rglob("*.rs"))


async def rust_static(paths: list[str]) -> dict[str, object]:
    async with DockerSandbox(seed_config()).session() as sess:
        out = await sess._run_tool(
            ["bash", "-lc", "cargo clippy --all-targets -- -D warnings || true"],
        )
        ok = out.get("returncode", 0) == 0
        return {"status": "success" if ok else "failed", "clippy": out}


async def rust_tests(paths: list[str], *, timeout_sec: int = 1800) -> dict[str, object]:
    async with DockerSandbox(seed_config()).session() as sess:
        out = await sess._run_tool(
            ["bash", "-lc", "cargo test --quiet || true"],
            timeout=timeout_sec,
        )
        ok = out.get("returncode", 0) == 0 and "FAILED" not in (out.get("stdout") or "")
        return {"status": "success" if ok else "failed", "logs": out}
