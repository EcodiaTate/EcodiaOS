# systems/axon/registry/feeds.py
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Dict, List, Optional

from core.utils.net_api import get_http_client

# Reuse your existing infra
from systems.axon.drivers.rss_driver import RssDriver
from systems.axon.ingest.normalizers import build_event
from systems.axon.registry.loader import RegistryManager, SourceCfg
from systems.axon.schemas import AxonEvent


class SourceRegistryIngestor:
    """
    Pulls from registry-defined sources and yields AxonEvent objects,
    using Quarantine-backed normalizers under the hood.
    """

    def __init__(self, *registry_paths: str):
        self.reg = RegistryManager(*registry_paths)

    async def refresh(self) -> None:
        self.reg.refresh_if_changed()

    # ------------------- RSS -------------------
    async def _iter_rss(self, s: SourceCfg) -> AsyncIterator[AxonEvent]:
        driver = RssDriver()
        params = {"urls": [s.url], "max_items_per_feed": 50}
        async for ev in driver.pull(params):
            # ev is already an AxonEvent produced by the driver.
            # However, its .parsed contains simple fields; we want taints + extra structure.
            # Convert to a richer form using the normalizer to add quarantine + provenance,
            # while preserving the observed timestamp.
            parsed = ev.parsed or {}
            title = parsed.get("title") or None
            link = parsed.get("link") or None
            cats = (parsed.get("categories") or []) or []
            enriched = build_event(
                driver_name=driver.NAME,
                version=driver.VERSION,
                source=f"rss:{s.id}",
                kind="rss.article",
                link=link,
                title=title,
                observed_ts=ev.t_observed,
                tags=list(cats) + (s.tags or []),
                body=parsed.get("description") or "",
                extra_parsed={"feed_url": s.url, "registry_id": s.id},
                guid_hint=parsed.get("guid") or link or title,
            )
            yield enriched

    # ------------------- JSON Feed -------------------
    async def _iter_jsonfeed(self, s: SourceCfg) -> AsyncIterator[AxonEvent]:
        client = await get_http_client()
        r = await client.get(s.url, timeout=float(s.timeout_sec or 10))
        r.raise_for_status()
        doc = r.json() or {}
        items = doc.get("items") or []
        for it in items:
            title = it.get("title") or None
            link = it.get("url") or None
            body = it.get("content_html") or it.get("content_text") or ""
            # dates
            dt = None
            for k in ("date_published", "date_modified"):
                if it.get(k):
                    try:
                        dt = it[k]
                        break
                    except Exception:
                        pass
            # Normalize to AxonEvent
            ev = build_event(
                driver_name="jsonfeed",
                version="1.0.0",
                source=f"jsonfeed:{s.id}",
                kind="news.item",
                link=link,
                title=title,
                observed_ts=None,  # let normalizer default to now; extend to parse ISO later
                tags=s.tags or [],
                body=body if isinstance(body, str) else str(body),
                extra_parsed={"feed_url": s.url, "registry_id": s.id, "raw_item": it},
                guid_hint=it.get("id") or link or title,
            )
            yield ev

    # ------------------- Arbitrary JSON (mapping) -------------------
    async def _iter_json(self, s: SourceCfg) -> AsyncIterator[AxonEvent]:
        client = await get_http_client()
        r = await client.get(s.url, timeout=float(s.timeout_sec or 10))
        r.raise_for_status()
        doc = r.json()
        rows = doc if isinstance(doc, list) else (doc.get("items") or [])
        for it in rows:
            # We pass the whole object as body so Quarantine can treat it as structured_data
            ev = build_event(
                driver_name="json",
                version="1.0.0",
                source=f"json:{s.id}",
                kind="news.item",
                link=(it.get("url") or it.get("link")) if isinstance(it, dict) else None,
                title=(it.get("title") if isinstance(it, dict) else None),
                observed_ts=None,
                tags=s.tags or [],
                body=it,
                extra_parsed={"feed_url": s.url, "registry_id": s.id},
                guid_hint=(it.get("id") if isinstance(it, dict) else None),
            )
            yield ev

    # ------------------- Stubs for future kinds -------------------
    async def _iter_csv(self, s: SourceCfg) -> AsyncIterator[AxonEvent]:
        # TODO: parse CSV → dict rows, then build_event(body=row, kind="tabular.row")
        if False:
            yield  # pragma: no cover

    async def _iter_ics(self, s: SourceCfg) -> AsyncIterator[AxonEvent]:
        # TODO: parse ICS → VEVENT(s), then build_event per event
        if False:
            yield  # pragma: no cover

    async def _iter_mqtt(self, s: SourceCfg) -> AsyncIterator[AxonEvent]:
        # TODO: subscribe to s.topic via local broker or bridge
        if False:
            yield  # pragma: no cover

    # ------------------- Public API -------------------
    async def iter_events(self) -> AsyncIterator[AxonEvent]:
        """
        Iterates all enabled sources, yielding AxonEvents.
        Call refresh() first if you want hot-reload behavior.
        """
        # snapshot enabled sources by kind
        rss = self.reg.iter_enabled("rss")
        jsf = self.reg.iter_enabled("jsonfeed")
        jsn = self.reg.iter_enabled("json")
        csv = self.reg.iter_enabled("csv")
        ics = self.reg.iter_enabled("ics")
        mqtt = self.reg.iter_enabled("mqtt")

        async def _yield_all(tasks: list):
            for coro in tasks:
                async for ev in coro:
                    yield ev

        # Launch per-source iterators serially by kind (easy backpressure). You can parallelize if needed.
        for s in rss:
            async for ev in self._iter_rss(s):
                yield ev
        for s in jsf:
            async for ev in self._iter_jsonfeed(s):
                yield ev
        for s in jsn:
            async for ev in self._iter_json(s):
                yield ev
        for s in csv:
            async for ev in self._iter_csv(s):
                yield ev
        for s in ics:
            async for ev in self._iter_ics(s):
                yield ev
        for s in mqtt:
            async for ev in self._iter_mqtt(s):
                yield ev
