# systems/equor/kms/keystore.py
from __future__ import annotations

import base64
import json
import os

_KEYS_CACHE: dict[str, bytes] | None = None


def _load_keys() -> dict[str, bytes]:
    global _KEYS_CACHE
    if _KEYS_CACHE is not None:
        return _KEYS_CACHE

    # Preferred: EQUOR_KMS_KEYS='{"k1":"base64secret==","k2":"..."}'
    env = os.getenv("EQUOR_KMS_KEYS", "")
    keys: dict[str, bytes] = {}
    if env:
        try:
            parsed = json.loads(env)
            for kid, b64 in parsed.items():
                keys[kid] = base64.b64decode(b64)
        except Exception:
            keys = {}

    # Fallback: EQUOR_KMS_K1 (raw, not base64) or dev default
    if not keys:
        keys["k1"] = os.getenv("EQUOR_KMS_K1", "dev-default-secret").encode("utf-8")

    _KEYS_CACHE = keys
    return keys


def get_hmac_key_by_kid(kid: str) -> bytes | None:
    return _load_keys().get(kid)


def list_kids() -> list[str]:
    return list(_load_keys().keys())


def get_active_kid() -> str:
    return os.getenv("EQUOR_KMS_ACTIVE_KID", "k1")
