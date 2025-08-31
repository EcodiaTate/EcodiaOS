from __future__ import annotations

"""
Contra manifest engine — LIVE overlay–aware checks (async).

This module consumes a built SystemManifest and validates it against the
live endpoint registry exposed by `api/meta/endpoints`.

Diagnostics produced here are intentionally *deterministic* and *actionable*:
- alias_parity ............: fail if any ENDPOINTS.<ALIAS> has no live mapping
- path_resolution .........: fail if any call-site resolves to null/empty path
- illegal_self_edge .......: fail if a system calls itself via HTTP (SoC breach)
- header_discipline .......: warn if HTTP call-sites don't propagate EOS headers
- schema_presence .........: warn if live registry exposes an alias without req/resp schemas

All checks are cheap and file-local; deeper AST diffs (model drift, tool args)
can be layered on top without changing this API.

Public:
    run_checks(manifest: SystemManifest) -> List[Diagnostic]   # async
    run_checks_sync(manifest: SystemManifest) -> List[Diagnostic]  # sync wrapper
"""

import asyncio
from typing import Any

from pydantic import BaseModel

from systems.qora.manifest.models import SystemManifest
from systems.qora.manifest.registry_client import (
    get_endpoint_aliases,
    get_endpoint_routes,
)

# --------------------------- Diagnostic model ---------------------------


class Diagnostic(BaseModel):
    assertion_id: str  # stable id
    status: str  # "pass" | "fail" | "warn"
    evidence: list[dict[str, Any]] = []  # concrete rows (file, line, alias, etc)
    suggested_fixes: list[dict[str, Any]] = []
    confidence: float = 1.0


# ------------------------------ Utilities ------------------------------


def _file_has_headers(path: str) -> bool:
    """Heuristic: does a file show header propagation usage or helper? (fast substring scan)"""
    try:
        txt = open(path, encoding="utf-8").read()
    except Exception:
        return False
    low = txt.lower()
    if "x-decision-id" in low or "x-budget-ms" in low:
        return True
    if "attach_eos_headers" in low:
        return True
    return False


# ------------------------------ Assertions -----------------------------


async def _alias_parity(m: SystemManifest) -> Diagnostic:
    """All used aliases must exist in the live overlay."""
    aliases = await get_endpoint_aliases()
    missing = [r for r in m.endpoints_used if r["alias"] not in aliases]
    if missing:
        return Diagnostic(
            assertion_id="alias_parity",
            status="fail",
            evidence=missing[:500],  # cap evidence
            suggested_fixes=[
                {
                    "action": "refresh_overlay_or_add_aliases",
                    "aliases": sorted({r["alias"] for r in missing}),
                    "hint": "Aliases must be emitted by api/meta/endpoints (canonical or synonyms).",
                },
            ],
            confidence=0.98,
        )
    return Diagnostic(assertion_id="alias_parity", status="pass")


async def _path_resolution(m: SystemManifest) -> Diagnostic:
    """
    Even if an alias exists, every call-site in the manifest should carry a resolvable path.
    Fail rows where path is None/empty (typical when the builder couldn't resolve).
    """
    unresolved = [r for r in m.endpoints_used if not r.get("path")]
    if unresolved:
        return Diagnostic(
            assertion_id="path_resolution",
            status="fail",
            evidence=unresolved[:500],
            suggested_fixes=[
                {
                    "action": "ensure_overlay_paths",
                    "aliases": sorted({r["alias"] for r in unresolved}),
                    "hint": "Verify api/meta/endpoints returns path for each alias.",
                },
            ],
            confidence=0.95,
        )
    return Diagnostic(assertion_id="path_resolution", status="pass")


