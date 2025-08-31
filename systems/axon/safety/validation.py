# systems/axon/safety/validation.py
from __future__ import annotations

import hashlib
import hmac
import time as pytime
from typing import Any

from pydantic import BaseModel

from systems.axon.mesh.registry import DriverRegistry
from systems.equor.kms.keystore import get_hmac_key_by_kid


class Predicate(BaseModel):
    variable: str
    operator: str
    value: Any


class CapabilityValidator:
    """
    Validates Equor capability tokens minted upstream.
    Enforces TTL (nbf/exp), issuer/audience, capability/driver binding, and KMS key rotation via `kid`.
    """

    def validate(self, intent, driver_registry: DriverRegistry | None = None) -> bool:
        token: dict[str, Any] | None = (intent.policy_trace or {}).get("equor_cap_token")
        if not token:
            return False

        # Required fields
        intent_id = token.get("intent_id")
        sig = token.get("signature")
        preds = token.get("predicates", [])
        nbf, exp = int(token.get("nbf", 0)), int(token.get("exp", 2**31))
        iss, aud = token.get("iss", ""), token.get("aud", "")
        cap = token.get("capability")
        version = str(token.get("version", ""))
        artifact_hash = token.get("artifact_hash")  # optional
        kid = token.get("kid", "k1")

        # Basic checks
        now = int(pytime.time())
        if now < nbf or now > exp:
            return False
        if iss != "equor" or aud not in ("axon", "atune", "unity"):
            return False
        if not intent_id or not sig or not cap:
            return False
        if intent.target_capability != cap:
            return False

        # KMS key lookup
        key = get_hmac_key_by_kid(kid)
        if not key:
            return False

        # Signature over canonical message: intent_id + sorted predicates (by string)
        message = intent_id.encode("utf-8") + str(sorted(preds, key=str)).encode("utf-8")
        expected = hmac.new(key, message, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return False

        # Bind to current live driver artifact/version (best-effort)
        if driver_registry:
            live = driver_registry.get_live_driver_for_capability(cap)
            if live and hasattr(live, "describe"):
                desc = live.describe()
                live_hash = getattr(desc, "artifact_hash", None)
                live_version = getattr(desc, "version", None)
                if artifact_hash and live_hash and artifact_hash != live_hash:
                    return False
                if version and live_version and str(version) != str(live_version):
                    return False

        return True
