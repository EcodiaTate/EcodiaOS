# systems/axon/mesh/promoter.py
from __future__ import annotations

from typing import Any

from systems.axon.dependencies import get_lifecycle_manager, get_scorecard_manager

# highlight-start
from systems.axon.mesh.attestation import AttestationPolicy, verify_attestation
from systems.axon.mesh.lifecycle import DriverStatus

# highlight-end


class PromotionPolicy:
    def __init__(
        self, max_p95_ms: int = 1200, min_uplift: float = 0.02, min_window: int = 50
    ) -> None:
        self.max_p95_ms = max_p95_ms
        self.min_uplift = min_uplift
        self.min_window = min_window

    def ok(self, scorecard_like: Any) -> bool:
        """
        Accepts either: Scorecard window dict or an object with needed attrs.
        """
        try:
            window_size = float(
                getattr(scorecard_like, "window_size", scorecard_like.get("window_size"))
            )
            p95_ms = float(getattr(scorecard_like, "p95_ms", scorecard_like.get("p95_ms")))
            uplift = float(
                getattr(scorecard_like, "uplift_vs_incumbent", scorecard_like.get("avg_uplift"))
            )
            return (
                window_size >= self.min_window
                and p95_ms <= self.max_p95_ms
                and uplift >= self.min_uplift
            )
        except Exception:
            return False


def _status_eq(current_status: Any, target: DriverStatus) -> bool:
    try:
        if isinstance(current_status, str):
            return current_status == target or current_status == getattr(target, "value", target)
        return current_status == target
    except Exception:
        return False


def _coerce_like(template: Any, desired: DriverStatus):
    if isinstance(template, str):
        return desired  # we use the literal string values in lifecycle
    return desired


async def promote_if_ready(
    driver_name: str, *, incumbent: str | None = None, policy: PromotionPolicy | None = None
) -> bool:
    """
    Advance testing → shadow → live when window metrics pass policy AND attestation is bound.
    """
    policy = policy or PromotionPolicy()
    lifecycle = get_lifecycle_manager()
    scores = get_scorecard_manager()
    # highlight-start
    attestation_policy = AttestationPolicy()

    state = lifecycle.get_driver_state(driver_name)
    if not state:
        return False
    # highlight-end

    # use rolling-window metrics
    wm = scores.get_window_metrics(driver_name, window_n=200)
    if not wm or not policy.ok(wm):
        return False

    # highlight-start
    # attestation guard (artifact hash + optional signature)
    if not verify_attestation(state.spec, policy=attestation_policy):
        return False
    # highlight-end

    # testing → shadow
    if _status_eq(state.status, "testing"):
        lifecycle.update_driver_status(driver_name, _coerce_like(state.status, "shadow"))  # type: ignore[arg-type]
        return True

    # shadow → live (optionally demote incumbent)
    if _status_eq(state.status, "shadow"):
        if incumbent and incumbent != driver_name:
            lifecycle.update_driver_status(
                incumbent, _coerce_like(state.status, "shadow")
            )  # demote live to shadow
        lifecycle.update_driver_status(
            driver_name, _coerce_like(state.status, "live")
        )  # promote shadow to live
        return True

    return False