async def _illegal_self_edge(m: SystemManifest) -> Diagnostic:
    """
    A system must not call its own HTTP endpoints. Use in-proc function/adapters instead.
    """
    sys_lower = m.system.lower()
    offenders = []
    for row in m.endpoints_used:
        p = (row.get("path") or "").lower()
        if f"/{sys_lower}/" in p:
            offenders.append(row)
    if offenders:
        return Diagnostic(
            assertion_id="illegal_self_edge",
            status="fail",
            evidence=offenders[:500],
            suggested_fixes=[
                {
                    "action": "swap_http_to_inproc",
                    "targets": sorted({r["file"] for r in offenders}),
                    "hint": "Generate an adapter in the caller and replace ENDPOINTS.<ALIAS> with a direct import.",
                },
            ],
            confidence=0.97,
        )
    return Diagnostic(assertion_id="illegal_self_edge", status="pass")


async def _header_discipline(m: SystemManifest) -> Diagnostic:
    """
    Warn when files issuing HTTP calls lack EOS header propagation.
    We only look at 'from' files in edges.http, and scan for header hints or helper usage.
    """
    http_edges = m.edges.get("http") or []
    if not http_edges:
        return Diagnostic(assertion_id="header_discipline", status="pass")

    callers = sorted({e["from"] for e in http_edges if "from" in e})
    missing = [f for f in callers if not _file_has_headers(f)]
    if missing:
        return Diagnostic(
            assertion_id="header_discipline",
            status="warn",
            evidence=[{"file": f} for f in missing[:500]],
            suggested_fixes=[
                {
                    "action": "inject_header_helper",
                    "helper": "attach_eos_headers(headers, decision_id, budget_ms)",
                    "files": missing[:100],
                    "hint": "Set request headers x-decision-id/x-budget-ms; stamp X-Cost-MS in responses.",
                },
            ],
            confidence=0.8,
        )
    return Diagnostic(assertion_id="header_discipline", status="pass")


async def _schema_presence(m: SystemManifest) -> Diagnostic:
    """
    If the live registry exposes schema info, warn when it's missing for aliases used.
    This pushes the platform to publish machine-checkable contracts.
    """
    routes = await get_endpoint_routes()
    used = sorted({r["alias"] for r in m.endpoints_used})
    lacking = []
    for alias in used:
        r = routes.get(alias) or {}
        if r and (not r.get("req_schema") or not r.get("res_schema")):
            lacking.append(
                {
                    "alias": alias,
                    "path": r.get("path"),
                    "has_req": bool(r.get("req_schema")),
                    "has_res": bool(r.get("res_schema")),
                },
            )
    if lacking:
        return Diagnostic(
            assertion_id="schema_presence",
            status="warn",
            evidence=lacking[:500],
            suggested_fixes=[
                {
                    "action": "publish_schemas_in_meta",
                    "aliases": [x["alias"] for x in lacking],
                    "hint": "Augment api/meta/endpoints with req_schema/res_schema for these aliases.",
                },
            ],
            confidence=0.85,
        )
    return Diagnostic(assertion_id="schema_presence", status="pass")


# ------------------------------- Runner -------------------------------


async def run_checks(manifest: SystemManifest) -> list[Diagnostic]:
    """
    Execute all overlay-aware checks for a given manifest.
    """
    checks = [
        _alias_parity,
        _path_resolution,
        _illegal_self_edge,
        _header_discipline,
        _schema_presence,
    ]
    results: list[Diagnostic] = []
    for check in checks:
        try:
            results.append(await check(manifest))
        except Exception as e:  # pragma: no cover
            results.append(
                Diagnostic(
                    assertion_id=f"{check.__name__}",
                    status="warn",
                    evidence=[{"error": repr(e)}],
                    suggested_fixes=[],
                    confidence=0.2,
                ),
            )
    return results


def run_checks_sync(manifest: SystemManifest) -> list[Diagnostic]:
    """
    Sync convenience wrapper (useful in startup hooks or tests).
    """
    return asyncio.run(run_checks(manifest))


__all__ = ["Diagnostic", "run_checks", "run_checks_sync"]
