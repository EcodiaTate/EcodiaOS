# systems/axon/dependencies.py
from __future__ import annotations

from functools import cache

from systems.axon.mesh.registry import DriverRegistry
from systems.axon.mesh.scorecard import ScorecardManager
from systems.axon.mesh.lifecycle import DriverLifecycleManager
from systems.axon.safety.conformal import ConformalPredictor
from systems.axon.safety.circuit_breaker import CircuitBreaker
from systems.axon.safety.contracts import ContractsEngine
from systems.axon.journal.mej import MerkleJournal
from systems.axon.io.quarantine import Quarantine


@cache
def get_driver_registry() -> DriverRegistry:
    return DriverRegistry()

@cache
def get_scorecard_manager() -> ScorecardManager:
    return ScorecardManager(window_max=500)

@cache
def get_lifecycle_manager() -> DriverLifecycleManager:
    # Use canonical artifact dir so synthesis/promotions are consistent
    return DriverLifecycleManager(artifact_dir="systems/axon/drivers/generated")

@cache
def get_conformal_predictor() -> ConformalPredictor:
    return ConformalPredictor(max_residuals=512, q=0.9)

@cache
def get_circuit_breaker() -> CircuitBreaker:
    return CircuitBreaker(window_sec=60, min_success=0.85, burst_fail_cap=5, cooldown_sec=30)

@cache
def get_contracts_engine() -> ContractsEngine:
    return ContractsEngine().with_default_rules()

@cache
def get_journal() -> MerkleJournal:
    return MerkleJournal()

@cache
def get_quarantine() -> Quarantine:
    return Quarantine()
