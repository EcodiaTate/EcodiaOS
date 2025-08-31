from __future__ import annotations

from systems.qora.manifest.models import SystemManifest

from .assertions import (
    CheckContext,
    check_alias_parity,
    check_header_discipline,
    check_illegal_self_edge,
    check_pydantic_drift,
    check_tool_required_args,
)
from .models import Diagnostic


async def run_checks(manifest: SystemManifest) -> list[Diagnostic]:
    ctx = CheckContext(manifest)
    checks = [
        check_alias_parity,
        check_header_discipline,
        check_tool_required_args,
        check_pydantic_drift,
        check_illegal_self_edge,
    ]
    out: list[Diagnostic] = []
    for c in checks:
        out.append(c(ctx))
    return out
