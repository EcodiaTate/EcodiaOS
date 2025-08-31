# systems/simula/config/__init__.py
# --- PROJECT SENTINEL UPGRADE ---
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# --- Helpers -----------------------------------------------------------------


def _normalize_path_string(p: str | Path) -> str:
    return str(Path(p).resolve()).replace("\\", "/")


def _git_root_cwd() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
        )
        return _normalize_path_string(out.decode().strip())
    except Exception:
        return None


def _default_repo_root() -> str:
    return (
        os.getenv("SIMULA_REPO_ROOT")
        or os.getenv("SIMULA_WORKSPACE_ROOT")
        or _git_root_cwd()
        or "/ecodiaos"
    )


def _optional_json_or_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() in (".yaml", ".yml") and yaml:
            data = yaml.safe_load(text) or {}
        else:
            data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# --- Nested Settings Groups --------------------------------------------------


class GateSettings(BaseSettings):
    """Configuration for quality gates, formerly from gates.py."""

    model_config = SettingsConfigDict(env_prefix="SIMULA_GATE_")
    require_static_clean: bool = True
    require_tests_green: bool = True
    min_delta_cov: float = 0.0
    run_safety: bool = True
    pr_open: bool = True
    pr_draft: bool = True
    pr_labels: list[str] = Field(default_factory=lambda: ["simula", "auto"])

    @property
    def autopr_enabled(self) -> bool:
        return self.pr_open


class SandboxSettings(BaseSettings):
    """Sandbox runtime (Docker or Local)."""

    model_config = SettingsConfigDict(env_prefix="SIMULA_SANDBOX_")
    mode: str = "docker"
    image: str = "python:3.11-slim"
    timeout_sec: int = 1800
    cpus: str = "2.0"
    memory: str = "4g"
    network: str | None = "bridge"
    pip_install: list[str] = Field(default_factory=list)


class TimeoutSettings(BaseSettings):
    """Tool-specific timeouts."""

    model_config = SettingsConfigDict(env_prefix="SIMULA_TIMEOUT_")
    tool_default: int = 90
    test: int = 1800
    llm: int = 120


# --- Top-level Settings Class ------------------------------------------------


class SimulaSettings(BaseSettings):
    """Global Simula configuration (single source of truth)."""

    model_config = SettingsConfigDict(env_prefix="SIMULA_")

    repo_root: str = Field(default_factory=_default_repo_root)
    artifacts_root: str = Field(default="")

    max_turns: int = 15
    max_observation_length: int = 4000
    test_mode: bool = False

    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)
    timeouts: TimeoutSettings = Field(default_factory=TimeoutSettings)
    gates: GateSettings = Field(default_factory=GateSettings)
    eos_policy_paths: list[str] | None = None

    @field_validator("test_mode", mode="before")
    @classmethod
    def _parse_test_mode(cls, v):
        if v is None:
            v = os.getenv("SIMULA_TEST_MODE", "0")
        return str(v).lower() in ("1", "true", "yes", "on")

    @model_validator(mode="after")
    def _harmonize_and_overlay(self):
        # 1. Normalize core paths
        if not self.artifacts_root:
            self.artifacts_root = str(Path(self.repo_root) / ".simula")
        self.repo_root = _normalize_path_string(self.repo_root)
        self.artifacts_root = _normalize_path_string(self.artifacts_root)

        # 2. Overlay team defaults from config files
        config_yaml = Path(self.repo_root) / ".simula" / "config.yaml"
        gates_json = Path(self.repo_root) / ".simula" / "gates.json"

        for cfg_path in [config_yaml, gates_json]:
            overlay = _optional_json_or_yaml(cfg_path)
            for key, value in overlay.items():
                if hasattr(self, key):
                    current_attr = getattr(self, key)
                    if isinstance(current_attr, BaseSettings) and isinstance(value, dict):
                        for sub_key, sub_value in value.items():
                            if hasattr(current_attr, sub_key):
                                setattr(current_attr, sub_key, sub_value)
                    else:
                        setattr(self, key, value)

        # 3. Ensure critical directories exist
        try:
            Path(self.artifacts_root).mkdir(parents=True, exist_ok=True)
            for sub in ("runs", "logs", "cache", "policy"):
                (Path(self.artifacts_root) / sub).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

        return self


# --- Singleton Instance ---
settings = SimulaSettings()
