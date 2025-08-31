from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from core.llm.bus import event_bus

logger = logging.getLogger(__name__)


def _proposal_payload(maybe_wrapped: dict[str, Any]) -> dict[str, Any]:
    if isinstance(maybe_wrapped, dict) and "diff" in maybe_wrapped:
        return maybe_wrapped
    if (
        isinstance(maybe_wrapped, dict)
        and "proposal" in maybe_wrapped
        and isinstance(maybe_wrapped["proposal"], dict)
    ):
        return maybe_wrapped["proposal"]
    return {}


def _proposal_id(p: dict[str, Any]) -> str:
    pid = str(p.get("id") or "").strip()
    if pid:
        return pid
    diff = str(p.get("diff") or "")
    h = hashlib.sha256(diff.encode("utf-8")).hexdigest()[:24]
    return f"pp_{h}"


class CICDListener:
    """Automated deployment listener for approved self-upgrades."""

    _instance: CICDListener | None = None

    # Class-level annotations (Pylance-friendly)
    _lock: asyncio.Lock
    _sub_task: asyncio.Task | None = None
    _started: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._lock = asyncio.Lock()
        return cls._instance

    def __init__(self):
        if self._started:
            return
        self._started = True
        loop = asyncio.get_event_loop()
        # No inline annotation here; Pylance-safe
        self._sub_task = loop.create_task(self._subscribe())
        logger.info("[CICDListener] Initializing subscription to deployment triggers.")

    async def _subscribe(self) -> None:
        try:
            event_bus.subscribe("governor.upgrade.approved", self._on_event)
            logger.info("[CICDListener] Subscribed to 'governor.upgrade.approved'.")
        except Exception:
            logger.exception("[CICDListener] Failed to subscribe to event bus.")

    async def _on_event(self, payload: dict[str, Any]) -> None:
        proposal = _proposal_payload(payload)
        if not proposal:
            logger.error("[CICDListener] Malformed approval event: %s", str(payload)[:500])
            await event_bus.publish(
                {"topic": "cicd.deployment.failed", "payload": {"reason": "malformed_event"}},
            )
            return
        await self.on_upgrade_approved(proposal)

    async def _run_command(self, command: str, cwd: str) -> str:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        out = stdout.decode(errors="ignore").strip()
        err = stderr.decode(errors="ignore").strip()

        if proc.returncode != 0:
            error_message = (
                f"command failed rc={proc.returncode} cmd=`{command}` stderr={err[:4000]}"
            )
            logger.error("[CICD] %s", error_message)
            await event_bus.publish(
                {"topic": "cicd.deployment.failed", "payload": {"reason": error_message}},
            )
            raise ChildProcessError(error_message)

        logger.info("[CICD] OK: `%s`", command)
        if out:
            logger.debug("[CICD] STDOUT: %s", out[:4000])
        return out

    async def on_upgrade_approved(self, proposal: dict[str, Any]) -> None:
        async with self._lock:
            summary = str(proposal.get("summary") or "Automated self-upgrade")
            diff = proposal.get("diff")
            if not diff:
                logger.error("[CICDListener] Approval event had no diff; aborting.")
                await event_bus.publish(
                    {
                        "topic": "cicd.deployment.failed",
                        "payload": {"reason": "no_diff_in_proposal"},
                    },
                )
                return

            pid = _proposal_id(proposal)
            repo_url = os.getenv("GIT_REPO_URL", "").strip()
            if not repo_url:
                msg = "GIT_REPO_URL not set"
                logger.error("[CICDListener] %s", msg)
                await event_bus.publish(
                    {
                        "topic": "cicd.deployment.failed",
                        "payload": {"reason": msg, "proposal_id": pid},
                    },
                )
                return

            base_branch = os.getenv("GIT_TARGET_BRANCH", "").strip() or None
            push_branch = os.getenv("GIT_PUSH_BRANCH", "").strip() or f"governor/auto-{pid[:8]}"
            commit_name = os.getenv("GIT_COMMIT_NAME", "Ecodia Governor")
            commit_email = os.getenv("GIT_COMMIT_EMAIL", "governor@ecodia.os")
            clone_depth = int(os.getenv("GIT_CLONE_DEPTH", "1"))

            logger.info("[CICDListener] Deployment starting id=%s branch=%s", pid, push_branch)
            await event_bus.publish(
                {
                    "topic": "cicd.deployment.started",
                    "payload": {"proposal_id": pid, "summary": summary, "push_branch": push_branch},
                },
            )

            with tempfile.TemporaryDirectory() as temp_dir:
                repo_path = str(Path(temp_dir) / "repo")
                patch_file = str(Path(repo_path) / "approved_patch.diff")

                depth_arg = f"--depth {clone_depth}" if clone_depth > 0 else ""
                await self._run_command(
                    f"git clone {depth_arg} {repo_url} {repo_path}",
                    cwd=temp_dir,
                )

                if base_branch:
                    await self._run_command(f"git fetch origin {base_branch}", cwd=repo_path)
                    await self._run_command(
                        f"git checkout -B {push_branch} origin/{base_branch}",
                        cwd=repo_path,
                    )
                else:
                    await self._run_command(f"git checkout -b {push_branch}", cwd=repo_path)

                Path(patch_file).write_text(diff, encoding="utf-8")
                await self._run_command(
                    f"git apply --index --whitespace=fix {patch_file}",
                    cwd=repo_path,
                )
                await self._run_command(f'git config user.name "{commit_name}"', cwd=repo_path)
                await self._run_command(f'git config user.email "{commit_email}"', cwd=repo_path)
                await self._run_command(
                    f'git commit -m "Apply approved self-upgrade ({pid}): {summary}"',
                    cwd=repo_path,
                )
                await self._run_command(
                    f"git push origin HEAD:refs/heads/{push_branch}",
                    cwd=repo_path,
                )

                commit_sha = await self._run_command("git rev-parse HEAD", cwd=repo_path)
                logger.info("[CICDListener] Deployment successful id=%s sha=%s", pid, commit_sha)
                await event_bus.publish(
                    "cicd.deployment.succeeded",
                    {
                        "proposal_id": pid,
                        "summary": summary,
                        "branch": push_branch,
                        "commit": commit_sha,
                    },
                )


# Instantiate to start listening
cicd_listener = CICDListener()
