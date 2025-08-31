# systems/simula/code_sim/sandbox/sandbox.py
# --- PROJECT SENTINEL UPGRADE ---
from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from systems.simula.config import settings

# --- Constants and Helpers ---
REPO_ROOT = Path(settings.repo_root).resolve()


@dataclass
class SandboxConfig:
    """Configuration for a sandbox session."""

    mode: str = "docker"
    image: str = "python:3.11-slim"
    timeout_sec: int = 1800
    workdir: str = "."
    env_allow: list[str] = field(default_factory=list)
    env_set: dict[str, str] = field(default_factory=dict)
    pip_install: list[str] = field(default_factory=list)
    # Docker-specific
    cpus: str = "2.0"
    memory: str = "4g"
    network: str | None = "bridge"
    mount_rw: list[str] = field(default_factory=list)


class BaseSession:
    """Abstract base class for Docker and Local sessions."""

    def __init__(self, cfg: SandboxConfig):
        self.cfg = cfg
        self.repo = REPO_ROOT
        self.workdir = (self.repo / cfg.workdir).resolve()
        self.tmp = Path(tempfile.mkdtemp(prefix="simula-sbx-")).resolve()

    @property
    def python_exe(self) -> str:
        """Determines the path to the virtual environment's Python executable."""
        raise NotImplementedError

    async def _run_tool(self, cmd: list[str], timeout: int | None = None) -> dict[str, Any]:
        """Runs a command, returning a dictionary with returncode and output."""
        raise NotImplementedError

    async def apply_unified_diff(self, diff: str, threeway: bool = False) -> bool:
        """Applies a unified diff inside the session."""
        if not diff.strip():
            return True
        patch_path = self.tmp / "patch.diff"
        patch_path.write_text(diff, encoding="utf-8")
        git_flags = "-3" if threeway else ""
        # Using git apply is safer than patch and handles more edge cases.
        out = await self._run_tool(["git", "apply", git_flags, "--whitespace=fix", str(patch_path)])
        return out.get("returncode", 1) == 0

    async def rollback_unified_diff(self, diff: str) -> bool:
        """Reverts a unified diff inside the session."""
        if not diff.strip():
            return True
        patch_path = self.tmp / "patch.diff"
        patch_path.write_text(diff, encoding="utf-8")
        out = await self._run_tool(["git", "apply", "-R", "--whitespace=fix", str(patch_path)])
        return out.get("returncode", 1) == 0

    async def run_pytest(self, paths: list[str], timeout: int = 900) -> tuple[bool, dict[str, Any]]:
        cmd = [self.python_exe, "-m", "pytest", "-q", "--maxfail=1", *paths]
        out = await self._run_tool(cmd, timeout=timeout)
        ok = out.get("returncode", 1) == 0
        return ok, out

    async def run_pytest_select(
        self,
        paths: list[str],
        k_expr: str,
        timeout: int = 900,
    ) -> tuple[bool, dict[str, Any]]:
        cmd = [self.python_exe, "-m", "pytest", "-q", "--maxfail=1", *paths]
        if k_expr:
            cmd.extend(["-k", k_expr])
        out = await self._run_tool(cmd, timeout=timeout)
        ok = out.get("returncode", 1) == 0
        return ok, out

    async def run_ruff(self, paths: list[str]) -> dict[str, Any]:
        return await self._run_tool([self.python_exe, "-m", "ruff", "check", *paths])

    async def run_mypy(self, paths: list[str]) -> dict[str, Any]:
        return await self._run_tool([self.python_exe, "-m", "mypy", "--pretty", *paths])

    def __del__(self):
        try:
            shutil.rmtree(self.tmp, ignore_errors=True)
        except Exception:
            pass


class DockerSession(BaseSession):
    """Container-backed session for isolated execution."""

    @property
    def python_exe(self) -> str:
        return "/workspace/.venv/bin/python"

    def _docker_base_cmd(self) -> list[str]:
        """Constructs the base docker run command with all mounts and env vars."""
        args = [
            "docker",
            "run",
            "--rm",
            "--init",
            "--cpus",
            str(self.cfg.cpus),
            "--memory",
            str(self.cfg.memory),
            "--workdir",
            f"/workspace/{self.cfg.workdir}",
            "-v",
            f"{self.repo.as_posix()}:/workspace:rw",
            "-v",
            f"{self.tmp.as_posix()}:/tmpw:rw",
        ]
        if self.cfg.network:
            args.extend(["--network", self.cfg.network])
        for k, v in self.cfg.env_set.items():
            args.extend(["-e", f"{k}={v}"])
        args.append(self.cfg.image)
        return args

    async def _run_tool(self, cmd: list[str], timeout: int | None = None) -> dict[str, Any]:
        full_cmd = self._docker_base_cmd() + cmd
        proc = await asyncio.create_subprocess_exec(
            *full_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout or self.cfg.timeout_sec,
            )
            return {
                "returncode": proc.returncode,
                "stdout": stdout_b.decode("utf-8", "replace"),
                "stderr": stderr_b.decode("utf-8", "replace"),
            }
        except TimeoutError:
            proc.kill()
            return {"returncode": 124, "stdout": "", "stderr": "Process timed out."}


class LocalSession(BaseSession):
    """Host-backed session for fast, local development loops."""

    @property
    def python_exe(self) -> str:
        win_path = self.repo / ".venv" / "Scripts" / "python.exe"
        nix_path = self.repo / ".venv" / "bin" / "python"
        return str(win_path if sys.platform == "win32" else nix_path)

    async def _run_tool(self, cmd: list[str], timeout: int | None = None) -> dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.workdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout or self.cfg.timeout_sec,
            )
            return {
                "returncode": proc.returncode,
                "stdout": stdout_b.decode("utf-8", "replace"),
                "stderr": stderr_b.decode("utf-8", "replace"),
            }
        except TimeoutError:
            proc.kill()
            return {"returncode": 124, "stdout": "", "stderr": "Process timed out."}


class DockerSandbox:
    """A factory for creating and managing Docker or Local sessions."""

    def __init__(self, cfg_dict: dict[str, object]):
        known_fields = {f.name for f in fields(SandboxConfig)}
        filtered_cfg = {k: v for k, v in cfg_dict.items() if k in known_fields}
        self.cfg = SandboxConfig(**filtered_cfg)

    @asynccontextmanager
    async def session(self):
        """Provides a session context, choosing Docker or Local based on settings."""
        mode = (os.getenv("SIMULA_SANDBOX_MODE") or self.cfg.mode or "docker").lower()
        if mode == "local":
            sess = LocalSession(self.cfg)
        elif mode == "docker":
            sess = DockerSession(self.cfg)
        else:
            raise NotImplementedError(f"Unsupported sandbox mode: {mode}")
        try:
            yield sess
        finally:
            pass
