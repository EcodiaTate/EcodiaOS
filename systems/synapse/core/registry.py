# systems/synapse/core/registry.py
# COMPLETE REPLACEMENT - HOF-AWARE + DYNAMIC ARMS, NO ensure_cold_start

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from collections.abc import Iterable
from typing import Any, Dict, List, Optional, Set

from core.utils.neo.cypher_query import cypher_query
from systems.synapse.policy.policy_dsl import PolicyGraph
from systems.synapse.training.neural_linear import (
    NeuralLinearBanditHead,
    neural_linear_manager,
)

logger = logging.getLogger(__name__)

# ---------- helpers ----------


def _coerce_policy_graph(pg_like: Any) -> PolicyGraph:
    if isinstance(pg_like, PolicyGraph):
        return pg_like
    if isinstance(pg_like, str):
        pg_like = json.loads(pg_like)
    if not isinstance(pg_like, dict):
        raise TypeError(f"Unsupported policy_graph type: {type(pg_like).__name__}")
    if hasattr(PolicyGraph, "model_validate"):
        return PolicyGraph.model_validate(pg_like)
    return PolicyGraph(**pg_like)


def _node_effects_says_dangerous(node: Any) -> bool:
    try:
        effects = getattr(node, "effects", node.get("effects") if isinstance(node, dict) else None)
        if not effects:
            return False
        dangerous_effects = {"write", "net_access", "execute"}
        items = (
            set(effects)
            if isinstance(effects, Iterable) and not isinstance(effects, str)
            else {effects}
        )
        return any(x in dangerous_effects for x in items)
    except Exception:
        return False


def _default_llm_model() -> str:
    return os.getenv("DEFAULT_LLM_MODEL", "gpt-4o-mini")


def _create_noop_policy_graph(arm_id: str) -> PolicyGraph:
    pg_dict = {
        "id": arm_id,
        "nodes": [
            {
                "id": "prompt",
                "type": "prompt",
                "model": _default_llm_model(),
                "params": {"temperature": 0.1},
            },
        ],
        "edges": [],
    }
    return _coerce_policy_graph(pg_dict)


def _is_dynamic_id(arm_id: str) -> bool:
    return isinstance(arm_id, str) and arm_id.startswith("dyn::")


# ---------- core classes ----------


class PolicyArm:
    __slots__ = ("id", "policy_graph", "mode", "bandit_head")

    def __init__(
        self, arm_id: str, policy_graph: PolicyGraph, mode: str, bandit_head: NeuralLinearBanditHead
    ):
        if not arm_id:
            raise ValueError("PolicyArm requires a non-empty arm_id.")
        self.id: str = arm_id
        self.policy_graph: PolicyGraph = policy_graph
        self.mode: str = mode or "generic"
        self.bandit_head: NeuralLinearBanditHead = bandit_head

    @property
    def is_safe_fallback(self) -> bool:
        try:
            return not any(_node_effects_says_dangerous(n) for n in (self.policy_graph.nodes or []))
        except Exception:
            return False


