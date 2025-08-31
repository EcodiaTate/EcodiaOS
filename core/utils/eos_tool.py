# core/utils/eos_tool.py
from __future__ import annotations

from collections.abc import Callable
from typing import Any


def eos_tool(
    *,
    name: str,
    description: str = "",
    inputs: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
    agent: str | None = None,  # "Atune" | "Unity" | "Simula" | "Synapse" | "*"
    capabilities: list[str] | None = None,  # ["search","eval","git.write"]
    safety_tier: int = 2,  # 0=unsafe..5=ultra-safe (policy-enforced downstream)
    allow_external: bool = False,  # hard gate for anything that reaches out-of-proc/world
) -> Callable:
    """
    Decorator to mark a function as an LLM-callable tool.
    Qora Patrol ingests these fields and stores them in Neo.
    """

    def deco(fn: Callable) -> Callable:
        meta = {
            "name": name,
            "description": description,
            "inputs": inputs or {},
            "outputs": outputs or {},
            "agent": agent or "*",
            "capabilities": capabilities or [],
            "safety_tier": safety_tier,
            "allow_external": allow_external,
        }
        setattr(fn, "__eos_tool__", meta)
        return fn

    return deco
