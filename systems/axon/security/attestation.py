# systems/axon/security/attestation.py
from __future__ import annotations

import os
from typing import Any

# highlight-start
from systems.axon.dependencies import get_lifecycle_manager
# highlight-end
from systems.axon.mesh.attestation import AttestationPolicy, verify_attestation


class AttestationManager:
    """
    Thin facade for future KMS-backed bindings.
    For now, we rely on mesh.attestation.verify_attestation(describe()) semantics.
    """

    def __init__(self, policy: AttestationPolicy | None = None) -> None:
        self._policy = policy or AttestationPolicy()

    def is_bound(self, driver_name: str) -> bool:
        """
        Checks if a driver has a valid attestation binding according to policy.
        """
# highlight-start
        # In a fuller implementation, this would check KMS signatures bound to artifact hashes.
        # For now, honor a dev override: AXON_ATTEST_BYPASS=1
        if os.getenv("AXON_ATTEST_BYPASS", "0") == "1":
            return True
        
        # This facade now correctly calls the real verification logic.
        try:
            lifecycle = get_lifecycle_manager()
            state = lifecycle.get_driver_state(driver_name)
            if not state or not state.spec:
                return False
            return verify_attestation(state.spec, self._policy)
        except Exception:
            return False
# highlight-end


def verify_driver_attestation(describe_obj: Any) -> bool:
    """
    Convenience wrapper for modules that import from security.attestation.
    """
    return verify_attestation(describe_obj, AttestationPolicy())