class ArmRegistry:
    _instance: ArmRegistry | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self._arms: dict[str, PolicyArm] = {}
        self._by_mode: dict[str, list[PolicyArm]] = {}
        self._hall_of_fame_arms: dict[str, set[str]] = {}
        self._lock = threading.RLock()

    async def initialize(self) -> None:
        print("[ArmRegistry] Initializing and hydrating all PolicyArms from graph...")

        query_arms = """
        MATCH (p:PolicyArm)
        RETURN
          coalesce(p.arm_id, p.id)    AS arm_id,
          p.policy_graph              AS policy_graph,
          coalesce(p.mode, 'generic') AS mode,
          p.A AS A, p.A_shape AS A_shape,
          p.b AS b, p.b_shape AS b_shape
        """
        query_hof = (
            "MATCH (h:HallOfFameArm) RETURN h.id AS arm_id, coalesce(h.mode,'generic') AS mode"
        )

        try:
            arm_rows, hof_rows = await asyncio.gather(
                cypher_query(query_arms),
                cypher_query(query_hof),
            )
            arm_rows = arm_rows or []
            hof_rows = hof_rows or []
        except Exception as e:
            print(f"[ArmRegistry] CRITICAL: Database query failed during initialization: {e}")
            arm_rows, hof_rows = [], []

        new_hof_arms: dict[str, set[str]] = {}
        for row in hof_rows:
            aid, mode = row.get("arm_id"), row.get("mode") or "generic"
            if aid and mode:
                new_hof_arms.setdefault(mode, set()).add(aid)

        new_arms: dict[str, PolicyArm] = {}
        new_by_mode: dict[str, list[PolicyArm]] = {}
        dimensions = getattr(neural_linear_manager, "dimensions", 64)

        for row in arm_rows:
            arm_id = row.get("arm_id")
            graph_raw = row.get("policy_graph")
            mode = row.get("mode") or "generic"
            if not arm_id or not graph_raw:
                continue
            try:
                pg = _coerce_policy_graph(graph_raw)
                initial_state = None
                if all(row.get(k) for k in ["A", "A_shape", "b", "b_shape"]):
                    initial_state = {
                        "A": row["A"],
                        "A_shape": row["A_shape"],
                        "b": row["b"],
                        "b_shape": row["b_shape"],
                    }
                head = NeuralLinearBanditHead(arm_id, dimensions, initial_state=initial_state)
                arm = PolicyArm(arm_id=arm_id, policy_graph=pg, mode=mode, bandit_head=head)
                new_arms[arm.id] = arm
                new_by_mode.setdefault(arm.mode, []).append(arm)
            except Exception as e:
                print(f"[ArmRegistry] ERROR: Could not hydrate PolicyArm '{arm_id}': {e}")

        with self._lock:
            self._arms = new_arms
            self._by_mode = new_by_mode
            self._hall_of_fame_arms = new_hof_arms

        total_loaded = len(self._arms)
        total_hof = sum(len(s) for s in self._hall_of_fame_arms.values())
        mode_counts = {mode: len(arms) for mode, arms in self._by_mode.items()}
        print(
            f"[ArmRegistry] Initialization complete. Loaded {total_loaded} arms ({total_hof} in Hall of Fame). Mode distribution: {mode_counts}"
        )

    async def reload(self) -> None:
        await self.initialize()

    def get_arm(self, arm_id: str) -> PolicyArm | None:
        with self._lock:
            arm = self._arms.get(arm_id)
        return arm

    def get_policy_arm(self, arm_id: str) -> PolicyArm | None:
        return self.get_arm(arm_id)

    def get_arms_for_mode(self, mode: str) -> list[PolicyArm]:
        with self._lock:
            return list(self._by_mode.get(mode, []))

    def list_modes(self) -> list[str]:
        with self._lock:
            return sorted(self._by_mode.keys())

    def get_hall_of_fame_arm_ids(self, mode: str) -> set[str]:
        with self._lock:
            return set(self._hall_of_fame_arms.get(mode, set()))

    async def register_dynamic_arm(
        self,
        arm_id: str,
        *,
        mode: str = "generic",
        policy_graph: PolicyGraph | dict[str, Any] | None = None,
        persist: bool = True,
        initial_state: dict[str, Any] | None = None,
    ) -> PolicyArm:
        if not arm_id:
            raise ValueError("arm_id is required")
        pg = (
            _coerce_policy_graph(policy_graph)
            if policy_graph
            else _create_noop_policy_graph(arm_id)
        )

        dimensions = getattr(neural_linear_manager, "dimensions", 64)
        head = NeuralLinearBanditHead(arm_id, dimensions, initial_state=initial_state)

        arm = PolicyArm(arm_id=arm_id, policy_graph=pg, mode=mode, bandit_head=head)
        with self._lock:
            self._arms[arm.id] = arm
            self._by_mode.setdefault(arm.mode, []).append(arm)

        if persist:
            try:
                await cypher_query(
                    """
                    MERGE (p:PolicyArm {arm_id: $id})
                    ON CREATE SET p.mode = $mode, p.policy_graph = $graph
                    ON MATCH  SET p.mode = coalesce(p.mode, $mode), p.policy_graph = coalesce(p.policy_graph, $graph)
                    """,
                    {"id": arm_id, "mode": mode, "graph": pg.model_dump(mode="json")},
                )
            except Exception as e:
                logger.warning("[ArmRegistry] Persisting dynamic arm '%s' failed: %r", arm_id, e)

        return arm

    async def get_or_register_dynamic_arm(self, arm_id: str, *, mode: str = "generic") -> PolicyArm:
        arm = self.get_arm(arm_id)
        if arm:
            return arm
        if _is_dynamic_id(arm_id):
            return await self.register_dynamic_arm(
                arm_id, mode=mode, policy_graph=None, persist=False
            )
        return None

    async def get_safe_fallback_arm(self, mode: str | None = None) -> PolicyArm:
        with self._lock:
            if mode:
                for arm in self._by_mode.get(mode, []):
                    if arm.is_safe_fallback:
                        return arm
            for arm_list in self._by_mode.values():
                for arm in arm_list:
                    if arm.is_safe_fallback:
                        return arm

        try:
            arm_id = "generic.safe_fallback"
            pg = _create_noop_policy_graph(arm_id)
            dimensions = getattr(neural_linear_manager, "dimensions", 64)
            head = NeuralLinearBanditHead(arm_id, dimensions, initial_state=None)
            ephemeral = PolicyArm(arm_id=arm_id, policy_graph=pg, mode="generic", bandit_head=head)
            with self._lock:
                self._arms[ephemeral.id] = ephemeral
                self._by_mode.setdefault(ephemeral.mode, []).append(ephemeral)
            logger.warning("[ArmRegistry] Created ephemeral '%s' safe fallback.", arm_id)
            return ephemeral
        except Exception as e:
            logger.error(
                "[ArmRegistry] FAILED to create ephemeral safe fallback: %r", e, exc_info=True
            )

            class _Shim:
                pass

            shim = _Shim()
            shim.id = "generic.safe_fallback"
            shim.mode = "generic"
            shim.policy_graph = _create_noop_policy_graph(shim.id)
            shim.bandit_head = NeuralLinearBanditHead(
                shim.id, getattr(neural_linear_manager, "dimensions", 64)
            )
            return shim


# singleton
arm_registry = ArmRegistry()
