from __future__ import annotations

from systems.qora.manifest.models import SystemManifest

from .models import Diagnostic

# Overlay alias snapshot
try:
    from core.utils.net_api import ENDPOINTS  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    ENDPOINTS = None


class CheckContext:
    def __init__(self, manifest: SystemManifest):
        self.m = manifest
        try:
            self.aliases: dict[str, str] = ENDPOINTS.endpoints_snapshot()  # type: ignore[attr-defined]
        except Exception:
            # fallback: pretend empty (forces alias parity failures to surface)
            self.aliases = {}


def check_alias_parity(ctx: CheckContext) -> Diagnostic:
    missing = []
    for row in ctx.m.endpoints_used:
        if row["alias"] not in ctx.aliases:
            missing.append(row)
    if missing:
        return Diagnostic(
            assertion_id="alias_parity",
            status="fail",
            evidence=missing,
            suggested_fixes=[{"action": "add_alias", "aliases": [x["alias"] for x in missing]}],
        )
    return Diagnostic(assertion_id="alias_parity", status="pass")


def check_header_discipline(ctx: CheckContext) -> Diagnostic:
    # If any HTTP edges exist, insist headers are propagated; suggest middleware if not obvious
    has_http = bool(ctx.m.edges.get("http"))
    if not has_http and ctx.m.endpoints_used:
        has_http = True
    if has_http:
        return Diagnostic(
            assertion_id="header_discipline",
            status="warn",
            evidence=[
                {"hint": "Ensure x-decision-id/x-budget-ms propagate; responses stamp X-Cost-MS."},
            ],
            suggested_fixes=[
                {"action": "ensure_header_middleware", "headers": ["x-decision-id", "x-budget-ms"]},
                {"action": "ensure_response_header", "headers": ["X-Cost-MS"]},
            ],
        )
    return Diagnostic(assertion_id="header_discipline", status="pass")


def check_tool_required_args(ctx: CheckContext) -> Diagnostic:
    # Placeholder: wire to Qora catalog schemas, diff against call-sites by AST
    return Diagnostic(
        assertion_id="tool_required_args",
        status="warn",
        evidence=[
            {"hint": "Cross-check @eos_tool required args against call-sites via Qora catalog."},
        ],
    )


def check_pydantic_drift(ctx: CheckContext) -> Diagnostic:
    # Placeholder: diff client models vs server handler annotations
    return Diagnostic(
        assertion_id="pydantic_drift",
        status="warn",
        evidence=[
            {"hint": "Compare client request/response models vs server handler annotations."},
        ],
    )


def check_illegal_self_edge(ctx: CheckContext) -> Diagnostic:
    offenders = []
    sys_lower = ctx.m.system.lower()
    for row in ctx.m.endpoints_used:
        path = (row.get("path") or "").lower()
        if f"/{sys_lower}/" in path:
            offenders.append(row)
    if offenders:
        return Diagnostic(
            assertion_id="illegal_self_edge",
            status="fail",
            evidence=offenders,
            suggested_fixes=[
                {"action": "swap_http_to_inproc", "targets": [x["file"] for x in offenders]},
            ],
        )
    return Diagnostic(assertion_id="illegal_self_edge", status="pass")
