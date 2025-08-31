# systems/simula/config/loader.py
from __future__ import annotations

from dataclasses import dataclass

from . import settings  # unified source


@dataclass
class SimulaConfig:
    delta_cov_min: float
    min_mutation_score: float
    use_xdist: bool
    enable_cache: bool
    eos_policy_paths: list[str] | None


def load_config() -> SimulaConfig:
    return SimulaConfig(
        delta_cov_min=settings.delta_cov_min,
        min_mutation_score=settings.min_mutation_score,
        use_xdist=settings.use_xdist,
        enable_cache=settings.enable_cache,
        eos_policy_paths=settings.eos_policy_paths,
    )
