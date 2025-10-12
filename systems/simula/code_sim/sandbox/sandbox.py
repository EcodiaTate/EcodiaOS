# systems/simula/code_sim/sandbox/sandbox.py
# --- SENTINEL PATCH: host-path mount, python -c normalization/materialization, /app -> /workspace mapping ---
from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, List  # MODIFIED: Added List
from uuid import uuid4

from systems.simula.config import settings

# Host path of the repo (set via compose): e.g. /mnt/d/EcodiaOS (WSL2), /Users/me/EcodiaOS (macOS), /home/me/EcodiaOS (Linux)
HOST_REPO = os.getenv("SIMULA_HOST_APP_DIR")  # absolute host path (preferred)
# Container view of the repo (API container): usually /app
REPO_ROOT = Path(settings.repo_root).resolve()
# Scratch dir lives under the repo so the host daemon sees it through the same bind mount
SIMULA_META_DIR = REPO_ROOT / ".simula"


@dataclass
class SandboxConfig:
    mode: str = settings.sandbox.mode
    image: str = settings.sandbox.image
    timeout_sec: int = settings.sandbox.timeout_sec
    workdir: str = "."
    env_set: dict[str, str] = field(default_factory=dict)
    cpus: str = settings.sandbox.cpus
    memory: str = settings.sandbox.memory
    network: str | None = settings.sandbox.network
    # FIXED: The 'pip_install' attribute was missing from this class definition.
    # By adding it here, the SandboxConfig object will now correctly store the
    # list of packages to be installed, fixing the AttributeError.
    pip_install: list[str] = field(default_factory=list)


# --------- helpers ---------
def _normalize_c_code(code: str) -> str:
    s = code.strip()
    # split on any semicolon that is not inside quotes (simple heuristic)
    parts = [p.strip() for p in s.split(";")]
    s = "\n".join(p for p in parts if p)

    def _expand_block(pattern: str, text: str) -> str:
        return re.sub(
            pattern,
            lambda m: f"{m.group('pre')}\n    {m.group('body')}",
            text,
            flags=re.MULTILINE,
        )

    s = _expand_block(r"^(?P<pre>\s*if [^:]+:\s*)(?P<body>\S.+)$", s)
    s = _expand_block(r"^(?P<pre>\s*with [^:]+:\s*)(?P<body>\S.+)$", s)
    if not s.endswith("\n"):
        s += "\n"
    return s


