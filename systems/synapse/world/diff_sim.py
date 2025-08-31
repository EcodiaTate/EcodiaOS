# systems/synapse/world/diff_sim.py
from __future__ import annotations

import copy
import math
from collections.abc import Callable
from typing import Any

import numpy as np

from systems.synapse.policy.policy_dsl import PolicyGraph


def _deepcopy_graph(g: PolicyGraph) -> PolicyGraph:
    try:
        # Some PolicyGraph impls support copy(deep=True)
        return g.copy(deep=True)  # type: ignore[arg-type]
    except Exception:
        return copy.deepcopy(g)


def _evaluate(
    loss_fn: Callable[[PolicyGraph, np.ndarray], float],
    graph: PolicyGraph,
    x: np.ndarray,
) -> float:
    val = loss_fn(graph, x)
    if not isinstance(val, int | float) or not math.isfinite(float(val)):
        raise ValueError("loss_fn must return a finite scalar.")
    return float(val)


def _numeric_params(graph: PolicyGraph) -> list[tuple[int, str, float]]:
    """
    Collect (node_index, key, value) for numeric params.
    """
    out: list[tuple[int, str, float]] = []
    for i, n in enumerate(getattr(graph, "nodes", [])):
        params = getattr(n, "params", None) or {}
        for k, v in list(params.items()):
            if isinstance(v, int | float) and math.isfinite(float(v)):
                out.append((i, k, float(v)))
    return out


def _guess_bounds(node: Any, key: str, v: float) -> tuple[float, float] | None:
    """
    Try to discover/guess sensible bounds for a parameter.
    Priority:
      1) node.param_bounds.get(key) or node.bounds.get(key) if present
      2) Heuristics for common names
    """
    for attr in ("param_bounds", "bounds"):
        b = getattr(node, attr, None)
        if (
            isinstance(b, dict)
            and key in b
            and isinstance(b[key], tuple | list)
            and len(b[key]) == 2
        ):
            lo, hi = float(b[key][0]), float(b[key][1])
            return (min(lo, hi), max(lo, hi))

    # Heuristics
    name = key.lower()
    if name in ("temperature", "temp"):
        return (0.0, 2.0)
    if "prob" in name or "probability" in name:
        return (0.0, 1.0)
    if name.endswith("_rate") or name.endswith("rate"):
        return (0.0, 1.0)
    # Unknown → unbounded
    return None


def _clamp(val: float, bounds: tuple[float, float] | None) -> float:
    if bounds is None:
        return val
    lo, hi = bounds
    return max(lo, min(hi, val))


def _finite_diff_grad(
    loss_fn: Callable[[PolicyGraph, np.ndarray], float],
    base_graph: PolicyGraph,
    x: np.ndarray,
    idx: int,
    key: str,
    eps: float,
) -> float:
    """
    Central finite difference dL/d(param)
    """
    g1 = _deepcopy_graph(base_graph)
    g2 = _deepcopy_graph(base_graph)

    v = float(getattr(g1.nodes[idx], "params")[key])
    getattr(g1.nodes[idx], "params")[key] = v + eps
    getattr(g2.nodes[idx], "params")[key] = v - eps

    f1 = _evaluate(loss_fn, g1, x)
    f2 = _evaluate(loss_fn, g2, x)
    return (f1 - f2) / (2.0 * eps)


def grad_optimize(
    plan_graph: PolicyGraph,
    x: np.ndarray,
    loss_fn: Callable,
    steps: int = 8,
) -> PolicyGraph:
    """
    Optimize continuous parameters in a plan by **finite-difference gradient descent**.
    - Detects all numeric node.params[*] across the PolicyGraph.
    - Computes central-difference gradients for each param.
    - Applies bounded updates (if bounds known/heuristically inferred).
    - Uses simple backoff if a step doesn't improve the loss.

    Arguments:
      plan_graph: PolicyGraph to optimize (not mutated; a deep copy is returned)
      x:          Context vector/array fed to loss_fn
      loss_fn:    Callable(graph, x) -> scalar loss (lower is better)
      steps:      Number of outer GD iterations
    """
    if steps <= 0:
        return plan_graph

    g = _deepcopy_graph(plan_graph)

    # Collect optimizable params once (layout assumed stable across steps)
    numeric = _numeric_params(g)
    if not numeric:
        # Nothing to optimize; return deep copy unchanged
        return g

    # Pre-compute param bounds map for speed
    bounds: dict[tuple[int, str], tuple[float, float] | None] = {}
    for i, k, v in numeric:
        node = g.nodes[i]
        bounds[(i, k)] = _guess_bounds(node, k, v)

    # Hyperparameters (kept internal to preserve the public signature)
    base_lr = 0.05
    eps = 1e-3
    max_backoff = 4
    grad_clip = 1e3  # clip by global L2 norm

    # Baseline loss
    best_loss = _evaluate(loss_fn, g, x)

    for t in range(steps):
        # Compute gradients at current point
        grads: dict[tuple[int, str], float] = {}
        for i, k, _ in numeric:
            try:
                grads[(i, k)] = _finite_diff_grad(loss_fn, g, x, i, k, eps=eps)
            except Exception:
                # If a particular derivative fails (e.g., non-finite), treat as zero
                grads[(i, k)] = 0.0

        # Global gradient clipping
        gvec = np.array(list(grads.values()), dtype=float)
        norm = float(np.linalg.norm(gvec)) if gvec.size else 0.0
        scale = 1.0
        if norm > grad_clip and norm > 0:
            scale = grad_clip / norm

        # Learning rate schedule (mild decay)
        lr = base_lr / (1.0 + 0.3 * t)

        # Propose update
        def _apply_update(src_graph: PolicyGraph, factor: float) -> PolicyGraph:
            h = _deepcopy_graph(src_graph)
            for i, k, _v0 in numeric:
                v = float(getattr(h.nodes[i], "params")[k])
                gk = grads[(i, k)] * scale
                new_v = v - factor * lr * gk  # gradient descent
                new_v = _clamp(new_v, bounds[(i, k)])

                # Preserve integer types if original was int
                orig_v = getattr(src_graph.nodes[i], "params")[k]
                if isinstance(orig_v, int):
                    new_v = int(round(new_v))
                getattr(h.nodes[i], "params")[k] = new_v
            return h

        # Backoff line search if loss doesn't improve
        factor = 1.0
        for _ in range(max_backoff + 1):
            cand = _apply_update(g, factor)
            cand_loss = _evaluate(loss_fn, cand, x)
            if cand_loss < best_loss:
                g = cand
                best_loss = cand_loss
                break
            factor *= 0.5  # shrink step and retry

        # If no improvement after backoff attempts, we still continue;
        # often later steps can help once eps/lr schedule progresses.

    return g
