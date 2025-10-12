from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Dict, List, Literal, Optional, Protocol, Tuple

from systems.axon.schemas import ActionResult, AxonIntent


class DriverInterface(Protocol):
    """Defines the contract all Axon drivers must adhere to."""

    driver_name: str
    mode: Literal["live", "shadow", "testing"]
    capabilities: list[str]  # optional: ["probe", "push", ...]

    def describe(self) -> dict[str, Any]:
        """Returns metadata about the driver (e.g., name, version, supported_actions)."""
        ...

    async def probe(self, params: dict[str, Any]) -> dict[str, Any]:
        """Executes an on-demand, read-only operation."""
        ...

    async def push(self, intent: AxonIntent) -> ActionResult:
        """Executes a write-operation or complex workflow."""
        ...


class DriverRegistry:
    """Manages the lifecycle and access to Axon drivers."""

    def __init__(self) -> None:
        self._drivers: dict[str, DriverInterface] = {}
        self._statuses: dict[str, Literal["live", "shadow", "testing"]] = {}
        self._capability_map: dict[str, list[str]] = {}
        print("[DriverRegistry] Initialized.")

    # ---------- helpers ----------

    @staticmethod
    def _safe_get_supported_actions(desc: Any, fallback_caps: Iterable[str]) -> list[str]:
        """
        Pull supported actions from a variety of describe() shapes:
        - dict-like: desc.get("supported_actions")
        - pydantic model: getattr(desc, "supported_actions", None)
        - fallback to provided capabilities list
        - final fallback: introspect known callable endpoints on the driver (handled by caller)
        """
        actions: Iterable[str] | None = None

        # dict-like
        if isinstance(desc, dict):
            actions = desc.get("supported_actions") or desc.get("capabilities")

        # attribute-like (e.g., Pydantic model)
        if actions is None:
            actions = getattr(desc, "supported_actions", None) or getattr(
                desc, "capabilities", None
            )

        if actions is None:
            actions = fallback_caps

        # normalize to unique, ordered list
        out: list[str] = []
        for a in actions:
            a = str(a).strip()
            if a and a not in out:
                out.append(a)
        return out

    def _introspect_callable_caps(self, driver: DriverInterface) -> list[str]:
        """As a last resort, infer capabilities by checking known optional methods."""
        caps: list[str] = []
        if hasattr(driver, "probe") and callable(getattr(driver, "probe")):
            caps.append("probe")
        if hasattr(driver, "push") and callable(getattr(driver, "push")):
            caps.append("push")
        return caps

    def _rebuild_capability_map_for_driver(self, driver_name: str, new_caps: Iterable[str]) -> None:
        """Remove stale entries and re-add fresh capability map entries for one driver."""
        # remove stale
        for cap, names in list(self._capability_map.items()):
            if driver_name in names:
                names = [n for n in names if n != driver_name]
                if names:
                    self._capability_map[cap] = names
                else:
                    del self._capability_map[cap]

        # add fresh
        for cap in new_caps:
            self._capability_map.setdefault(cap, [])
            if driver_name not in self._capability_map[cap]:
                self._capability_map[cap].append(driver_name)

    def _map_capabilities(self, driver_name: str, driver: DriverInterface) -> list[str]:
        """Compute and store the capability mapping for a driver. Returns the resolved caps."""
        # Try describe() first
        caps: list[str] = []
        try:
            desc = driver.describe()
        except Exception as e:
            print(f"[DriverRegistry] WARN: describe() failed for '{driver_name}': {e}")
            desc = {}

        # Combine describe-supported, declared .capabilities, and callable introspection
        declared_caps = getattr(driver, "capabilities", []) or []
        caps = self._safe_get_supported_actions(desc, declared_caps)
        if not caps:
            caps = self._introspect_callable_caps(driver)

        if not caps:
            print(
                f"[DriverRegistry] WARN: No capabilities discovered for '{driver_name}'. "
                f"Add supported_actions in describe() or set .capabilities on the driver."
            )

        self._rebuild_capability_map_for_driver(driver_name, caps)
        return caps

    # ---------- public API ----------

    def register(
        self,
        driver_name: str,
        driver: DriverInterface,
        status: Literal["live", "shadow", "testing"] = "testing",
    ) -> None:
        """Registers a driver instance with a given status and wires its capabilities."""
        self._drivers[driver_name] = driver
        self._statuses[driver_name] = status
        caps = self._map_capabilities(driver_name, driver)
        print(
            f"[DriverRegistry] Registered driver: '{driver_name}' "
            f"(status: {status}) caps={caps or '[]'}"
        )

    def unregister(self, driver_name: str) -> None:
        """Unregister a driver and remove its capabilities."""
        if driver_name in self._drivers:
            del self._drivers[driver_name]
        if driver_name in self._statuses:
            del self._statuses[driver_name]
        # remove from capability map
        for cap, names in list(self._capability_map.items()):
            if driver_name in names:
                names = [n for n in names if n != driver_name]
                if names:
                    self._capability_map[cap] = names
                else:
                    del self._capability_map[cap]
        print(f"[DriverRegistry] Unregistered driver: '{driver_name}'")

    def get(self, driver_name: str) -> DriverInterface | None:
        """Gets a driver by its unique name."""
        return self._drivers.get(driver_name)

    def list_drivers(self) -> list[tuple[str, str, list[str]]]:
        """Returns [(name, status, caps...)] for debugging/UI."""
        out: list[tuple[str, str, list[str]]] = []
        for name, drv in self._drivers.items():
            caps = []
            # prefer describe() values for visibility
            try:
                caps = self._safe_get_supported_actions(
                    drv.describe(), getattr(drv, "capabilities", [])
                )
            except Exception:
                caps = getattr(drv, "capabilities", []) or self._introspect_callable_caps(drv)
            out.append((name, self._statuses.get(name, "?"), caps))
        return out

    def get_shadow_drivers_for_capability(self, capability: str) -> list[DriverInterface]:
        """Finds all registered shadow drivers that support a given capability."""
        drivers: list[DriverInterface] = []
        for name in self._capability_map.get(capability, []):
            if self._statuses.get(name) == "shadow":
                drv = self.get(name)
                if drv:
                    drivers.append(drv)
        return drivers

    def get_live_driver_for_capability(self, capability: str) -> DriverInterface | None:
        """Finds the single active 'live' driver for a given capability."""
        for name in self._capability_map.get(capability, []):
            if self._statuses.get(name) == "live":
                return self.get(name)
        return None

    def debug_dump(self) -> None:
        """Print a concise map for troubleshooting."""
        print("[DriverRegistry] Drivers:")
        for name, status, caps in self.list_drivers():
            print(f"  - {name:20} status={status:7} caps={caps}")
        print("[DriverRegistry] Capability map:")
        for cap, names in self._capability_map.items():
            print(f"  - {cap:12} -> {names}")
