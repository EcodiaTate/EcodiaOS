from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class UES(BaseModel):
    id: str  # stable content hash or source id
    ts: datetime  # when this happened (best-effort)
    seen_at: datetime  # when we ingested it
    source: str  # e.g., "rss:abc-top", "json:events-api"
    kind: str  # rss.article, news.item, calendar.event, iot.reading, etc.
    subject: str | None = None  # title/summary/headline
    text: str | None = None  # readable text body (sanitized)
    html: str | None = None
    link: str | None = None  # canonical URL if known
    location: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)  # structured residue
    pii_flags: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)  # registry id, fetcher, taints, etc.
