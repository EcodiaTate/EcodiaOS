from __future__ import annotations

import json
from pathlib import Path

from systems.simula.config import settings

_BASE = Path(settings.artifacts_root) / "qora" / "policy_packs"
_BASE.mkdir(parents=True, exist_ok=True)


def list_packs() -> list[str]:
    return sorted([p.stem for p in _BASE.glob("*.json")])


def write_pack(name: str, files: list[dict[str, str]]) -> None:
    # files: [{"path":"policies/foo.rego", "content":"..."}]
    payload = {"files": files}
    (_BASE / f"{name}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_pack(name: str) -> dict:
    p = _BASE / f"{name}.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))
