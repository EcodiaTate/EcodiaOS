from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

wm_search_router = APIRouter()

# Light WM indexer (graceful fallback)
try:
    from systems.qora.wm.indexer import _index, bootstrap_index  # type: ignore
except Exception:  # pragma: no cover
    bootstrap_index = None
    _index = None


class SearchRequest(BaseModel):
    q: str = Field(..., min_length=2)
    top_k: int = Field(25, ge=1, le=200)


class SearchHit(BaseModel):
    path: str
    line: int
    kind: str
    symbol: str
    score: float
    snippet: str


class SearchResponse(BaseModel):
    hits: list[SearchHit] = Field(default_factory=list)


def _read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _score(q: str, text: str, name: str, file_path: str) -> tuple[float, int]:
    tf = len(re.findall(re.escape(q), text, flags=re.IGNORECASE))
    name_hits = 1 if re.search(re.escape(q), name, re.IGNORECASE) else 0
    file_hits = 1 if re.search(re.escape(q), Path(file_path).name, re.IGNORECASE) else 0
    return (3.0 * name_hits) + (2.0 * file_hits) + (1.0 * tf), tf


def _first_line(text: str, q: str) -> int:
    try:
        m = re.search(re.escape(q), text, flags=re.IGNORECASE)
        if not m:
            return 1
        return text.count("\n", 0, m.start()) + 1
    except Exception:
        return 1


def _snippet(text: str, q: str, around: int = 2) -> str:
    lines = text.splitlines()
    try:
        m = re.search(re.escape(q), text, flags=re.IGNORECASE)
        if not m:
            return "\n".join(lines[: min(len(lines), 5)])
        ln = text.count("\n", 0, m.start()) + 1
        lo = max(1, ln - around) - 1
        hi = min(len(lines), ln + around)
        return "\n".join(lines[lo:hi])
    except Exception:
        return "\n".join(lines[: min(len(lines), 5)])


@wm_search_router.post("/search", response_model=SearchResponse)
async def wm_search(req: SearchRequest) -> SearchResponse:
    if _index is None:
        raise HTTPException(status_code=501, detail="WM index not available")
    try:
        idx = _index()
        if not idx and callable(bootstrap_index):
            bootstrap_index(None)
            idx = _index()
        nodes: dict[str, dict[str, Any]] = idx.get("nodes", {})
        hits: list[SearchHit] = []
        q = req.q.strip()
        for fq, meta in nodes.items():
            file_path = meta.get("file") or ""
            if not file_path:
                continue
            text = _read_text(file_path)
            sc, _ = _score(q, text, name=fq.split("::")[-1], file_path=file_path)
            if sc <= 0:
                continue
            line = _first_line(text, q)
            hits.append(
                SearchHit(
                    path=file_path,
                    line=line,
                    kind=meta.get("kind", "symbol"),
                    symbol=fq,
                    score=float(sc),
                    snippet=_snippet(text, q),
                ),
            )
        hits.sort(key=lambda h: h.score, reverse=True)
        return SearchResponse(hits=hits[: req.top_k])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"wm_search failed: {e!r}")
