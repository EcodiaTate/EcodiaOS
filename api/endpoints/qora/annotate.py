from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

# Optional imports; we degrade gracefully if not present
try:
    from systems.qora.client import policy_check_diff, wm_search
except Exception:  # pragma: no cover
    policy_check_diff = None
    wm_search = None

annotate_router = APIRouter(tags=["qora-annotate"])

_DIFF_FILE_RE = re.compile(r"^\+\+\+ b/(.+)$", re.M)


class AnnotateRequest(BaseModel):
    diff: str = Field(..., description="unified diff text")
    q_per_file: int = Field(3, ge=0, le=10, description="WM search hits per changed file")


class AnnotateResponse(BaseModel):
    markdown: str
    summary: dict[str, Any] = Field(default_factory=dict)


def _changed_files(diff: str) -> list[str]:
    return sorted(set(_DIFF_FILE_RE.findall(diff or "")))


def _mk_title_line(files: list[str], ok_policy: bool | None) -> str:
    badge = "✅" if ok_policy else ("⚠️" if ok_policy is False else "ℹ️")
    return f"{badge} Simula/Qora analysis for {len(files)} changed file(s)"


def _mk_section(title: str) -> str:
    return f"\n### {title}\n"


def _mk_bullets(items: list[str]) -> str:
    return "".join([f"- {i}\n" for i in items])


@annotate_router.post("/diff", response_model=AnnotateResponse)
async def annotate_diff(req: AnnotateRequest) -> AnnotateResponse:
    diff = req.diff or ""
    files = _changed_files(diff)

    # 1) Policy gate
    pol = None
    if callable(policy_check_diff):
        try:
            pol = await policy_check_diff(diff)
        except Exception:
            pol = None

    # 2) WM hints per file
    hints: dict[str, list[str]] = {}
    if callable(wm_search) and req.q_per_file > 0:
        for f in files:
            try:
                # search by filename stem and last path component
                stem = f.rsplit("/", 1)[-1].split(".")[0]
                hits = await wm_search(q=stem, top_k=req.q_per_file)
                rows = hits.get("hits", []) if isinstance(hits, dict) else []
                hints[f] = [
                    f"`{h.get('symbol', '')}` @ L{h.get('line', 1)} — {h.get('path', '')}"
                    for h in rows
                ]
            except Exception:
                continue

    # 3) Build nice markdown
    md: list[str] = []
    md.append(f"## {_mk_title_line(files, pol.get('ok') if isinstance(pol, dict) else None)}\n")
    md.append(_mk_section("Changed files"))
    md.append(_mk_bullets([f"`{p}`" for p in files] or ["(none)"]))

    if isinstance(pol, dict):
        md.append(_mk_section("Policy"))
        if pol.get("ok", False):
            md.append("- **OK** — no violations found.\n")
        else:
            md.append("- **Issues detected** — please review summary below.\n")
        if "summary" in pol:
            md.append("```json\n")
            # keep compact, avoid 1000s of lines
            import json

            md.append(json.dumps(pol["summary"], indent=2)[:3000])
            md.append("\n```\n")

    if hints:
        md.append(_mk_section("Related symbols (quick WM hints)"))
        for f, rows in hints.items():
            md.append(f"- **{f}**\n")
            for r in rows:
                md.append(f"  - {r}\n")

    return AnnotateResponse(
        markdown="".join(md),
        summary={"files": files, "policy_ok": (pol.get("ok") if isinstance(pol, dict) else None)},
    )
