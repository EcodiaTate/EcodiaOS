from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from pathlib import Path

from systems.nova.insights.self_model import ArmStats, NovaSelfModel

DEFAULT_PATH = os.getenv("NOVA_SELF_MODEL_PATH", "/var/lib/ecodia/nova/self_model.json")
DECAY_HALF_LIFE_DAYS = float(os.getenv("NOVA_SELF_MODEL_HALF_LIFE_DAYS", "21"))


class SelfModelStore:
    """
    Persists NovaSelfModel across runs with gentle recency decay.
    Falls back to in-memory if the path is unwritable.
    """

    def __init__(self, model: NovaSelfModel, path: str | None = None) -> None:
        self.model = model
        self.path = path or DEFAULT_PATH
        self._loaded = False

    def _decay(self, st: ArmStats, now: float) -> ArmStats:
        if st.trials <= 0:
            return st
        dt_days = max(0.0, (now - st.last_ts) / 86400.0)
        if DECAY_HALF_LIFE_DAYS <= 0:
            return st
        decay = 0.5 ** (dt_days / DECAY_HALF_LIFE_DAYS)
        st.trials = max(0, int(round(st.trials * decay)))
        st.wins = max(0, int(round(st.wins * decay)))
        st.score_sum *= decay
        st.spend_ms = int(round(st.spend_ms * decay))
        return st

    def load(self) -> None:
        if self._loaded:
            return
        try:
            p = Path(self.path)
            if not p.exists():
                self._loaded = True
                return
            data = json.loads(p.read_text(encoding="utf-8"))
            now = time.time()
            arms: dict[tuple[str, str], ArmStats] = {}
            for k, v in data.get("arms", {}).items():
                st = ArmStats(**v)
                arms[tuple(k.split("::", 1))] = self._decay(st, now)
            self.model._arms = arms
            self._loaded = True
        except Exception:
            # Don’t crash NOVA if the file is missing or corrupt
            self._loaded = True

    def save(self) -> None:
        try:
            p = Path(self.path)
            p.parent.mkdir(parents=True, exist_ok=True)
            arms = {f"{a}::{b}": asdict(st) for (a, b), st in self.model._arms.items()}
            p.write_text(json.dumps({"arms": arms}, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            # Best-effort persistence only
            pass
