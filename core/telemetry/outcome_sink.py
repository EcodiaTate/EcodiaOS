from __future__ import annotations

from typing import Any

from core.services.synapse import synapse
from core.telemetry.context import get_ctx

from .budget import ensure_budget_fields


async def send_episode_outcome(
    *,
    task_key: str,
    episode_id: str,
    extra_metrics: dict[str, Any] | None = None,
    outcome: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Single write to Synapse; merges accumulated telemetry blob + caller-supplied metrics.
    """
    ctx = get_ctx()
    blob = ctx.snapshot() if ctx.enabled else {}
    # Add budget lens (spent_ms) if not already present.
    blob = ensure_budget_fields(blob)
    if extra_metrics:
        for k, v in extra_metrics.items():
            if v is not None:
                blob[k] = v
    # EOS-canonical: write once to /synapse/ingest/outcome
    return await synapse.log_outcome(episode_id=episode_id, task_key=task_key, metrics=blob)
