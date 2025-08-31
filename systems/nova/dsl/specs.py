# file: systems/nova/dsl/specs.py
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class MechanismOp(BaseModel):
    name: str
    params: dict[str, Any] = {}


class MechanismSpec(BaseModel):
    # minimal, typed DAG-ish representation
    nodes: list[MechanismOp] = []
    edges: list[list[int]] = []  # adjacency by index


class CapabilitySpec(BaseModel):
    io: dict[str, Any] = {}  # schemas
    rate_limits: dict[str, Any] = {}  # qps, burst
    obligations: dict[str, list[str]] = {}
    rollback_contract: dict[str, Any] = {"type": "undo", "params": {}}


class ProofSpec(BaseModel):
    obligations: dict[str, list[str]] = {}
    sketches: dict[str, Any] = {}
