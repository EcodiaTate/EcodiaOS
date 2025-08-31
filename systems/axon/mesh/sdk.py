# systems/axon/mesh/sdk.py
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, Literal

from pydantic import BaseModel, Field

from systems.axon.schemas import ActionResult, AxonEvent, AxonIntent


class CapabilitySpec(BaseModel):
    """describe() output"""
    driver_name: str
    driver_version: str
    supported_actions: list[str] = Field(..., description="Capabilities this driver can push.")
    risk_profile: dict[str, str] = Field(..., description="action → risk tier")
    budget_model: dict[str, float] = Field(..., description="action → est. cost")
    auth_requirements: list[str] = Field(..., description="e.g., api_key, oauth2")


class HealthStatus(BaseModel):
    status: Literal["ok", "degraded", "error"]
    details: str = ""
    dependencies: dict[str, Literal["ok", "error"]] = Field(default_factory=dict)


class ReplayCapsule(BaseModel):
    """bit-exact replay bundle"""
    id: str
    type: Literal["event", "intent"]
    driver_version: str
    environment_hash: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]


class DriverInterface(ABC):
    """
    Canonical Axon driver SDK — now async to match real drivers.
    """

    @abstractmethod
    def describe(self) -> CapabilitySpec:  # sync is fine here
        ...

    @abstractmethod
    async def pull(self, params: dict[str, Any]) -> AsyncIterator[AxonEvent]:
        """
        Sense loop: yield AxonEvent(s). Implement only if the driver is a pull/sensor.
        """
        if False:  # pragma: no cover (interface)
            yield AxonEvent()  # type: ignore

    @abstractmethod
    async def push(self, intent: AxonIntent) -> ActionResult:
        """
        Execute a capability. Must honor constraints.dry_run when present.
        """
        ...

    @abstractmethod
    async def self_test(self) -> HealthStatus:
        """
        Lightweight dependency/health probe for lifecycle + probecraft.
        """
        ...

    @abstractmethod
    async def repro_bundle(self, *, id: str, kind: Literal["event", "intent"]) -> ReplayCapsule:
        """
        Build and return a deterministic replay capsule for the given item.
        """
        ...
