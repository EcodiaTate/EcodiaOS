# systems/simula/config/__init__.py
# MDO-CLEANUP: This is now the single source of truth for all Simula configuration.

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# --- Helpers ---
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
    return os.getenv("SIMULA_REPO_ROOT") or _git_root_cwd() or "/app"


# --- Nested Settings Groups ---
class SandboxSettings(BaseSettings):
    """Sandbox runtime (Docker or Local)."""

    model_config = SettingsConfigDict(env_prefix="SIMULA_SANDBOX_")
    mode: str = "docker"
    image: str = "ecodiaos:dev"  # Correctly defaults to our main image
    timeout_sec: int = 1800
    cpus: str = "2.0"
    memory: str = "4g"
    network: str | None = "bridge"
    # Centralized toolchain definition
    pip_install: list[str] = Field(
        default_factory=lambda: [
            "pytest==8.2.0",
            "ruff==0.5.6",
            "mypy==1.10.0",
            "bandit==1.7.9",
            "pytest-xdist",
            "black",
        ],
    )


# --- Top-level Settings Class ---
class SimulaSettings(BaseSettings):
    """Global Simula configuration (single source of truth)."""

    model_config = SettingsConfigDict(env_prefix="SIMULA_")
    repo_root: str = Field(default_factory=_default_repo_root)
    artifacts_root: str = Field(default="")
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)

    @model_validator(mode="after")
    def _harmonize_paths(self):
        if not self.artifacts_root:
            self.artifacts_root = str(Path(self.repo_root) / ".simula")
        self.repo_root = _normalize_path_string(self.repo_root)
        self.artifacts_root = _normalize_path_string(self.artifacts_root)
        try:
            Path(self.artifacts_root).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return self


# --- Singleton Instance ---
settings = SimulaSettings()


# --- MDO-CLEANUP: The 'seed_config' function now lives here ---
def seed_config() -> dict[str, object]:
    """Derive the sandbox configuration directly from the central settings singleton."""
    sbx = settings.sandbox
    return {
        "mode": sbx.mode,
        "image": sbx.image,
        "timeout_sec": sbx.timeout_sec,
        "cpus": sbx.cpus,
        "memory": sbx.memory,
        "network": sbx.network,
        "workdir": ".",
        "env_set": {
            "PYTHONDONTWRITEBYTECODE": "1",
            "SIMULA_REPO_ROOT": "/workspace",
        },
    }
