# systems/atune/ingest/followups.py
from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from core.metrics.registry import REGISTRY

# Rolling stores (process-local)
MAX_EVENTS = 500
_action_results: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)
_search_results: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)

# Simple keyword freq for salience hints
_kw_freq: dict[str, int] = defaultdict(int)
_url_host_freq: dict[str, int] = defaultdict(int)

_url_host_rx = re.compile(r"^(?:https?://)?([^/]+)/?")


@dataclass
class HarvestSummary:
    action_results_ingested: int = 0
    search_results_ingested: int = 0
    kw_updates: int = 0
    host_updates: int = 0
    kw_top: list[str] = field(default_factory=list)
    host_top: list[str] = field(default_factory=list)


def _host_of(url: str) -> str:
    m = _url_host_rx.match(str(url or ""))
    return m.group(1).lower() if m else ""


def harvest_followup_event(ev: dict[str, Any]) -> HarvestSummary:
    et = str(ev.get("event_type", ""))
    parsed = ev.get("parsed") or {}
    s = HarvestSummary()

    if et == "action.result":
        _action_results.append(ev)
        s.action_results_ingested += 1
        status = str(parsed.get("status", ""))
        REGISTRY.counter(f"atune.followups.action_result.{status or 'unknown'}").inc()

        # harvest keywords from summary
        summary = str(parsed.get("summary", ""))
        for kw in re.findall(r"[A-Za-z]{3,}", summary.lower()):
            _kw_freq[kw] += 1
            s.kw_updates += 1

    elif et == "search.results":
        _search_results.append(ev)
        s.search_results_ingested += 1
        REGISTRY.counter("atune.followups.search_results").inc()

        results = parsed.get("results") or []
        for r in results[:10]:
            host = _host_of(r.get("url", ""))
            if host:
                _url_host_freq[host] += 1
                s.host_updates += 1

            # lightweight keyword bumps from titles/snippets
            blob = (r.get("title") or "") + " " + (r.get("snippet") or "")
            for kw in re.findall(r"[A-Za-z]{3,}", blob.lower()):
                _kw_freq[kw] += 1
                s.kw_updates += 1

    # precompute top-k for quick hints
    if _kw_freq:
        s.kw_top = sorted(_kw_freq, key=_kw_freq.get, reverse=True)[:20]
        REGISTRY.gauge("atune.followups.kw_unique").set(len(_kw_freq))
    if _url_host_freq:
        s.host_top = sorted(_url_host_freq, key=_url_host_freq.get, reverse=True)[:20]
        REGISTRY.gauge("atune.followups.host_unique").set(len(_url_host_freq))

    return s


def harvest_batch_followups(events: list[dict[str, Any]]) -> HarvestSummary:
    agg = HarvestSummary()
    for ev in events:
        s = harvest_followup_event(ev)
        agg.action_results_ingested += s.action_results_ingested
        agg.search_results_ingested += s.search_results_ingested
        agg.kw_updates += s.kw_updates
        agg.host_updates += s.host_updates
    return agg


def salience_hints_from_harvest() -> dict[str, Any]:
    """
    Returns ultra-light hints derived from follow-ups. You can pass pieces of this
    into your salience/planner as priors (optional).
    """
    return {
        "top_keywords": sorted(_kw_freq, key=_kw_freq.get, reverse=True)[:50],
        "top_hosts": sorted(_url_host_freq, key=_url_host_freq.get, reverse=True)[:50],
    }
