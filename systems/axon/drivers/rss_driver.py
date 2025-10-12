# systems/axon/drivers/rss_driver.py
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time as pytime
import uuid
import xml.etree.ElementTree as ET
from collections import OrderedDict
from collections.abc import AsyncIterator, Iterable
from datetime import UTC, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, List

from core.utils.net_api import get_http_client
from systems.axon.mesh.sdk import CapabilitySpec, DriverInterface, HealthStatus, ReplayCapsule
from systems.axon.schemas import ActionResult, AxonEvent, AxonIntent

# --- Prometheus (safe no-op fallback) ---
try:
    from prometheus_client import Counter  # type: ignore
except Exception:  # pragma: no cover

    class Counter:  # minimal no-op
        def __init__(self, *a, **k): ...
        def labels(self, **k):
            return self

        def inc(self, *a, **k): ...


RSS_PULL_ITEMS = Counter(
    "axon_rss_items_yielded_total",
    "Total items yielded by RSS driver",
    ["feed"],
)

# ----------------------------- Namespaces & helpers -----------------------------

ATOM_NS = "http://www.w3.org/2005/Atom"
DC_NS = "http://purl.org/dc/elements/1.1/"
NSMAP = {"atom": ATOM_NS, "dc": DC_NS}
DEBUG = os.getenv("AXON_RSS_DEBUG", "0") == "1"


def _to_epoch(dt: datetime | None) -> float | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return float(dt.timestamp())


def _parse_when(text: str | None) -> float | None:
    if not text:
        return None
    try:
        return _to_epoch(parsedate_to_datetime(text))
    except Exception:
        return None


def _first_text(elem: ET.Element, *paths: str) -> str | None:
    for p in paths:
        ns_path = []
        for part in p.split("/"):
            if ":" in part:
                prefix, local = part.split(":", 1)
                ns_path.append(f"{{{NSMAP.get(prefix, '')}}}{local}")
            else:
                ns_path.append(part)
        q = "/".join(ns_path)
        hit = elem.find(q)
        if hit is not None:
            val = (hit.text or "").strip()
            if val:
                return val
    return None


