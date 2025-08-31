# systems/synapse/core/registry.py
# FINAL VERSION — COMPATIBLE, BOOTSTRAPPABLE, PERSISTENCE-AWARE, COLD-START SAFE
from __future__ import annotations

import inspect
import json
import os
import threading
from collections.abc import Iterable
from typing import Any

from core.utils.neo.cypher_query import cypher_query
from systems.synapse.policy.policy_dsl import PolicyGraph
from systems.synapse.training.neural_linear import NeuralLinearBanditHead, neural_linear_manager

# -----------------------
# Helpers
# -----------------------


def _coerce_policy_graph(pg_like: Any) -> PolicyGraph:
    """
    Accept dict / JSON string / PolicyGraph and return a PolicyGraph.
    Robust across Pydantic v1/v2.
    """
    if isinstance(pg_like, PolicyGraph):
        return pg_like

    if isinstance(pg_like, str):
        try:
            pg_like = json.loads(pg_like)
        except Exception as e:
            raise ValueError(f"policy_graph JSON parse failed: {e}")

    if not isinstance(pg_like, dict):
        raise TypeError(f"Unsupported policy_graph type: {type(pg_like).__name__}")

    # Try v2 first
    if hasattr(PolicyGraph, "model_validate"):
        return PolicyGraph.model_validate(pg_like)  # type: ignore[attr-defined]

    # Fallback v1-style
    return PolicyGraph(**pg_like)  # type: ignore[call-arg]


from collections.abc import Iterable  # (or keep typing.Iterable)


def _node_effects_says_dangerous(node: Any) -> bool:
    try:
        eff = (
            getattr(node, "effects", None)
            if hasattr(node, "effects")
            else (node.get("effects") if isinstance(node, dict) else None)
        )
        if not eff:
            return False
        dangerous = {"write", "net_access", "execute"}

        # --- fix: treat strings atomically, iterate only non-string iterables ---
        if isinstance(eff, str):
            items = {eff}
        elif isinstance(eff, Iterable):
            items = set(eff)
        else:
            items = {eff}

        return any(x in dangerous for x in items)
    except Exception:
        return False


async def _maybe_await(v):
    """Allow both sync and async cypher_query implementations."""
    if inspect.isawaitable(v):
        return await v
    return v


def _default_llm_model() -> str:
    return os.getenv("DEFAULT_LLM_MODEL", "gpt-4o-mini")


def _noop_pg_dict(arm_id: str) -> dict[str, Any]:
    """Minimal, safe, model-agnostic policy graph as dict."""
    return {
        "id": arm_id,
        "nodes": [
            {
                "id": "prompt",
                "type": "prompt",
                "model": _default_llm_model(),
                "params": {"temperature": 0.1},
                # NOTE: no 'effects' field => safe by design
            },
        ],
        "edges": [],
    }


# -----------------------
# Core types
# -----------------------


class PolicyArm:
    """
    A selectable action/policy configuration with learned bandit head.
    """

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
        self.mode: str = mode or "planful"
        self.bandit_head: NeuralLinearBanditHead = bandit_head

    @property
    def is_safe_fallback(self) -> bool:
        """
        Consider an arm safe if no node declares dangerous effects.
        Missing 'effects' => safe.
        """
        try:
            nodes = getattr(self.policy_graph, "nodes", [])
        except Exception:
            nodes = []
        for n in nodes or []:
            if _node_effects_says_dangerous(n):
                return False
        return True


