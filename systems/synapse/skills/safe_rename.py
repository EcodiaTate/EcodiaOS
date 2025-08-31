# systems/synapse/skills/safe_rename.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SafeRenameSpec:
    file: str
    symbol: str
    new_name: str


async def plan(spec: SafeRenameSpec) -> dict[str, object]:
    return {
        "arms": [
            {"arm_id": "analyze_usages", "params": spec.__dict__},
            {"arm_id": "apply_rename", "params": spec.__dict__},
            {"arm_id": "run_hygiene", "params": {"paths": ["tests"]}},
        ],
    }
