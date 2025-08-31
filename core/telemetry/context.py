from __future__ import annotations

import contextvars
import uuid
from typing import Any

from .harvest import harvest_headers, merge_metrics


class TelemetryContext:
    """
    Per-episode accumulator. Always safe to use (no-op when disabled).
    """

    __slots__ = ("episode_id", "task_key", "enabled", "blob", "correlation")

    def __init__(
        self,
        *,
        episode_id: str | None = None,
        task_key: str | None = None,
        enabled: bool = True,
    ) -> None:
        self.episode_id = episode_id
        self.task_key = task_key
        self.enabled = enabled
        self.blob: dict[str, Any] = {}
        self.correlation: dict[str, Any] = {}

    def note_request(
        self,
        *,
        decision_id: str | None = None,
        budget_ms: int | None = None,
        spec_id: str | None = None,
        spec_version: str | None = None,
        arm_id: str | None = None,
    ) -> dict[str, str]:
        """
        Build headers to inject on outbound requests (correlation). Missing values are omitted.
        """
        if not self.enabled:
            return {}
        hdrs: dict[str, str] = {}
        if decision_id:
            hdrs["X-Decision-Id"] = decision_id
            self.correlation["decision_id"] = decision_id
        if budget_ms is not None:
            hdrs["X-Budget-MS"] = str(budget_ms)
            self.correlation["budget_ms"] = budget_ms
        if spec_id:
            hdrs["X-Spec-ID"] = spec_id
        if spec_version:
            hdrs["X-Spec-Version"] = spec_version
        if arm_id:
            hdrs["X-Arm-ID"] = arm_id
        hdrs["X-Call-ID"] = str(uuid.uuid4())
        return hdrs

    def note_response(self, headers: dict[str, str], *, service_hint: str | None = None) -> None:
        if not self.enabled:
            return
        mm = harvest_headers(headers, service_hint=service_hint)
        merge_metrics(self.blob, mm)

    def snapshot(self) -> dict[str, Any]:
        out = dict(self.blob)
        if self.correlation:
            out["correlation"] = {**out.get("correlation", {}), **self.correlation}
        return out


_current_ctx: contextvars.ContextVar[TelemetryContext] = contextvars.ContextVar(
    "telemetry_ctx",
    default=TelemetryContext(enabled=False),
)


def get_ctx() -> TelemetryContext:
    return _current_ctx.get()


def bind_episode(
    episode_id: str,
    *,
    task_key: str | None = None,
    enabled: bool = True,
) -> TelemetryContext:
    ctx = TelemetryContext(episode_id=episode_id, task_key=task_key, enabled=enabled)
    _current_ctx.set(ctx)
    return ctx
