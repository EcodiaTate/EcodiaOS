from __future__ import annotations

from typing import Any


class QualityMixin:
    async def run_cmd(self, args: list[str], timeout: int = 900) -> tuple[bool, dict[str, Any]]:
        """
        Implemented by DockerSandbox.session(); must execute args in the container
        and return (ok, logs_dict). If you already have `exec`, adapt to call it here.
        """
        raise NotImplementedError

    async def run_pytest(self, paths: list[str], timeout: int = 900) -> tuple[bool, dict[str, Any]]:
        return await self.run_cmd(["pytest", "-q", *paths], timeout=timeout)

    async def run_mypy(self, paths: list[str]) -> dict[str, Any]:
        ok, logs = await self.run_cmd(["mypy", "--hide-error-context", *paths], timeout=900)
        logs["ok"] = ok
        return logs

    async def run_ruff(self, paths: list[str]) -> dict[str, Any]:
        ok, logs = await self.run_cmd(["ruff", "check", *paths], timeout=600)
        logs["ok"] = ok
        return logs

    async def run_bandit(self, paths: list[str]) -> dict[str, Any]:
        ok, logs = await self.run_cmd(["bandit", "-q", "-r", *paths], timeout=600)
        logs["ok"] = ok
        return logs
