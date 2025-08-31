# systems/simula/recipes/generator.py
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Recipe:
    id: str
    goal: str
    context_fqname: str
    impact_hint: str
    steps: list[str]
    success: bool
    created_at: float


_CATALOG = Path(".simula/recipes.json")


def load_catalog() -> list[Recipe]:
    if not _CATALOG.exists():
        return []
    try:
        raw = json.loads(_CATALOG.read_text(encoding="utf-8"))
        return [Recipe(**r) for r in raw]
    except Exception:
        return []


def save_catalog(items: list[Recipe]) -> None:
    _CATALOG.parent.mkdir(parents=True, exist_ok=True)
    _CATALOG.write_text(json.dumps([asdict(r) for r in items], indent=2), encoding="utf-8")


def append_recipe(
    goal: str,
    context_fqname: str,
    steps: list[str],
    success: bool,
    impact_hint: str = "",
) -> Recipe:
    rs = load_catalog()
    r = Recipe(
        id=f"rx-{int(time.time())}",
        goal=goal,
        context_fqname=context_fqname,
        impact_hint=impact_hint,
        steps=steps,
        success=success,
        created_at=time.time(),
    )
    rs.append(r)
    save_catalog(rs)
    return r
