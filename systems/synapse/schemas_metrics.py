from __future__ import annotations

from pydantic import BaseModel

from core.telemetry.schemas import MetricDatum


class ArmOutcome(BaseModel):
    # whatever you already have for outcomes...
    task_key: str
    decision_id: str | None = None
    arm_id: str | None = None
    reward: float | None = None
    info: dict | None = None
    # NEW (optional): attach arm-scoped metrics directly on the outcome
    metrics: list[MetricDatum] | None = None
