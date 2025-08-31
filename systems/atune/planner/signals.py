# systems/atune/planner/signals.py
from __future__ import annotations

from typing import Any


class SECLSignals:
    def __init__(
        self,
        head_pvals: dict[str, float] | None = None,
        postcond_errors: list[dict[str, Any]] | None = None,
        regret_window: list[float] | None = None,
        trending_hosts: list[str] | None = None,
        exemplars: list[dict[str, Any]] | None = None,
        incumbent_driver: str | None = None,
    ):
        self.head_pvals = head_pvals or {}
        self.postcond_errors = postcond_errors or []
        self.regret_window = regret_window or []
        self.trending_hosts = trending_hosts or []
        self.exemplars = exemplars or []
        self.incumbent_driver = incumbent_driver
