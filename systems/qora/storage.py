# systems/qora/storage.py
from __future__ import annotations

import json
import os
from pathlib import Path

ART = Path(os.getenv("SIMULA_ARTIFACTS_ROOT", ".simula")).resolve()
ART.mkdir(parents=True, exist_ok=True)


def load_json(name: str, default):
    p = ART / name
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(name: str, data):
    p = ART / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
