# systems/simula/nscs/language_adapters.py  (extend dispatch to Rust)
from __future__ import annotations

from pathlib import Path

from systems.simula.code_sim.sandbox.sandbox import DockerSandbox
from systems.simula.code_sim.sandbox.seeds import seed_config

from .language_adapters_go import go_static, go_tests, is_go_repo
from .language_adapters_java import is_java_repo, java_static, java_tests
from .language_adapters_rust import is_rust_repo, rust_static, rust_tests


def _is_node_repo() -> bool:
    return Path("package.json").exists()


def _is_python_repo() -> bool:
    return any(Path(".").rglob("*.py"))


async def _python_static(paths: list[str]) -> dict[str, object]:
    async with DockerSandbox(seed_config()).session() as sess:
        ruff = await sess._run_tool(["bash", "-lc", "ruff check . || true"])
        mypy = await sess._run_tool(["bash", "-lc", "mypy --hide-error-context --pretty . || true"])
        ok = ruff.get("returncode", 1) == 0 and mypy.get("returncode", 1) == 0
        return {"status": "success" if ok else "failed", "ruff": ruff, "mypy": mypy}


async def _python_tests(paths: list[str], *, timeout_sec: int) -> dict[str, object]:
    async with DockerSandbox(seed_config()).session() as sess:
        out = await sess._run_tool(
            [
                "bash",
                "-lc",
                "pytest -q --maxfail=1 --disable-warnings " + " ".join(paths) + " || true",
            ],
            timeout=timeout_sec,
        )
        ok = out.get("returncode", 0) == 0 and "failed" not in (out.get("stdout") or "")
        return {"status": "success" if ok else "failed", "logs": out}


async def _node_static(paths: list[str]) -> dict[str, object]:
    async with DockerSandbox(seed_config()).session() as sess:
        out = await sess._run_tool(["bash", "-lc", "npx -y eslint . || true"])
        ok = out.get("returncode", 0) == 0
        return {"status": "success" if ok else "failed", "eslint": out}


async def _node_tests(paths: list[str], *, timeout_sec: int) -> dict[str, object]:
    async with DockerSandbox(seed_config()).session() as sess:
        cmd = "npx jest -w 4 --ci --silent || npm test --silent || true"
        out = await sess._run_tool(["bash", "-lc", cmd], timeout=timeout_sec)
        ok = out.get("returncode", 0) == 0 and "failed" not in (out.get("stdout") or "")
        return {"status": "success" if ok else "failed", "logs": out}


async def static_check(paths: list[str]) -> dict[str, object]:
    if is_rust_repo():
        return await rust_static(paths)
    if is_go_repo():
        return await go_static(paths)
    if is_java_repo():
        return await java_static(paths)
    if _is_python_repo():
        return await _python_static(paths)
    if _is_node_repo():
        return await _node_static(paths)
    return {"status": "success", "note": "no static adapter matched"}


async def run_tests(paths: list[str], *, timeout_sec: int = 900) -> dict[str, object]:
    if is_rust_repo():
        return await rust_tests(paths, timeout_sec=timeout_sec)
    if is_go_repo():
        return await go_tests(paths, timeout_sec=timeout_sec)
    if is_java_repo():
        return await java_tests(paths, timeout_sec=timeout_sec)
    if _is_python_repo():
        return await _python_tests(paths, timeout_sec=timeout_sec)
    if _is_node_repo():
        return await _node_tests(paths, timeout_sec=timeout_sec)
    return {"status": "success", "note": "no test adapter matched"}
