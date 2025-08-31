from __future__ import annotations

import os

from fastapi import Header, HTTPException


def require_qora_key(x_qora_key: str = Header(default=None, alias="X-Qora-Key")) -> str:
    expected = os.getenv("QORA_API_KEY", "")
    if not expected:
        # If no key is configured, allow but warn (dev mode)
        return x_qora_key or ""
    if not x_qora_key or x_qora_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Qora-Key")
    return x_qora_key
