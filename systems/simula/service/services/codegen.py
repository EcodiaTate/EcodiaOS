# systems/simula/service/services/codegen.py
# --- PROJECT SENTINEL UPGRADE (FINAL) ---
from __future__ import annotations

import json
import logging
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from systems.simula.agent.orchestrator_main import AgentOrchestrator
from systems.simula.config import settings
from systems.synk.core.switchboard.gatekit import gate


class JobContext:
    """Manages state, artifacts, and logging for a single codegen job."""

    def __init__(self, spec: str, targets: list[dict[str, Any]] | None):
        self.spec = spec
        self.start_ts = time.time()
        self.job_id = f"job_{int(self.start_ts)}_{str(uuid4())[:8]}"

        runs_dir = Path(settings.artifacts_root) / "runs"
        self.workdir = runs_dir / self.job_id
        self.workdir.mkdir(parents=True, exist_ok=True)

        self.log_handler: logging.Handler | None = None
        self.meta: dict[str, Any] = {"job_id": self.job_id, "status": "init"}

    def _utc_iso(self, ts: float) -> str:
        return datetime.fromtimestamp(ts, tz=UTC).isoformat()

    def setup_logging(self) -> None:
        """Attaches a file logger for this specific job."""
        handler = logging.FileHandler(self.workdir / "agent.log", encoding="utf-8")
        formatter = logging.Formatter(
            fmt="%(asctime)s.%(msecs)03dZ %(levelname)-8s [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.setLevel(logging.DEBUG)
        # Attach to the root logger to capture logs from all modules
        logging.getLogger().addHandler(handler)
        self.log_handler = handler

    def teardown_logging(self) -> None:
        """Detaches the job-specific file logger."""
        if self.log_handler:
            logging.getLogger().removeHandler(self.log_handler)
            self.log_handler.close()
            self.log_handler = None

    def finalize(self, result: dict[str, Any], error: Exception | None = None) -> None:
        """Finalizes the job metadata and saves the result."""
        self.meta.update(
            {
                "status": result.get("status", "error"),
                "message": result.get("message") or result.get("reason"),
                "duration_s": round(time.time() - self.start_ts, 4),
                "end_time_utc": self._utc_iso(time.time()),
            },
        )
        if error:
            self.meta["error"] = str(error)
            self.meta["traceback"] = traceback.format_exc()

        result_path = self.workdir / "result.json"
        result_path.write_text(json.dumps(self.meta, indent=2, default=str), encoding="utf-8")


async def run_codegen_job(spec: str, targets: list[dict[str, Any]] | None) -> dict[str, Any]:
    """
    Initializes the environment and runs the autonomous agent to fulfill the spec.
    """
    if not await gate("simula.codegen.enabled", True):
        return {"status": "disabled", "reason": "Feature gate 'simula.codegen.enabled' is off."}

    job = JobContext(spec, targets)
    job.setup_logging()

    try:
        objective_dict = {
            "id": f"obj_{job.job_id}",
            "title": (spec or "Untitled Codegen Task")[:120],
            "description": spec,
            "steps": [{"name": "main_evolution_step", "targets": targets or []}],
            "acceptance": {},
            "iterations": {},
        }

        logging.info("Instantiating AgentOrchestrator for job_id=%s", job.job_id)
        agent = AgentOrchestrator()
        result = await agent.run(goal=spec, objective_dict=objective_dict)
        job.finalize(result)

    except Exception as e:
        logging.exception("Agent execution failed for job_id=%s", job.job_id)
        result = {"status": "error", "reason": f"Unhandled exception in codegen job: {e!r}"}
        job.finalize(result, error=e)

    finally:
        job.teardown_logging()

    return job.meta
