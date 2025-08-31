from __future__ import annotations

import traceback
from contextlib import asynccontextmanager
from typing import Any

from core.telemetry.context import get_ctx
from core.telemetry.outcome_sink import send_episode_outcome

_OUTCOME_SENT = "__eos_outcome_sent__"


@asynccontextmanager
async def episode_outcome(task_key: str, *, extra_success_fields: dict[str, Any] | None = None):
    """
    Wrap a workflow so we ALWAYS write one outcome.
    If someone accidentally calls the sink again, this block no-ops on the second write.
    """
    ctx = get_ctx()
    if not getattr(ctx, "enabled", False) or not getattr(ctx, "episode_id", None):
        yield
        return

    # idempotence guard
    if getattr(ctx, _OUTCOME_SENT, False):
        yield
        return

    ok = True
    err_payload: dict[str, Any] = {}
    try:
        yield
    except Exception as e:
        ok = False
        err_payload = {
            "success.error_type": e.__class__.__name__,
            "success.error_msg": str(e)[:256],
            "success.trace_hint": "".join(traceback.format_tb(e.__traceback__))[-512:],
        }
        raise
    finally:
        extra = {"success.ok": ok}
        if extra_success_fields:
            extra.update({k: v for k, v in extra_success_fields.items() if v is not None})
        extra.update(err_payload)

        await send_episode_outcome(
            task_key=task_key,
            episode_id=ctx.episode_id,
            extra_metrics=extra,
        )
        setattr(ctx, _OUTCOME_SENT, True)
