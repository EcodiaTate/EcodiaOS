from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import Any

from .client import SynapseClient

MetricsFn = Callable[[Any, BaseException | None, float], dict[str, Any]]
TaskKeyFn = Callable[[dict[str, Any]], str]
AffordancesFn = Callable[[dict[str, Any]], list]


def evolutionary(
    *,
    task_key_fn: TaskKeyFn,
    mode_hint: str | None = None,
    metrics_fn: MetricsFn | None = None,
    affordances_fn: AffordancesFn | None = None,
):
    """
    Wrap a decision path so it always:
    1) Calls Synapse hint (planner -> bandit -> firewall -> episode)
    2) Executes using the chosen arm config
    3) Logs reward via ingest

    The wrapped function signature must be: fn(hint_response: dict, context: dict, *args, **kwargs)
    and return a result object that metrics_fn can read.
    """

    def deco(fn):
        @functools.wraps(fn)
        async def wrapped(context: dict[str, Any], *args, **kwargs):
            sc = SynapseClient()
            tk = task_key_fn(context)
            affordances = (
                affordances_fn(context) if affordances_fn else context.get("affordances", [])
            )
            hint = await sc.hint(
                task_key=tk,
                mode_hint=mode_hint,
                context=context,
                affordances=affordances,
                acceptance_criteria=context.get("acceptance_criteria"),
                observability=context.get("observability"),
                parent_episode_id=context.get("parent_episode_id"),
                context_vector=context.get("context_vector"),
                _test_mode=context.get("_test_mode"),
            )
            start = time.time()
            result = None
            error: BaseException | None = None
            try:
                result = await fn(hint, context, *args, **kwargs)
                return result
            except BaseException as e:  # intentional: log reward even on hard failures
                error = e
                raise
            finally:
                elapsed_ms = (time.time() - start) * 1000.0
                default_metrics = {
                    "latency_ms": elapsed_ms,
                    "ok": 0 if error else 1,
                }
                computed = metrics_fn(result, error, elapsed_ms) if metrics_fn else default_metrics
                # Require scalar reward; if your service computes it, place in context["reward"]
                reward = float(
                    context.get("reward", computed.get("reward", 1.0 if not error else 0.0)),
                )
                await sc.ingest_reward(
                    episode_id=hint["episode_id"],
                    task_key=tk,
                    reward=reward,
                    metrics=computed,
                )

        return wrapped

    return deco
