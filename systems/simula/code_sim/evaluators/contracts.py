# simula/code_sim/evaluators/contracts.py
"""
Contracts evaluator: exports present, registry updated, docs touched.

Objective keys used
-------------------
objective.acceptance.contracts.must_export: ["path.py::func(a:int)->R", ...]
objective.acceptance.contracts.must_register: ["registry: contains tool 'NAME'", ...]
objective.acceptance.docs.files_must_change: ["docs/...", ...]

Public API
----------
run(step, sandbox_session) -> dict
    {
      "exports_ok": bool,
      "registry_ok": bool,
      "docs_ok": bool,
      "details": {"exports": [...], "registry": [...], "docs_required": [...]}
    }
"""

from __future__ import annotations

import re
from pathlib import Path


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _approx_sig_present(src: str, func_sig: str) -> bool:
    # Compare by name + arg count (ignore types/whitespace)
    head = func_sig.strip()
    name = head.split("(", 1)[0].strip()
    try:
        params = head.split("(", 1)[1].rsplit(")", 1)[0]
    except Exception:
        return False
    param_names = [p.split(":")[0].split("=")[0].strip() for p in params.split(",") if p.strip()]
    pat = re.compile(rf"def\s+{re.escape(name)}\s*\((.*?)\)\s*:", re.DOTALL)
    for m in pat.finditer(src):
        got = [a.split("=")[0].split(":")[0].strip() for a in m.group(1).split(",") if a.strip()]
        if len(got) == len(param_names):
            return True
    return False


def _contains_tool_registration(src: str, tool_name: str) -> bool:
    return bool(re.search(rf"(register|add)_tool\([^)]*{re.escape(tool_name)}[^)]*\)", src))


def _git_changed(sess) -> list[str]:
    rc, out = sess.run(["git", "diff", "--name-only"], timeout=300)
    return out.strip().splitlines() if rc == 0 else []


def run(objective: dict, sandbox_session) -> dict[str, object]:
    """
    FIX: Changed function signature from 'step' to 'objective' to match the caller.
    """
    acc = objective.get("acceptance", {})
    exports = acc.get("contracts", {}).get("must_export", []) or []
    registers = acc.get("contracts", {}).get("must_register", []) or []
    docs_required = acc.get("docs", {}).get("files_must_change", []) or []

    exports_ok = True
    export_details: list[str] = []
    for spec in exports:
        try:
            file_part, sig = spec.split("::", 1)
        except ValueError:
            exports_ok = False
            export_details.append(f"BAD_SPEC {spec!r}")
            continue
        # This path resolution might need adjustment if sandbox root differs from repo root
        src = _read(Path(file_part))
        present = _approx_sig_present(src, sig)
        export_details.append(f"{'OK' if present else 'MISS'} {file_part} :: {sig}")
        exports_ok &= present

    registry_ok = True
    registry_details: list[str] = []
    for item in registers:
        m = re.search(r"tool\s+'([^']+)'", item)
        if not m:
            registry_ok = False
            registry_details.append(f"BAD_SPEC {item!r}")
            continue
        tool = m.group(1)
        reg_path = Path("systems/synk/core/tools/registry.py")
        src = _read(reg_path)
        ok = _contains_tool_registration(src, tool) or (tool in src)
        registry_details.append(f"{'OK' if ok else 'MISS'} registry contains {tool}")
        registry_ok &= ok

    docs_ok = True
    if docs_required:
        changed = set(_git_changed(sandbox_session))
        need = set(docs_required)
        docs_ok = need.issubset(changed)

    return {
        "exports_ok": exports_ok,
        "registry_ok": registry_ok,
        "docs_ok": docs_ok,
        "details": {
            "exports": export_details,
            "registry": registry_details,
            "docs_required": docs_required,
        },
    }
