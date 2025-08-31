from __future__ import annotations

import json
from hashlib import blake2s
from typing import Any


class ReplayCapsuleManager:
    """
    Minimal in-memory registry for replay capsules to support /evo/replay/*.
    """

    def __init__(self) -> None:
        self._capsules: dict[str, dict[str, Any]] = {}

    def add(self, capsule: dict[str, Any]) -> None:
        self._capsules[capsule["capsule_id"]] = capsule

    def manifest(self, capsule_id: str) -> dict[str, Any]:
        return dict(self._capsules.get(capsule_id, {}))

    def verify(self, capsule_id: str) -> bool:
        cap = self._capsules.get(capsule_id)
        if not cap:
            return False
        barcode = cap.get("barcode")
        body = {k: v for k, v in cap.items() if k != "barcode"}
        calc = blake2s(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        ).hexdigest()
        return calc == barcode
