# systems/simula/code_sim/loop.py
"""
Simula Code Evolution - Utilities Module

This module previously contained the main SimulaEngine orchestrator. Its core logic
has been refactored into the `execute_planned_code_evolution` tool, which is
now available to the AgentOrchestrator.

This file is preserved to provide essential, stateless utility classes and
functions that support the new tool and other parts of the system, such as:
- Artifact storage and management (`ArtifactStore`)
- Configuration data structures (`SimulaConfig`)
- Standardized JSON logging (`JsonLogFormatter`)
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

# --- Simula subsystems ---
# Note: The main loop dependencies are now in agent/tools.py

try:
    import yaml
except ImportError as e:
    raise RuntimeError("PyYAML is required for Simula's utility functions.") from e

# =========================
# Utilities & Logging
# =========================


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": dt.datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "lvl": record.levelname,
            "msg": record.getMessage(),
            "logger": record.name,
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra", None)
        if isinstance(extra, dict):
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(verbose: bool, run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("simula")  # Get simula-namespaced logger
    log.handlers.clear()
    log.setLevel(logging.DEBUG if verbose else logging.INFO)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(JsonLogFormatter())
    log.addHandler(ch)

    fh = logging.FileHandler(run_dir / "simula.log", encoding="utf-8")
    fh.setFormatter(JsonLogFormatter())
    log.addHandler(fh)


def sha1(s: str) -> str:
    import hashlib as _h

    return _h.sha1(s.encode("utf-8")).hexdigest()


# =========================
# Configuration Dataclasses
# =========================


@dataclass
class SandboxCfg:
    image: str = "python:3.11-slim"
    timeout_sec: int = 1200
    network: str = "bridge"


@dataclass
class OrchestratorCfg:
    parallelism: int = 2
    max_wall_minutes: int = 90
    seed: int | None = None
    keep_artifacts: bool = True
    k_candidates: int = 2
    unity_channel: str = "simula.codegen"


@dataclass
class SimulaConfig:
    sandbox: SandboxCfg
    orchestrator: OrchestratorCfg

    @staticmethod
    def load(path: Path | None = None) -> SimulaConfig:
        raw = {}
        if path and path.exists():
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

        # Return default config if no file is provided or file is empty
        return SimulaConfig(
            sandbox=SandboxCfg(**(raw.get("sandbox", {}) or {})),
            orchestrator=OrchestratorCfg(**(raw.get("orchestrator", {}) or {})),
        )


# =========================
# Provenance / Artifacts
# =========================


class ArtifactStore:
    """
    Persists patches, evaluator outputs, and other artifacts for a given run.
    """

    def __init__(self, root_dir: Path, run_id: str):
        self.base = root_dir / "runs" / run_id
        self.base.mkdir(parents=True, exist_ok=True)
        (self.base / "candidates").mkdir(exist_ok=True)
        (self.base / "winners").mkdir(exist_ok=True)
        (self.base / "evaluator").mkdir(exist_ok=True)

    def write_text(self, rel: str, content: str) -> Path:
        p = self.base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def save_candidate(
        self,
        step_name: str,
        iter_idx: int,
        file_rel: str,
        patch: str,
        tag: str = "",
    ) -> Path:
        h = sha1(patch)[:10]
        safe_rel = (file_rel or "unknown").replace("/", "__")
        name = f"{step_name}_iter{iter_idx:02d}_{safe_rel}_{h}{('_' + tag) if tag else ''}.diff"
        return self.write_text(f"candidates/{name}", patch)
