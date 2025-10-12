# core/security/soul_node_service.py
# Centralized service for SoulNode encryption/decryption with Fernet + AES-GCM interop.
from __future__ import annotations

import base64
import hmac
import json
import os
from typing import Any, Dict, Literal, Optional, Tuple

from cryptography.fernet import Fernet

try:
    # Optional: load .env if available (won't error if dotenv isn't installed)
    from dotenv import find_dotenv, load_dotenv  # type: ignore

    load_dotenv(r"D:\EcodiaOS\config\.env") or load_dotenv(find_dotenv())
except Exception:
    pass

# ---- AES-GCM helpers (optional path) ----
# These utilities SHOULD NOT import this module back, or you’ll reintroduce cycles.
try:
    from core.utils.crypto.secret import decrypt_soul as aesgcm_decrypt_soul
    from core.utils.crypto.secret import encrypt_soul as aesgcm_encrypt_soul

    _AES_AVAILABLE = True
except Exception:
    _AES_AVAILABLE = False

CipherMode = Literal["fernet", "aesgcm"]


# ---------------------------
# Fernet key loading/validation
# ---------------------------
def _load_fernet_key() -> bytes | None:
    key_str = (os.getenv("SOULNODE_ENCRYPTION_KEY") or "").strip()
    if not key_str:
        return None
    key_bytes = key_str.encode("utf-8")
    # Validate: constructing Fernet will raise ValueError if bad (not 32-byte urlsafe b64)
    Fernet(key_bytes)
    return key_bytes


_FERNET_KEY: bytes | None = None
_FERNET: Fernet | None = None

try:
    _FERNET_KEY = _load_fernet_key()
    if _FERNET_KEY:
        _FERNET = Fernet(_FERNET_KEY)
except ValueError as e:
    raise ValueError(
        "SOULNODE_ENCRYPTION_KEY is invalid. It must be 32 url-safe base64-encoded bytes "
        "(44 chars, usually ending with '='). Generate with:\n"
        "  from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())",
    ) from e

# ---------------------------
# Mode selection
# ---------------------------
_forced = (os.getenv("SOULNODE_CIPHER") or "").strip().lower()
if _forced and _forced not in ("fernet", "aesgcm"):
    raise ValueError("SOULNODE_CIPHER must be either 'fernet' or 'aesgcm' (or unset).")


def _default_mode() -> CipherMode:
    if _forced == "fernet":
        return "fernet"
    if _forced == "aesgcm":
        return "aesgcm"
    # Auto: prefer Fernet if key present; otherwise AES-GCM if available.
    if _FERNET is not None:
        return "fernet"
    if _AES_AVAILABLE:
        return "aesgcm"
    raise RuntimeError(
        "No usable cipher configured. Set SOULNODE_ENCRYPTION_KEY (Fernet) or ECODIA_PHRASE_KEY (AES-GCM).",
    )


# ---------------------------
# Format detectors
# ---------------------------
def _looks_like_fernet_wrapped(value: str) -> bool:
    """
    Legacy format: urlsafe_base64 wrapping a Fernet token.
    Heuristic: base64-decodes cleanly; true decrypt validates later.
    """
    try:
        base64.urlsafe_b64decode(value.encode("utf-8"))
        return True
    except Exception:
        return False


def _looks_like_aesgcm_json(value: str) -> bool:
    try:
        obj = json.loads(value)
        return isinstance(obj, dict) and obj.get("alg") == "AES-256-GCM"
    except Exception:
        return False


# ---------------------------
# Public API
# ---------------------------
def encrypt_soulnode(plaintext: str, aad: dict[str, Any] | None = None) -> str:
    """
    Encrypt for storage using the selected/default mode.
    - fernet: returns urlsafe_base64(fernet_token_bytes).decode()
    - aesgcm: returns compact JSON string: {"alg","kid","iv","ct","aad"}
    """
    mode = _default_mode()
    if mode == "fernet":
        if _FERNET is None:
            raise RuntimeError("Fernet selected but SOULNODE_ENCRYPTION_KEY is not set/valid.")
        token = _FERNET.encrypt(plaintext.encode("utf-8"))  # bytes (urlsafe b64 already)
        return base64.urlsafe_b64encode(token).decode("utf-8")
    # AES-GCM path
    if not _AES_AVAILABLE:
        raise RuntimeError("AES-GCM selected but AES utilities are unavailable.")
    obj = aesgcm_encrypt_soul(plaintext, aad=aad or {})
    return json.dumps(obj, separators=(",", ":"))


def decrypt_soulnode(stored_value: str) -> str:
    """
    Decrypt from storage. Auto-detects:
      - AES-GCM JSON (preferred if present)
      - Legacy Fernet double-base64
    """
    # Try AES-GCM first when it looks like JSON
    if _AES_AVAILABLE and _looks_like_aesgcm_json(stored_value):
        obj = json.loads(stored_value)
        return aesgcm_decrypt_soul(obj["iv"], obj["ct"], obj.get("aad", ""))

    # Otherwise try Fernet (legacy double-b64)
    if _FERNET is not None and _looks_like_fernet_wrapped(stored_value):
        inner = base64.urlsafe_b64decode(stored_value.encode("utf-8"))
        return _FERNET.decrypt(inner).decode("utf-8")

    # Last attempts based on availability (raise if wrong format)
    if _FERNET is not None:
        inner = base64.urlsafe_b64decode(stored_value.encode("utf-8"))
        return _FERNET.decrypt(inner).decode("utf-8")
    if _AES_AVAILABLE:
        obj = json.loads(stored_value)  # will raise if not JSON
        return aesgcm_decrypt_soul(obj["iv"], obj["ct"], obj.get("aad", ""))

    raise ValueError("Unable to determine cipher format for stored SoulNode.")


def verify_soulnode(user_input_soul: str, stored_encrypted_soul: str) -> bool:
    """Constant-time comparison after decrypt."""
    try:
        decrypted = decrypt_soulnode(stored_encrypted_soul)
        return hmac.compare_digest(user_input_soul.encode("utf-8"), decrypted.encode("utf-8"))
    except Exception:
        return False


def reencrypt_if_legacy(stored_value: str, aad: dict[str, Any] | None = None) -> tuple[str, bool]:
    """
    Re-encrypt to current default if format differs.
    Returns (new_value, changed?)
    """
    want = _default_mode()
    is_aes = _looks_like_aesgcm_json(stored_value)
    is_fer = _looks_like_fernet_wrapped(stored_value)
    if (want == "aesgcm" and is_aes) or (want == "fernet" and is_fer):
        return stored_value, False
    plain = decrypt_soulnode(stored_value)
    return encrypt_soulnode(plain, aad=aad), True
