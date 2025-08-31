# systems/synapse/skills/introduce_adapter.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IntroduceAdapterSpec:
    file: str
    symbol: str
    adapter_name: str


async def plan(spec: IntroduceAdapterSpec) -> dict[str, object]:
    return {
        "arms": [
            {"arm_id": "generate_adapter", "params": spec.__dict__},
            {"arm_id": "wire_adapter", "params": spec.__dict__},
            {"arm_id": "run_hygiene", "params": {"paths": ["tests"]}},
        ],
    }
