# systems/axon/mesh/registry.py
from __future__ import annotations

from typing import Iterable

import importlib.util

from systems.axon.mesh.attestation import AttestationPolicy, verify_attestation
from systems.axon.mesh.lifecycle import DriverStatus
from systems.axon.mesh.sdk import DriverInterface


class DriverRegistry:
    """
    Manages driver lifecycle & routing with status-aware dispatch.
    Enforces attestation when a driver is 'live' (configurable).
    """

    def __init__(self):
        self._drivers: dict[str, DriverInterface] = {}
        self._capability_map: dict[str, list[str]] = {}
        self._driver_statuses: dict[str, DriverStatus] = {}
        self._policy = AttestationPolicy()

    # ---------- Introspection ----------

    def list_all(self) -> Iterable[DriverInterface]:
        return list(self._drivers.values())

    def describe(self, driver_name: str) -> dict | None:
        d = self._drivers.get(driver_name)
        try:
            return d.describe().model_dump() if d else None
        except Exception:
            return None
            
# highlight-start
    def list_capabilities(self) -> list[str]:
        """Returns a list of all unique capability strings known to the registry."""
        return sorted(self._capability_map.keys())
# highlight-end

    # ---------- Registration / Loading ----------

    def _map_capabilities(self, driver: DriverInterface) -> None:
        spec = driver.describe()
        # remove stale entries for this driver
        for cap, names in list(self._capability_map.items()):
            self._capability_map[cap] = [n for n in names if n != spec.driver_name]
        # add fresh entries
        for capability in spec.supported_actions:
            self._capability_map.setdefault(capability, [])
            if spec.driver_name not in self._capability_map[capability]:
                self._capability_map[capability].append(spec.driver_name)

    def register(self, driver: DriverInterface, initial_status: DriverStatus = "testing"):
        spec = driver.describe()
        self._drivers[spec.driver_name] = driver
        self._driver_statuses[spec.driver_name] = initial_status
        self._map_capabilities(driver)
        print(f"[Registry] Registered {spec.driver_name} status={initial_status}")

    def update_driver_status(self, driver_name: str, new_status: DriverStatus):
        if driver_name not in self._drivers:
            # allow preset status for drivers loaded later
            self._driver_statuses[driver_name] = new_status
            print(f"[Registry] Preset status for '{driver_name}' → {new_status}")
            return
        self._driver_statuses[driver_name] = new_status
        print(f"[Registry] Updated status for '{driver_name}' → {new_status}")
        # enforce attestation when moving to live
        if new_status == "live":
            d = self._drivers[driver_name]
            if not verify_attestation(d.describe(), self._policy):
                self._driver_statuses[driver_name] = "testing"
                raise RuntimeError(f"Driver '{driver_name}' failed attestation; reverted to 'testing'")

    def load_and_register_driver(
        self,
        driver_name: str,
        module_path: str,
        class_name: str,
        initial_status: DriverStatus | None = None,
    ):
        try:
            spec = importlib.util.spec_from_file_location(driver_name, module_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot load spec from {module_path}")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore
            if not hasattr(mod, class_name):
                raise ImportError(f"{class_name} not found in {module_path}")
            cls = getattr(mod, class_name)
            driver: DriverInterface = cls()
            status = initial_status or self._driver_statuses.get(driver_name, "testing")
            self.register(driver, initial_status=status)
            if status == "live" and not verify_attestation(driver.describe(), self._policy):
                self._driver_statuses[driver_name] = "testing"
                raise RuntimeError(f"Loaded driver '{driver_name}' without valid attestation")
            print(f"[Registry] Loaded '{driver_name}' from '{module_path}' as '{class_name}'")
        except Exception as e:
            raise RuntimeError(f"load_and_register_driver failed for '{driver_name}': {e}")

    # ---------- Routing ----------

    def get_live_driver_for_capability(self, capability: str) -> DriverInterface | None:
        for name in self._capability_map.get(capability, []):
            if self._driver_statuses.get(name) == "live":
                return self._drivers.get(name)
        return None

    def get_shadow_drivers_for_capability(self, capability: str) -> list[DriverInterface]:
        out: list[DriverInterface] = []
        for name in self._capability_map.get(capability, []):
            if self._driver_statuses.get(name) == "shadow":
                d = self._drivers.get(name)
                if d:
                    out.append(d)
        return out

    def promote_shadow_to_live(self, capability: str, shadow_driver_name: str) -> None:
        # demote current live if any, then promote the named shadow
        live = self.get_live_driver_for_capability(capability)
        if live:
            live_name = live.describe().driver_name
            self.update_driver_status(live_name, "shadow")
        self.update_driver_status(shadow_driver_name, "live")

    def demote_live_to_shadow(self, capability: str) -> None:
        live = self.get_live_driver_for_capability(capability)
        if live:
            live_name = live.describe().driver_name
            self.update_driver_status(live_name, "shadow")