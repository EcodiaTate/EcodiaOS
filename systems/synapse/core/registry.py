# systems/synapse/core/registry.py
# COMPLETE REPLACEMENT - HOF-AWARE + DYNAMIC ARMS, BASE.* IDS, MODE='generic'

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from collections.abc import Iterable
from typing import Any

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


def _alias_arm_id(arm_id: str) -> str:
    """
    Normalize legacy 'generic.*' IDs to the canonical 'base.*' namespace.
    The 'mode' for base.* arms remains 'generic'.
    """
    if not isinstance(arm_id, str):
        return arm_id
    if arm_id.startswith("generic."):
        return "base." + arm_id[len("generic.") :]
    return arm_id


# ---------- core classes ----------


class PolicyArm:
    __slots__ = ("id", "policy_graph", "mode", "bandit_head")

    def __init__(
        self,
        arm_id: str,
        policy_graph: PolicyGraph,
        mode: str,
        bandit_head: NeuralLinearBanditHead,
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

        # We accept either p.id or legacy p.arm_id; canonical is p.id.
        query_arms = """
        MATCH (p:PolicyArm)
        RETURN
          coalesce(p.id, p.arm_id)     AS arm_id,
          p.policy_graph               AS policy_graph,
          coalesce(p.mode, 'generic')  AS mode,
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
                # Apply alias here as well so HOF references align with canonical IDs.
                aid = _alias_arm_id(aid)
                new_hof_arms.setdefault(mode, set()).add(aid)

        new_arms: dict[str, PolicyArm] = {}
        new_by_mode: dict[str, list[PolicyArm]] = {}
        dimensions = getattr(neural_linear_manager, "dimensions", 64)

        for row in arm_rows:
            raw_id = row.get("arm_id")
            graph_raw = row.get("policy_graph")
            mode = row.get("mode") or "generic"
            if not raw_id or not graph_raw:
                continue

            arm_id = _alias_arm_id(raw_id)
            try:
                pg = _coerce_policy_graph(graph_raw)
                initial_state = None
                if all(row.get(k) is not None for k in ["A", "A_shape", "b", "b_shape"]):
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
            f"[ArmRegistry] Initialization complete. Loaded {total_loaded} arms ({total_hof} in Hall of Fame). Mode distribution: {mode_counts}",
        )

    async def reload(self) -> None:
        await self.initialize()

    def get_arm(self, arm_id: str) -> PolicyArm | None:
        arm_id = _alias_arm_id(arm_id)
        with self._lock:
            return self._arms.get(arm_id)

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

        arm_id = _alias_arm_id(arm_id)
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
                    MERGE (p:PolicyArm {id: $id})
                    ON CREATE SET p.arm_id = $id, p.mode = $mode, p.policy_graph = $graph
                    ON MATCH  SET p.arm_id = coalesce(p.arm_id, $id),
                                p.mode = coalesce(p.mode, $mode),
                                p.policy_graph = coalesce(p.policy_graph, $graph)
                    """,
                    {"id": arm_id, "mode": mode, "graph": pg.model_dump(mode="json")},
                )
            except Exception as e:
                logger.warning("[ArmRegistry] Persisting dynamic arm '%s' failed: %r", arm_id, e)

        return arm

    async def get_or_register_dynamic_arm(
        self, arm_id: str, *, mode: str = "generic",
    ) -> PolicyArm | None:
        arm_id = _alias_arm_id(arm_id)
        arm = self.get_arm(arm_id)
        if arm:
            return arm
        if _is_dynamic_id(arm_id):
            return await self.register_dynamic_arm(
                arm_id, mode=mode, policy_graph=None, persist=False,
            )
        return None

    async def get_safe_fallback_arm(self, mode: str | None = None) -> PolicyArm:
        """
        Return a safe fallback (no dangerous effects) if one exists, otherwise create/persist
        a single canonical fallback: base.safe_fallback (mode='generic').
        """
        with self._lock:
            if mode:
                for arm in self._by_mode.get(mode, []):
                    if arm.is_safe_fallback:
                        return arm
            for arm_list in self._by_mode.values():
                for arm in arm_list:
                    if arm.is_safe_fallback:
                        return arm

        # Create canonical safe fallback as base.safe_fallback (mode='generic')
        try:
            arm_id = "base.safe_fallback"
            pg = _create_noop_policy_graph(arm_id)
            dimensions = getattr(neural_linear_manager, "dimensions", 64)
            head = NeuralLinearBanditHead(arm_id, dimensions, initial_state=None)
            fallback = PolicyArm(arm_id=arm_id, policy_graph=pg, mode="generic", bandit_head=head)

            with self._lock:
                self._arms[fallback.id] = fallback
                self._by_mode.setdefault(fallback.mode, []).append(fallback)

            try:
                await cypher_query(
                    """
                    MERGE (p:PolicyArm {id: $id})
                    ON CREATE SET p.arm_id = $id, p.mode = $mode, p.policy_graph = $graph
                    ON MATCH  SET p.mode = coalesce(p.mode, $mode),
                                p.policy_graph = coalesce(p.policy_graph, $graph)
                    """,
                    {"id": arm_id, "mode": "generic", "graph": pg.model_dump(mode="json")},
                )
            except Exception as e:
                logger.warning("[ArmRegistry] Persisting safe fallback '%s' failed: %r", arm_id, e)

            logger.warning("[ArmRegistry] Using canonical safe fallback '%s'.", arm_id)
            return fallback

        except Exception as e:
            logger.error("[ArmRegistry] FAILED to create safe fallback: %r", e, exc_info=True)

            # last-resort in-memory shim (still canonical id)
            class _Shim: ...

            shim = _Shim()
            shim.id = "base.safe_fallback"
            shim.mode = "generic"
            shim.policy_graph = _create_noop_policy_graph(shim.id)
            shim.bandit_head = NeuralLinearBanditHead(
                shim.id,
                getattr(neural_linear_manager, "dimensions", 64),
            )
            return shim


# singleton
arm_registry = ArmRegistry()
