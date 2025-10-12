# systems/axon/dependencies.py
from __future__ import annotations

import threading
from typing import Optional

from systems.axon.io.quarantine import Quarantine
from systems.axon.journal.mej import MerkleJournal
from systems.axon.mesh.lifecycle import DriverLifecycleManager
from systems.axon.mesh.registry import DriverRegistry
from systems.axon.mesh.scorecard import ScorecardManager
from systems.axon.safety.circuit_breaker import CircuitBreaker
from systems.axon.safety.conformal import ConformalPredictor
from systems.axon.safety.contracts import ContractsEngine

# --- Globals for Singleton Management ---
_REGISTRY: DriverRegistry | None = None
_LOCK = threading.Lock()

# --- Singleton Getters ---


def get_driver_registry() -> DriverRegistry:
    """
    Returns a pre-populated, thread-safe singleton DriverRegistry with all supported drivers.
    Each registration is best-effort and will fail silently if import errors occur.
    """
    global _REGISTRY
    # Fast path: if the registry is already initialized, return it immediately.
    if _REGISTRY is not None:
        return _REGISTRY

    # Slow path: acquire a lock to ensure only one thread initializes the registry.
    with _LOCK:
        # Double-check in case another thread initialized it while we were waiting for the lock.
        if _REGISTRY is not None:
            return _REGISTRY

        reg = DriverRegistry()

        # --- Driver Registration ---

        # Google Programmable Search
        try:
            from systems.axon.drivers.google_pse import GooglePse

            reg.register("google_pse", GooglePse(), status="stable")
        except Exception as e:
            print(f"[DriverRegistry] Skipped registering 'google_pse': {e}")

        # OpenMeteo Weather
        try:
            from systems.axon.drivers.open_meteo import OpenMeteo

            reg.register("open_meteo", OpenMeteo(), status="stable")
        except Exception as e:
            print(f"[DriverRegistry] Skipped registering 'open_meteo': {e}")

        # Qora (Internal Knowledge Search)
        try:
            from systems.axon.drivers.qora_search import QoraSearch

            reg.register("qora", QoraSearch(), status="stable")
        except Exception as e:
            print(f"[DriverRegistry] Skipped registering 'qora': {e}")

        # Nager.Date (Public Holidays)
        try:
            from systems.axon.drivers.nager_date import NagerDate

            reg.register("nager", NagerDate(), status="stable")
        except Exception as e:
            print(f"[DriverRegistry] Skipped registering 'nager': {e}")

        # Generic RSS Driver
        try:
            from systems.axon.drivers.quickrss import RSSDriver

            reg.register("rssdriver", RSSDriver(), status="stable")
        except Exception as e:
            print(f"[DriverRegistry] Skipped registering 'rssdriver': {e}")

        # Nominatim (Geocoding)
        try:
            from systems.axon.drivers.nominatim import Nominatim

            reg.register("nominatim", Nominatim(), status="stable")
        except Exception as e:
            print(f"[DriverRegistry] Skipped registering 'nominatim': {e}")

        # FXRates (Currency Exchange)
        try:
            from systems.axon.drivers.fxrates import FXRates

            reg.register("fxrates", FXRates(), status="stable")
        except Exception as e:
            print(f"[DriverRegistry] Skipped registering 'fxrates': {e}")

        # NEW: MemoryDriver (Semantic Search)
        try:
            from systems.axon.drivers.user_memory import MemoryDriver

            reg.register("memory", MemoryDriver(), status="stable")
        except Exception as e:
            print(f"[DriverRegistry] Skipped registering 'memory': {e}")

        print("[Axon] Drivers ready.")
        _REGISTRY = reg
        return reg


def get_scorecard_manager() -> ScorecardManager:
    """Returns the singleton ScorecardManager used for Axon metrics."""
    return ScorecardManager(window_max=500)


def get_lifecycle_manager() -> DriverLifecycleManager:
    """Returns the lifecycle manager responsible for driver promotion and demotion."""
    return DriverLifecycleManager(artifact_dir="systems/axon/drivers/generated")


def get_conformal_predictor() -> ConformalPredictor:
    """Returns a conformal predictor for confidence calibration."""
    return ConformalPredictor(max_residuals=512, q=0.9)


def get_circuit_breaker() -> CircuitBreaker:
    """Returns a circuit breaker for driver-level fault tolerance."""
    return CircuitBreaker(
        window_sec=60,
        min_success=0.85,
        burst_fail_cap=5,
        cooldown_sec=30,
    )


def get_contracts_engine() -> ContractsEngine:
    """Returns the canonical contracts engine enforcing data safety."""
    return ContractsEngine().with_default_rules()


def get_journal() -> MerkleJournal:
    """Returns the Merkle-based journaling system for driver operations."""
    return MerkleJournal()


def get_quarantine() -> Quarantine:
    """Returns the quarantine subsystem for isolating failed driver calls."""
    return Quarantine()
