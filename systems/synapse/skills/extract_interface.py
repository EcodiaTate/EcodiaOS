# systems/synapse/skills/extract_interface.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExtractInterfaceSpec:
    file: str
    class_name: str
    iface_name: str
    methods: list[str]


async def plan(spec: ExtractInterfaceSpec) -> dict[str, object]:
    return {
        "arms": [
            {"arm_id": "analyze_methods", "params": spec.__dict__},
            {"arm_id": "create_interface", "params": spec.__dict__},
            {"arm_id": "adapt_callers", "params": spec.__dict__},
            {"arm_id": "run_hygiene", "params": {"paths": ["tests"]}},
        ],
    }