# --------- sessions ---------
class BaseSession:
    def __init__(self, cfg: SandboxConfig):
        self.cfg = cfg
        self.repo = REPO_ROOT
        self.workdir = (self.repo / cfg.workdir).resolve()
        SIMULA_META_DIR.mkdir(parents=True, exist_ok=True)
        self.tmp = (SIMULA_META_DIR / f"sbx-{uuid4().hex}").resolve()
        self.tmp.mkdir(parents=True, exist_ok=True)

    @property
    def python_exe(self) -> str:
        raise NotImplementedError

    async def _run_tool(self, cmd: list[str], timeout: int | None = None) -> dict[str, Any]:
        raise NotImplementedError

    # FIXED: Added _ensure_tool method to BaseSession for LocalSession compatibility
    async def _ensure_tool(self, module_name: str, pip_name: str) -> None:
        """Ensures a tool is available in the venv, installing if necessary."""
        # This implementation is for LocalSession; DockerSession overrides it.
        check_cmd = [self.python_exe, "-c", f"import {module_name}"]
        proc = await asyncio.create_subprocess_exec(
            *check_cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        if proc.returncode != 0:
            install_cmd = [self.python_exe, "-m", "pip", "install", "-U", pip_name]
            install_proc = await asyncio.create_subprocess_exec(
                *install_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_b, stderr_b = await install_proc.communicate()
            if install_proc.returncode != 0:
                raise RuntimeError(
                    f"Failed to install '{pip_name}' in sandbox venv. Stderr: {stderr_b.decode()}",
                )

    async def apply_unified_diff(self, diff: str, threeway: bool = False) -> bool:
        if not diff.strip():
            return True
        patch_path = self.tmp / "patch.diff"
        patch_path.write_text(diff, encoding="utf-8")
        args = ["git", "apply"]
        if threeway:
            args.append("-3")
        args += ["--whitespace=fix", str(patch_path)]
        out = await self._run_tool(args)
        return out.get("returncode", 1) == 0

    async def rollback_unified_diff(self, diff: str) -> bool:
        if not diff.strip():
            return True
        patch_path = self.tmp / "patch.diff"
        patch_path.write_text(diff, encoding="utf-8")
        out = await self._run_tool(["git", "apply", "-R", "--whitespace=fix", str(patch_path)])
        return out.get("returncode", 1) == 0

    async def run_pytest(self, paths: list[str], timeout: int = 900) -> tuple[bool, dict[str, Any]]:
        await self._ensure_tool("pytest", "pytest==8.2.0")
        cmd = [self.python_exe, "-m", "pytest", "-q", "--maxfail=1", *paths]
        out = await self._run_tool(cmd, timeout=timeout)
        return out.get("returncode", 1) == 0, out

    async def run_pytest_select(
        self, paths: list[str], k_expr: str, timeout: int = 900
    ) -> tuple[bool, dict[str, Any]]:
        await self._ensure_tool("pytest", "pytest==8.2.0")
        cmd = [self.python_exe, "-m", "pytest", "-q", "--maxfail=1", *paths]
        if k_expr:
            cmd.extend(["-k", k_expr])
        out = await self._run_tool(cmd, timeout=timeout)
        return out.get("returncode", 1) == 0, out

    async def run_pytest_xdist(
        self, paths: list[str], nprocs: str = "auto", timeout: int = 900
    ) -> tuple[bool, dict[str, Any]]:
        await self._ensure_tool("pytest_xdist", "pytest-xdist")
        cmd = [self.python_exe, "-m", "pytest", "-q", f"-n={nprocs}", *paths]
        out = await self._run_tool(cmd, timeout=timeout)
        return out.get("returncode", 1) == 0, out

    async def run_ruff(self, paths: list[str]) -> dict[str, Any]:
        await self._ensure_tool("ruff", "ruff==0.5.6")
        return await self._run_tool([self.python_exe, "-m", "ruff", "check", *paths])

    async def run_mypy(self, paths: list[str]) -> dict[str, Any]:
        await self._ensure_tool("mypy", "mypy==1.10.0")
        return await self._run_tool([self.python_exe, "-m", "mypy", "--pretty", *paths])

    def __del__(self):
        try:
            shutil.rmtree(self.tmp, ignore_errors=True)
        except Exception:
            pass


class DockerSession(BaseSession):
    @property
    def python_exe(self) -> str:
        # The python executable inside the container.
        return "python"

    def _host_repo_src(self) -> str:
        """
        Source for -v <src>:/workspace. Prefer SIMULA_HOST_APP_DIR.
        If unset, fall back to REPO_ROOT path (works only when Docker daemon can see it).
        """
        return HOST_REPO or REPO_ROOT.as_posix()

    def _docker_base_cmd(self) -> list[str]:
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
            f"{self._host_repo_src()}:/workspace:rw",
        ]
        if self.cfg.network:
            args += ["--network", self.cfg.network]
        # Pass through explicit env vars
        for k, v in self.cfg.env_set.items():
            args += ["-e", f"{k}={v}"]
        # Helpful defaults inside the job container
        args += ["-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "SIMULA_REPO_ROOT=/workspace"]
        args.append(self.cfg.image)
        return args

    def _remap_args(self, args: list[str]) -> list[str]:
        """Map any /app/... paths (API container view) to /workspace/... (job container view)."""
        mapped: list[str] = []
        for a in args:
            if isinstance(a, str) and a.startswith("/app/"):
                mapped.append("/workspace/" + a[len("/app/") :])
            else:
                mapped.append(a)
        return mapped

    def _materialize_python_c(self, cmd: list[str]) -> list[str]:
        """
        If the command is `python -c <code> [args...]`, write <code> to a temp script
        under REPO_ROOT/.simula/sbx-... so it's visible to the daemon via the same bind,
        then run it as `python /workspace/.simula/.../inline_script.py ...`.
        """
        if len(cmd) >= 3 and cmd[0] in ("python", "python3") and cmd[1] == "-c":
            code = _normalize_c_code(cmd[2])
            script_path = self.tmp / "inline_script.py"
            script_path.write_text(code, encoding="utf-8")
            container_script = f"/workspace/.simula/{self.tmp.name}/inline_script.py"
            return [self.python_exe, container_script, *cmd[3:]]
        return cmd

    async def _ensure_tool(self, module_name: str, pip_name: str) -> None:
        """
        NO-OP for Docker. Assumes all tools are pre-installed in the image.
        """
        return

    async def _run_tool(self, cmd: list[str], timeout: int | None = None) -> dict[str, Any]:
        # 1) transform python -c to a real file (with normalization)
        cmd = self._materialize_python_c(cmd)
        # 2) remap any /app paths to /workspace
        cmd = self._remap_args(cmd)
        full_cmd = self._docker_base_cmd() + cmd

        proc = await asyncio.create_subprocess_exec(
            *full_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout or self.cfg.timeout_sec
            )
        except TimeoutError:
            proc.kill()
            return {"returncode": 124, "stdout": "", "stderr": "Process timed out."}

        out = {
            "returncode": proc.returncode,
            "stdout": stdout_b.decode("utf-8", "replace"),
            "stderr": stderr_b.decode("utf-8", "replace"),
        }
        if out["returncode"] != 0:
            sys.stderr.write(
                f"[DockerSession] rc={out['returncode']}\n"
                f"CMD: {' '.join(full_cmd)}\n"
                f"STDOUT:\n{out['stdout']}\nSTDERR:\n{out['stderr']}\n",
            )
        return out


class LocalSession(BaseSession):
    @property
    def python_exe(self) -> str:
        win = self.repo / ".venv" / "Scripts" / "python.exe"
        nix = self.repo / ".venv" / "bin" / "python"
        return str(win if sys.platform == "win32" else nix)

    async def _run_tool(self, cmd: list[str], timeout: int | None = None) -> dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.workdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout or self.cfg.timeout_sec
            )
        except TimeoutError:
            proc.kill()
            return {"returncode": 124, "stdout": "", "stderr": "Process timed out."}
        return {
            "returncode": proc.returncode,
            "stdout": stdout_b.decode("utf-8", "replace"),
            "stderr": stderr_b.decode("utf-8", "replace"),
        }


class DockerSandbox:
    def __init__(self, cfg_dict: dict[str, object]):
        known = {f.name for f in fields(SandboxConfig)}
        self.cfg = SandboxConfig(**{k: v for k, v in cfg_dict.items() if k in known})

    @asynccontextmanager
    async def session(self):
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
