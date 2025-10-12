# systems/axon/mesh/attestation.py
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Dict, Optional

from systems.axon.mesh.sdk import CapabilitySpec


@dataclass
class AttestationPolicy:
    # Expand with signature/kms fields later
    require_binding_for_live: bool = True


class AttestationRegistry:
    """
    In-memory map of driver_name → {capability, artifact_hash}.
    """

    def __init__(self) -> None:
        self._bindings: dict[str, dict[str, str]] = {}

    def bind(self, *, driver_name: str, capability: str, artifact_hash: str) -> None:
        self._bindings[driver_name] = {"capability": capability, "artifact_hash": artifact_hash}

    def get(self, driver_name: str) -> dict[str, str] | None:
        return self._bindings.get(driver_name)


_REG = AttestationRegistry()


def _hash_file(path: str) -> str:
    h = hashlib.blake2b(digest_size=32)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_artifact_hash(artifact_path: str) -> str:
    """
    Computes a stable hash for the artifact file/module.
    """
    if not os.path.exists(artifact_path):
        raise FileNotFoundError(artifact_path)
    return _hash_file(artifact_path)


def bind_artifact_to_capability(*, driver_name: str, capability: str, artifact_hash: str) -> None:
    _REG.bind(driver_name=driver_name, capability=capability, artifact_hash=artifact_hash)


def verify_attestation(describe_obj: CapabilitySpec | dict, policy: AttestationPolicy) -> bool:
    """
    Verify that a driver has a binding. For now this checks presence & capability match.
    """
    if isinstance(describe_obj, dict):
        name = describe_obj.get("driver_name", "")
        cap = (describe_obj.get("supported_actions") or [None])[0]
    else:
        name = describe_obj.driver_name
        cap = (describe_obj.supported_actions or [None])[0]

    rec = _REG.get(name)
    if not rec:
        return not policy.require_binding_for_live  # allow if policy relaxed
    if cap and rec.get("capability") and cap != rec["capability"]:
        return False
    return True
