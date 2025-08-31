from __future__ import annotations

from typing import Any

from .model import SIMIR, FuncDecl


async def plan_patch_from_constraints(constraints: dict[str, Any]) -> dict[str, Any]:
    # Placeholder planner; upgrade with LLM + dossier-guided planning.
    targets = constraints.get("targets") or ["app/core.py"]
    patch = {"modules": {}}
    for t in targets:
        patch["modules"][t] = {
            "funcs": [
                {
                    "fqname": f"{t}::main",
                    "params": {},
                    "returns": "int",
                    "contracts": {"post": "result >= 0"},
                },
            ],
        }
    return patch


def apply_ir_patch(ir: SIMIR, patch: dict[str, Any]) -> SIMIR:
    for path, m in (patch.get("modules") or {}).items():
        mod = ir.ensure_module(path)
        for f in m.get("funcs", []):
            fd = FuncDecl(**f)
            mod.funcs = [x for x in mod.funcs if x.fqname != fd.fqname] + [fd]
    return ir
