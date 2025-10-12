# systems/axon/mesh/sdk.py
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, Literal

from pydantic import BaseModel, Field

from systems.axon.schemas import ActionResult, AxonEvent, AxonIntent

# -----------------------------------------------------------------------------
# Capability / Health / Replay models
# -----------------------------------------------------------------------------


class CapabilitySpec(BaseModel):
    """describe() output — what this driver can do and what it needs."""

    driver_name: str
    driver_version: str
    # NOTE: For pull/probe/push we keep simple action strings. Examples:
    #  - "pull:rss"        (yield events via pull)
    #  - "probe:search"    (on-demand API lookup)
    #  - "push:send_sms"   (perform an action with side-effects)
    supported_actions: list[str] = Field(..., description="Capabilities this driver exposes.")
    risk_profile: dict[str, str] = Field(..., description="action → risk tier")
    budget_model: dict[str, float] = Field(..., description="action → est. cost")
    auth_requirements: list[str] = Field(..., description="e.g., api_key, oauth2")


class HealthStatus(BaseModel):
    status: Literal["ok", "degraded", "error"]
    details: str = ""
    dependencies: dict[str, Literal["ok", "error"]] = Field(default_factory=dict)


class ReplayCapsule(BaseModel):
    """Bit-exact replay bundle for events or intents."""

    id: str
    type: Literal["event", "intent"]
    driver_version: str
    environment_hash: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]


# -----------------------------------------------------------------------------
# Driver SDK
# -----------------------------------------------------------------------------


class DriverInterface(ABC):
    """
    Canonical Axon Driver SDK.

    Modes:
      - poll   : implements pull() to yield AxonEvents for SenseLoop
      - probe  : implements probe() for on-demand queries (Voxis tools)
      - hybrid : supports both

    We provide safe defaults so probe-only drivers don't have to implement pull(),
    and poll-only drivers don't have to implement probe()/push().
    """

    # Declared by concrete drivers
    MODE: Literal["poll", "probe", "hybrid"] = "poll"
    NAME: str = "driver"
    VERSION: str = "1.0.0"

    # ---- Required basics -----------------------------------------------------

    @abstractmethod
    def describe(self) -> CapabilitySpec:
        """Return static capabilities / auth / budget info."""
        ...

    @abstractmethod
    async def self_test(self) -> HealthStatus:
        """Lightweight dependency/health probe (used by lifecycle & probecraft)."""
        ...

    @abstractmethod
    async def repro_bundle(self, *, id: str, kind: Literal["event", "intent"]) -> ReplayCapsule:
        """Build and return a deterministic replay capsule for the given item."""
        ...

    # ---- Optional surfaces (safe defaults) ----------------------------------

    async def pull(self, params: dict[str, Any]) -> AsyncIterator[AxonEvent]:
        """
        Sense loop: yield AxonEvent(s).
        Default: no events (so probe-only drivers don't need to implement this).
        """
        if False:  # pragma: no cover
            yield AxonEvent()  # type: ignore

    async def probe(self, params: dict[str, Any]) -> Any:
        """
        On-demand lookup (for Voxis tools).
        Default: not supported.
        """
        raise NotImplementedError(f"{self.NAME} does not support probe()")

    async def push(self, intent: AxonIntent) -> ActionResult:
        """
        Perform an action with side-effects.
        Default: not supported.
        """
        return ActionResult(
            ok=False,
            detail=f"{self.NAME} does not support push()",
            data={},
        )
