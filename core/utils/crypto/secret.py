from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# add at top, near imports
from dotenv import find_dotenv, load_dotenv

# hard-prefer your local config path if you have one; otherwise autodetect
load_dotenv(r"D:\EcodiaOS\config\.env") or load_dotenv(find_dotenv())

ALG = "AES-256-GCM"
IV_LEN = 12  # 96-bit


def _key_bytes() -> bytes:
    b64 = (os.getenv("ECODIA_PHRASE_KEY") or "").strip()
    if not b64:
        raise RuntimeError("Missing ECODIA_PHRASE_KEY (base64 32 bytes).")
    try:
        key = base64.b64decode(b64, validate=True)
    except Exception as e:
        raise RuntimeError(f"ECODIA_PHRASE_KEY is not valid base64: {e}")
    if len(key) != 32:
        raise RuntimeError(f"ECODIA_PHRASE_KEY must decode to 32 bytes, got {len(key)}.")
    return key


def _key_id() -> str:
    return os.getenv("ECODIA_PHRASE_KEY_ID", "default")


def encrypt_soul(plaintext: str, aad: dict[str, Any] | None = None) -> dict[str, str]:
    aad_bytes = json.dumps(aad or {}, separators=(",", ":")).encode("utf-8")
    iv = os.urandom(IV_LEN)
    ct = AESGCM(_key_bytes()).encrypt(iv, plaintext.encode("utf-8"), aad_bytes)
    return {
        "alg": ALG,
        "kid": _key_id(),
        "iv": base64.b64encode(iv).decode("ascii"),
        "ct": base64.b64encode(ct).decode("ascii"),
        "aad": base64.b64encode(aad_bytes).decode("ascii"),
    }


def decrypt_soul(iv_b64: str, ct_b64: str, aad_b64: str) -> str:
    iv = base64.b64decode(iv_b64)
    ct = base64.b64decode(ct_b64)
    aad = base64.b64decode(aad_b64)
    pt = AESGCM(_key_bytes()).decrypt(iv, ct, aad)
    return pt.decode("utf-8")
