# file: systems/evo/config.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvoConfig:
    """Static configuration for Evo (MVP)."""

    name: str = "evo"
    version: str = "0.1-mvp"