class ArmRegistry:
    """
    Canonical in-memory source of truth for available stateful PolicyArms.
    Hydrates from graph (policy + learned head state). Also supports
    in-process bootstrapping via add_arm (ephemeral unless persisted by caller).
    """

    _instance: ArmRegistry | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self._arms: dict[str, PolicyArm] = {}
        self._by_mode: dict[str, list[PolicyArm]] = {}
        self._lock = threading.RLock()

    # -----------------------
    # Persistence hydration
    # -----------------------

    async def initialize(self) -> None:
        """
        Loads PolicyArm nodes from Neo4j, hydrating with policy graph and
        bandit head state. If nothing can be loaded, perform cold-start seeding.
        Never raises.
        """
        print("[ArmRegistry] Initializing and hydrating state from graph...")
        query = """
        MATCH (p:PolicyArm)
        RETURN
          coalesce(p.arm_id, p.id) AS arm_id,
          p.policy_graph            AS policy_graph,
          coalesce(p.mode,'planful') AS mode,
          p.A AS A, p.A_shape AS A_shape,
          p.b AS b, p.b_shape AS b_shape
        """

        rows = []
        try:
            rows = await _maybe_await(cypher_query(query)) or []
        except Exception as e:
            print(f"[ArmRegistry] WARNING: cypher_query failed during init: {e}")

        new_arms: dict[str, PolicyArm] = {}
        new_by_mode: dict[str, list[PolicyArm]] = {}
        added = 0

        # Be resilient: dimensions may not be initialized yet.
        dimensions = getattr(neural_linear_manager, "dimensions", None) or 64

        for row in rows:
            arm_id = row.get("arm_id")
            graph_raw = row.get("policy_graph")
            mode = row.get("mode") or "planful"
            if not arm_id or not graph_raw:
                continue
            try:
                pg = _coerce_policy_graph(graph_raw)
                initial_state = None
                if row.get("A") and row.get("A_shape") and row.get("b") and row.get("b_shape"):
                    initial_state = {
                        "A": row["A"],
                        "A_shape": row["A_shape"],
                        "b": row["b"],
                        "b_shape": row["b_shape"],
                    }
                head = NeuralLinearBanditHead(arm_id, dimensions, initial_state=initial_state)
                arm = PolicyArm(arm_id=arm_id, policy_graph=pg, mode=mode, bandit_head=head)
            except Exception as e:
                print(f"[ArmRegistry] ERROR: Could not hydrate PolicyArm '{arm_id}': {e}")
                continue

            new_arms[arm.id] = arm
            new_by_mode.setdefault(arm.mode, []).append(arm)
            added += 1

        with self._lock:
            self._arms = new_arms
            self._by_mode = new_by_mode

        print(f"[ArmRegistry] Initialized with {added} stateful PolicyGraph arms.")

        # Cold-start guarantee: ensure safe fallbacks for key modes exist.
        self.ensure_cold_start(min_modes=("planful", "greedy"))

    async def reload(self) -> None:
        await self.initialize()

    # -----------------------
    # Query / accessors
    # -----------------------

    def get_arm(self, arm_id: str) -> PolicyArm | None:
        with self._lock:
            return self._arms.get(arm_id)

    def get_arms_for_mode(self, mode: str) -> list[PolicyArm]:
        with self._lock:
            return list(self._by_mode.get(mode, []))

    # Backward/compat alias used by other modules
    def list_arms_for_mode(self, mode: str) -> list[PolicyArm]:
        return self.get_arms_for_mode(mode)

    def list_modes(self) -> list[str]:
        with self._lock:
            return sorted(self._by_mode.keys())

    def all_arm_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._arms.keys())

    # -----------------------
    # Mutation (in-memory)
    # -----------------------

    def add_arm(self, *args, **kwargs) -> None:
        """
        Flexible, signature-tolerant add:
          add_arm(arm_id, policy_graph, mode, meta?)
          add_arm(arm_id=..., policy_graph=..., mode=..., meta=...)
          add_arm(arm_id, policy_graph, meta={...})  # mode optional
        Persists in-memory only; caller may write to graph separately if desired.
        """
        # Normalize inputs
        if args and not kwargs:
            # Try positional forms
            if len(args) == 4:
                arm_id, pg_like, mode, _meta = args
            elif len(args) == 3:
                arm_id, pg_like, third = args
                if isinstance(third, str):
                    mode, _meta = third, None
                else:
                    mode, _meta = "planful", third
            else:
                raise TypeError("add_arm expects 3 or 4 positional args or keyword args")
        else:
            arm_id = kwargs.get("arm_id")
            pg_like = kwargs.get("policy_graph")
            mode = kwargs.get("mode") or "planful"
            _meta = kwargs.get("meta")

        if not arm_id or pg_like is None:
            raise ValueError("add_arm requires arm_id and policy_graph")

        # Coerce PolicyGraph and create a fresh bandit head
        pg = _coerce_policy_graph(pg_like)
        dimensions = getattr(neural_linear_manager, "dimensions", None) or 64
        head = NeuralLinearBanditHead(arm_id, dimensions)

        arm = PolicyArm(arm_id=arm_id, policy_graph=pg, mode=mode, bandit_head=head)

        with self._lock:
            self._arms[arm.id] = arm
            self._by_mode.setdefault(arm.mode, []).append(arm)

        print(f"[ArmRegistry] Added arm '{arm.id}' (mode='{arm.mode}') [ephemeral].")

    def get_safe_fallback_arm(self, mode: str | None = None) -> PolicyArm:
        with self._lock:
            if mode:
                for arm in self._by_mode.get(mode, []):
                    if arm.is_safe_fallback:
                        return arm
            for arm_list in self._by_mode.values():
                for arm in arm_list:
                    if arm.is_safe_fallback:
                        return arm

        # No safe arms → seed and try again
        self.ensure_cold_start(min_modes=(mode,) if mode else ("planful", "greedy"))

        with self._lock:
            if mode:
                for arm in self._by_mode.get(mode, []):
                    if arm.is_safe_fallback:
                        return arm
            for arm_list in self._by_mode.values():
                for arm in arm_list:
                    if arm.is_safe_fallback:
                        return arm

        raise RuntimeError(
            "CRITICAL: No SAFE fallback arm is available, even after cold-start seeding.",
        )

    # -----------------------
    # Cold-start seeding
    # -----------------------

    def ensure_cold_start(self, *, min_modes: Iterable[str] = ("planful", "greedy")) -> None:
        """
        Idempotent: guarantees at least one SAFE fallback arm exists for each mode in `min_modes`.
        Prefers using an external bootstrap helper if present; otherwise seeds inline.
        A "SAFE" arm is one where PolicyGraph nodes have no 'effects' that imply write/net/exec.
        """

        def _safe_present_for(mode: str) -> bool:
            with self._lock:
                return any(a.is_safe_fallback for a in self._by_mode.get(mode, []))

        # 1) Fast path: if all requested modes already have a safe arm, return
        with self._lock:
            missing = [m for m in min_modes if not _safe_present_for(m)]
        if not missing:
            return

        # 2) Try external bootstrap (keeps one source-of-truth for seeding if your project has it)
        try:
            # Support both legacy and new function names
            mod = __import__("systems.synapse.core.registry_bootstrap", fromlist=["*"])
            fn = None
            for name in ("ensure_minimum_arms", "seed_minimum_arms"):
                fn = getattr(mod, name, None) or fn
            if fn:
                import inspect as _inspect

                if len(_inspect.signature(fn).parameters) >= 1:
                    fn(self)  # pass registry if supported
                else:
                    fn()  # no-arg bootstrap
                with self._lock:
                    missing = [m for m in min_modes if not _safe_present_for(m)]
                if not missing:
                    print(
                        "[ArmRegistry] Cold-start seeding via registry_bootstrap ensured minimum SAFE arms.",
                    )
                    return
        except Exception as e:
            print(
                f"[ArmRegistry] Bootstrap helper unavailable/failed ({e}); falling back to inline seeding.",
            )

        # 3) Inline SAFE seeding (last resort)
        for mode in missing:
            base_id = f"noop_safe_{mode}"
            with self._lock:
                existing_ids = set(self._arms.keys())
            arm_id = base_id
            suffix = 1
            while arm_id in existing_ids:
                suffix += 1
                arm_id = f"{base_id}_{suffix}"

            try:
                pg = _coerce_policy_graph(
                    _noop_pg_dict(arm_id),
                )  # SAFE graph: prompt-only, low-temp, no effects
                self.add_arm(
                    arm_id=arm_id,
                    policy_graph=pg,
                    mode=mode,
                    meta={"kind": "noop", "cold_start": True},
                )
                print(f"[ArmRegistry] Inline-seeded SAFE fallback '{arm_id}' for mode '{mode}'.")
            except Exception as e:
                print(f"[ArmRegistry] ERROR: Inline seeding failed for mode '{mode}': {e}")

        # 4) Final safety check: if still missing, escalate hard (this should be practically unreachable)
        with self._lock:
            still_missing = [m for m in min_modes if not _safe_present_for(m)]
        if still_missing:
            raise RuntimeError(
                f"CRITICAL: No SAFE fallback arms available after cold-start for modes: {still_missing}",
            )


arm_registry = ArmRegistry()