def _stable_guid(*parts: str) -> str:
    payload = "|".join((p or "") for p in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _coalesce_time(item: ET.Element) -> float:
    RSS_pub = _parse_when(_first_text(item, "pubDate"))
    ATOM_upd = _parse_when(_first_text(item, "atom:updated"))
    ATOM_pub = _parse_when(_first_text(item, "atom:published"))
    DC_date = _parse_when(_first_text(item, "dc:date"))
    return float(RSS_pub or ATOM_upd or ATOM_pub or DC_date or pytime.time())


def _extract_link(item: ET.Element) -> str:
    # Common RSS <link> or Atom <link rel="alternate" href="...">
    link = _first_text(item, "link", "atom:title") or ""
    # If RSS <link> node was a text child, we already got it. For Atom, inspect link elements.
    for link_el in item.findall(f".//{{{ATOM_NS}}}link"):
        href = (link_el.get("href") or "").strip()
        rel = (link_el.get("rel") or "alternate").lower()
        if rel == "alternate" and href:
            link = href
            break
    if not link:
        link_el = item.find(f".//{{{ATOM_NS}}}link")
        if link_el is not None:
            href = (link_el.get("href") or "").strip()
            if href:
                link = href
    return link.strip()


def _parse_listish(s: str) -> list[str]:
    # Split on commas, whitespace, or newlines; strip comments (# ...)
    parts: list[str] = []
    for line in re.split(r"[\n\r]+", s):
        line = re.sub(r"#.*$", "", line).strip()
        if not line:
            continue
        parts.extend([p.strip() for p in re.split(r"[,\s]+", line) if p.strip()])
    # De-dupe while preserving order
    seen = set()
    out: list[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _load_opml(path: str | None) -> list[str]:
    if not path:
        return []
    try:
        doc = ET.parse(path).getroot()
        urls: list[str] = []
        for node in doc.findall(".//outline"):
            url = node.get("xmlUrl") or node.get("url")
            if url:
                urls.append(url.strip())
        return urls
    except Exception:
        return []


def _normalize_urls(urls: Iterable[str]) -> list[str]:
    """Normalize + strongly de-dupe feed list to prevent double pulls."""
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if not isinstance(u, str):
            continue
        u = u.strip()
        if not u:
            continue
        # very light normalization
        u = u.replace("http://feeds.bbci.co.uk", "https://feeds.bbci.co.uk")
        if u.endswith("/"):
            u = u[:-1]
        if u not in seen and u.startswith(("http://", "https://")):
            seen.add(u)
            out.append(u)
    return out


DEFAULT_FEEDS: list[str] = []

# --------------------------------- Driver --------------------------------------


class RssDriver(DriverInterface):
    """
    Pulls RSS/Atom from many feeds concurrently with replay + dedupe.

    Env toggles / tuning:
      AXON_ENABLE_RSS=1
      AXON_SENSE_PERIOD_SEC=60
      AXON_RSS_MAX_BYTES=2000000
      AXON_RSS_TIMEOUT=10
      AXON_RSS_WARMUP_MAX=3
      AXON_RSS_BOOT_BACKFILL_SEC=0
      AXON_RSS_SEEN_MAX=4096
      AXON_RSS_DEFAULT_URL=<url>
      AXON_RSS_URLS="url1, url2, ..."
      AXON_RSS_OPML_PATH=/path/to/feeds.opml
      AXON_RSS_TOTAL_LIMIT=0    # 0 = unlimited
      AXON_RSS_CONCURRENCY=8
    """

    NAME = "rss"
    VERSION = "2.1.0"
    CAPABILITY = None  # no push

    _SEEN_MAX = int(os.getenv("AXON_RSS_SEEN_MAX", "4096"))

    def __init__(self):
        self._pull_cache: dict[str, str] = {}
        self._id_map: dict[str, str] = {}
        self._seen: OrderedDict[str, None] = OrderedDict()  # GUID LRU across all feeds

        self._started_at = pytime.time()
        self._first_pull = True
        self._last_pull_id_by_feed: dict[str, str] = {}
        # Conditional GET support to reduce 200/OK churn on 301/302/304 feeds
        self._last_etag: dict[str, str] = {}
        self._last_modified: dict[str, str] = {}

    def describe(self) -> CapabilitySpec:
        return CapabilitySpec(
            driver_name=self.NAME,
            driver_version=self.VERSION,
            supported_actions=[],
            risk_profile={},
            budget_model={"pull": 1.0},
            auth_requirements=["none"],
        )

    async def _fetch_feed_bytes(self, url: str, timeout: float) -> tuple[str, bytes, str] | None:
        """
        Returns (encoding, content_bytes, content_sha) or None if 304/unchanged.
        Follows redirects explicitly (some environments disable global follow).
        Sends If-None-Match / If-Modified-Since when available.
        """
        client = await get_http_client()
        headers = {
            "User-Agent": os.getenv("AXON_RSS_UA", "EcodiaAxonRSS/2.1 (+https://ecodia.local)"),
        }
        et = self._last_etag.get(url)
        lm = self._last_modified.get(url)
        if et:
            headers["If-None-Match"] = et
        if lm:
            headers["If-Modified-Since"] = lm

        # httpx.AsyncClient supports follow_redirects kw; requests-like clients ignore extra kw.
        resp = await client.get(url, timeout=timeout, follow_redirects=True, headers=headers)  # type: ignore
        if resp.status_code == 304:
            return None

        resp.raise_for_status()

        # Store for next time
        etag = resp.headers.get("ETag")
        last_mod = resp.headers.get("Last-Modified")
        if etag:
            self._last_etag[url] = etag
        if last_mod:
            self._last_modified[url] = last_mod

        content_bytes = resp.content
        enc = resp.encoding or "utf-8"
        return enc, content_bytes, hashlib.sha256(content_bytes).hexdigest()

    def _parse_feed_events(
        self,
        *,
        feed_url: str,
        raw_content: str,
        pull_id: str,
        warmup_cap: int,
        watermark: float | None,
        max_items_per_feed: int | None,
    ) -> list[AxonEvent]:
        # Parse XML
        try:
            root = ET.fromstring(raw_content)
        except Exception as e:
            if DEBUG:
                print(f"[RssDriver] XML parse error for {feed_url}: {e}")
            return []

        # Prefer RSS items; fallback to Atom entries
        items = root.findall(".//item")
        if not items:
            items = root.findall(f".//{{{ATOM_NS}}}entry")

        yielded_events: list[AxonEvent] = []
        yielded = 0
        skipped_old = 0

        for item in items:
            # warmup cap only on very first pull if caller didn't override a per-feed cap
            if self._first_pull and max_items_per_feed is None and yielded >= warmup_cap:
                break
            if max_items_per_feed is not None and yielded >= max_items_per_feed:
                break

            try:
                title = _first_text(item, "title", "atom:title") or ""
                desc = _first_text(item, "description", "atom:summary") or ""
                link = _extract_link(item)

                # If guid element exists and looks like a permalink, use it; else synth.
                guid_raw = _first_text(item, "guid", "atom:id") or ""
                if guid_raw and guid_raw.startswith("http"):
                    guid = guid_raw
                else:
                    guid = _stable_guid(feed_url, link, title, desc)

                t_obs = _coalesce_time(item)

                # Skip historical items on very first pull
                if watermark is not None and t_obs < watermark:
                    skipped_old += 1
                    continue

                # global de-dup
                if guid in self._seen:
                    self._seen.move_to_end(guid, last=True)
                    continue
                self._seen[guid] = None
                if len(self._seen) > self._SEEN_MAX:
                    self._seen.popitem(last=False)

                self._id_map[guid] = pull_id

                categories: list[str] = []
                for cat in item.findall("category"):
                    txt = (cat.text or "").strip()
                    if txt:
                        categories.append(txt)
                if not categories:
                    for cat in item.findall(f".//{{{ATOM_NS}}}category"):
                        term = (cat.get("term") or "").strip()
                        if term:
                            categories.append(term)

                parsed = {
                    "title": title or None,
                    "description": desc or None,
                    "link": link or None,
                    "guid": guid,
                    "categories": categories or None,
                    "feed_url": feed_url,
                }

                ev = AxonEvent(
                    event_id=str(uuid.uuid4()),
                    t_observed=t_obs,
                    source=f"rss:{feed_url}",
                    event_type="observation",
                    modality="text",
                    payload_ref=link or None,
                    parsed=parsed,
                    embeddings={},
                    provenance={
                        "driver_id": self.NAME,
                        "version": self.VERSION,
                        "feed_url": feed_url,
                        "pull_id": pull_id,
                    },
                    salience_hints={"keywords": categories} if categories else {},
                    quality={},
                    triangulation={},
                    cost_ms=None,
                    cost_usd=0.0,
                )
                yielded_events.append(ev)
                yielded += 1
                RSS_PULL_ITEMS.labels(feed=feed_url).inc()

            except Exception as ex:
                if DEBUG:
                    print(f"[RssDriver] skipped malformed item from {feed_url}: {ex}")
                continue

        if DEBUG:
            total_items = -1
            try:
                total_items = len(items)
            except Exception:
                pass
            wm_note = f" watermark={int(watermark) if watermark is not None else 'none'}"
            print(
                f"[RssDriver] feed={feed_url} pulled={total_items} yielded={len(yielded_events)} "
                f"skipped_old={skipped_old}{wm_note} pull_id={pull_id[:12]}",
            )

        return yielded_events

    def _resolve_feed_list(self, params: dict[str, Any]) -> list[str]:
        # Priority: params.urls -> AXON_RSS_URLS -> AXON_RSS_DEFAULT_URL -> DEFAULT_FEEDS
        urls: list[str] = []
        if "urls" in params and params["urls"]:
            if isinstance(params["urls"], (list, tuple)):
                urls = [str(u).strip() for u in params["urls"] if str(u).strip()]
            else:
                urls = _parse_listish(str(params["urls"]))
        elif os.getenv("AXON_RSS_URLS"):
            urls = _parse_listish(os.getenv("AXON_RSS_URLS", ""))
        elif os.getenv("AXON_RSS_DEFAULT_URL"):
            urls = [os.getenv("AXON_RSS_DEFAULT_URL", "").strip()]

        opml_urls = _load_opml(os.getenv("AXON_RSS_OPML_PATH"))
        # merge (params/env first), then OPML, then defaults
        merged = urls or []
        if opml_urls:
            merged = [*merged, *opml_urls]
        if not merged:
            merged = DEFAULT_FEEDS[:]

        # Normalize + dedupe hard (prevents the double GETs you saw in logs)
        merged = _normalize_urls(merged)
        return merged

    async def pull(self, params: dict[str, Any]) -> AsyncIterator[AxonEvent]:
        if os.getenv("AXON_ENABLE_RSS", "0") != "1":
            return

        urls = self._resolve_feed_list(params)
        if not urls:
            raise ValueError(
                "No RSS feeds configured (params.urls / AXON_RSS_URLS / OPML / defaults)."
            )

        http_timeout = float(params.get("timeout") or os.getenv("AXON_RSS_TIMEOUT", "10.0"))
        max_bytes = int(os.getenv("AXON_RSS_MAX_BYTES", "2000000"))
        warmup_cap = int(os.getenv("AXON_RSS_WARMUP_MAX", os.getenv("AXON_RSS_WARMUP_CAP", "3")))
        backfill_sec = float(os.getenv("AXON_RSS_BOOT_BACKFILL_SEC", "0"))
        watermark = self._started_at - max(0.0, backfill_sec) if self._first_pull else None

        # Optional limits
        per_feed_cap = params.get("max_items_per_feed")
        if isinstance(per_feed_cap, str):
            try:
                per_feed_cap = int(per_feed_cap)
            except Exception:
                per_feed_cap = None
        total_limit = params.get("total_limit")
        if total_limit is None:
            env_total = os.getenv("AXON_RSS_TOTAL_LIMIT", "0")
            total_limit = int(env_total) if env_total.isdigit() else 0
        if isinstance(total_limit, str):
            try:
                total_limit = int(total_limit)
            except Exception:
                total_limit = 0  # unlimited

        # Fetch feeds concurrently
        sem = asyncio.Semaphore(int(os.getenv("AXON_RSS_CONCURRENCY", "8")))

        async def process_one(feed_url: str) -> list[AxonEvent]:
            async with sem:
                try:
                    fetched = await self._fetch_feed_bytes(feed_url, http_timeout)
                    if fetched is None:
                        # 304 Not Modified
                        if DEBUG:
                            print(f"[RssDriver] 304 Not Modified for {feed_url}")
                        return []
                    enc, content_bytes, pull_id = fetched
                    if len(content_bytes) > max_bytes:
                        if DEBUG:
                            print(
                                f"[RssDriver] too large: {len(content_bytes)} > {max_bytes} bytes; {feed_url}"
                            )
                        return []
                    raw_content = content_bytes.decode(enc, errors="replace")

                    # identical content short-circuit (after warmup rules)
                    if self._last_pull_id_by_feed.get(feed_url) == pull_id:
                        if DEBUG:
                            print(f"[RssDriver] unchanged feed; skipping: {feed_url}")
                        return []

                    # cache for repro
                    self._pull_cache[pull_id] = raw_content

                    evs = self._parse_feed_events(
                        feed_url=feed_url,
                        raw_content=raw_content,
                        pull_id=pull_id,
                        warmup_cap=warmup_cap,
                        watermark=watermark,
                        max_items_per_feed=per_feed_cap if per_feed_cap is not None else None,
                    )

                    # Only mark feed pull as "seen" if we actually emitted events
                    if not (self._first_pull and len(evs) == 0):
                        self._last_pull_id_by_feed[feed_url] = pull_id
                    return evs
                except Exception as e:
                    if DEBUG:
                        print(f"[RssDriver] failed for {feed_url}: {e}")
                    return []

        tasks = [asyncio.create_task(process_one(u)) for u in urls]
        gathered: list[list[AxonEvent]] = await asyncio.gather(*tasks, return_exceptions=False)

        # Flatten and enforce total_limit (if any) in a stable order (by feed order)
        total = 0
        for ev_list in gathered:
            for ev in ev_list:
                if total_limit and total >= total_limit:
                    break
                yield ev
                total += 1
            if total_limit and total >= total_limit:
                break

        if DEBUG:
            print(
                f"[RssDriver] urls={len(urls)} yielded_total={total} watermark={'none' if watermark is None else int(watermark)}"
            )

        self._first_pull = False

    async def push(self, intent: AxonIntent) -> ActionResult:
        raise NotImplementedError("RssDriver does not support 'push'.")

    async def self_test(self) -> HealthStatus:
        try:
            ET.fromstring("<rss><channel><item><title>x</title></item></channel></rss>")
            return HealthStatus(status="ok", details="XML parser OK")
        except Exception as e:
            return HealthStatus(status="error", details=f"xml error: {e}")

    async def repro_bundle(self, *, id: str, kind: str) -> ReplayCapsule:
        pull_id = self._id_map.get(id)
        if not pull_id or pull_id not in self._pull_cache:
            # As a fallback, allow id to be a pull_id directly (useful in tests)
            if id in self._pull_cache:
                pull_id = id
            else:
                raise KeyError(f"No cached content for GUID {id}")
        raw_content = self._pull_cache[pull_id]
        env_hash = hashlib.blake2b(pull_id.encode("utf-8"), digest_size=16).hexdigest()
        return ReplayCapsule(
            id=id,
            type="event",
            driver_version=self.VERSION,
            environment_hash=env_hash,
            inputs={"params": {"urls": ["replay"]}, "pull_id": pull_id, "feed_url": "replay"},
            outputs={"raw_content": raw_content},
        )
