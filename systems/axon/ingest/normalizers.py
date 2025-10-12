# systems/axon/ingest/normalizers.py
from __future__ import annotations

import email.utils as eut
import hashlib
import json
import re
import uuid
from datetime import UTC, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from systems.axon.io.quarantine import CanonicalizedPayload, Quarantine
from systems.axon.schemas import AxonEvent

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _now_ts() -> float:
    return datetime.now(UTC).timestamp()


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(p or "" for p in parts).encode()).hexdigest()


_A_TAG_RE = re.compile(
    r'<a\b[^>]*href=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_BOILERPLATE_POST_RE = re.compile(
    r"\bThe post\b.*?\bappeared first on\b.*?$", re.IGNORECASE | re.DOTALL
)

TRACKING_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "utm_brand",
    "utm_reader",
    "utm_name",
    "utm_social",
    "utm_social-type",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
}


def _clean_url(u: str) -> str:
    """Strip tracking params and fragments, keep everything else intact."""
    try:
        if not u:
            return u
        sp = urlsplit(u)
        fragless = sp._replace(fragment="")
        if fragless.query:
            q = [
                (k, v)
                for (k, v) in parse_qsl(fragless.query, keep_blank_values=True)
                if k not in TRACKING_KEYS
            ]
            fragless = fragless._replace(query=urlencode(q))
        return urlunsplit(fragless)
    except Exception:
        return u


def _hostname(u: str) -> str | None:
    try:
        return urlsplit(u).hostname
    except Exception:
        return None


def _dedupe_links(links: list[str], primary: str | None) -> list[str]:
    """Deduplicate, strip tracking, and drop bare site-root duplicates of the primary domain."""
    seen = set()
    out = []
    base = _hostname(primary) if primary else None
    for u in links or []:
        cu = _clean_url(u)
        if not cu:
            continue
        if base and _hostname(cu) == base:
            # Drop exact site root like https://example.com/
            if cu.rstrip("/").lower() == (f"https://{base}".rstrip("/").lower()):
                continue
        if cu not in seen:
            seen.add(cu)
            out.append(cu)
    return out


def _parse_pub_ts(obj: dict | None) -> float | None:
    """
    Try to parse a publication timestamp from common feed keys:
      - 'timestamp' (epoch)
      - 'published'/'updated'/'pubDate' (RFC2822 strings)
      - 'published_parsed'/'updated_parsed' (time.struct_time)
    """
    if not obj:
        return None
    try:
        if "timestamp" in obj and obj["timestamp"]:
            return float(obj["timestamp"])
        for k in ("published", "updated", "pubDate"):
            v = obj.get(k)
            if isinstance(v, str):
                dt = eut.parsedate_to_datetime(v)
                if dt:
                    return dt.timestamp()
        for k in ("published_parsed", "updated_parsed"):
            v = obj.get(k)
            if v:
                import time as _t

                return float(_t.mktime(v))
    except Exception:
        return None
    return None


def _summarize(text: str, n: int = 280) -> str | None:
    if not text:
        return None
    t = text.strip()
    if len(t) <= n:
        return t
    return (t[:n].rsplit(" ", 1)[0] + "…") if " " in t[:n] else t[:n] + "…"


def _extract_links_from_html(raw: str) -> list[str]:
    """Return all hrefs from <a> tags in the raw HTML."""
    try:
        return [m.group(1).strip() for m in _A_TAG_RE.finditer(raw or "")]
    except Exception:
        return []


def _strip_boilerplate(text: str) -> str:
    """Remove common feed boilerplate like 'The post ... appeared first on ...'."""
    if not text:
        return text
    cleaned = _BOILERPLATE_POST_RE.sub("", text).strip()
    # Collapse excessive whitespace
    cleaned = _WS_RE.sub(" ", cleaned)
    cleaned = re.sub(r" *(?:\n\s*){2,}", "\n\n", cleaned)
    return cleaned.strip()


def _enrich_hnrss(text: str, anchors: list[str]) -> dict[str, Any]:
    """
    Parse HN RSS (hnrss.org) description blocks into structured fields.
    Expected lines include:
      'Article URL:' + link
      'Comments URL:' + link
      'Points: N'
      '# Comments: M'
    Anchors may already contain both URLs; otherwise we fallback to line regex.
    """
    out: dict[str, Any] = {}
    # Try anchors first
    if anchors:
        comments = [u for u in anchors if "news.ycombinator.com" in u]
        articles = [u for u in anchors if "news.ycombinator.com" not in u]
        if articles:
            out["article_url"] = articles[0]
        if comments:
            out["comments_url"] = comments[0]

    # Fallback: parse from plain text
    plain = _HTML_TAG_RE.sub("", text or "")
    lines = [ln.strip() for ln in plain.splitlines() if ln.strip()]
    for ln in lines:
        lnl = ln.lower()
        if lnl.startswith("article url"):
            m = re.search(r"(https?://\S+)", ln)
            if m:
                out.setdefault("article_url", m.group(1))
        elif lnl.startswith("comments url"):
            m = re.search(r"(https?://\S+)", ln)
            if m:
                out.setdefault("comments_url", m.group(1))
        elif lnl.startswith("points"):
            m = re.search(r"(\d+)", ln)
            if m:
                out["points"] = int(m.group(1))
        elif "# comments" in lnl:
            m = re.search(r"(\d+)", ln)
            if m:
                out["num_comments"] = int(m.group(1))
    return out


def _canonize_text_or_json(q: Quarantine, body: Any) -> tuple[CanonicalizedPayload, list[str], str]:
    """
    Canonicalize payload and (if HTML) return extracted anchors too.
    Returns (canon_payload, links, raw_str_used_for_canon)
    """
    # Structured JSON → pass through as JSON
    if isinstance(body, dict):
        cp = q.process_and_canonicalize(body, "application/json")
        return cp, [], ""  # raw not needed in this branch

    # Convert to string for text/html handling
    raw = str(body or "")

    # Extract anchors before sanitization
    links = _extract_links_from_html(raw) if ("<" in raw and ">" in raw) else []

    # Canonicalize as HTML vs plain text
    if "<" in raw and ">" in raw:
        cp = q.process_and_canonicalize(raw, "text/html")
    else:
        cp = q.process_and_canonicalize(raw, "text/plain")

    return cp, links, raw


def _postprocess_parsed(
    parsed: dict[str, Any], *, registry_id: str | None, raw_text: str, anchors: list[str]
) -> dict[str, Any]:
    """
    Apply feed-specific cleanup/enrichment.
    """
    # Attach extracted anchors as generic links (dedup/clean)
    if anchors:
        existing = parsed.get("links") or []
        parsed["links"] = _dedupe_links(existing + anchors, parsed.get("link"))

    # Clean boilerplate from text if present and add summary
    if parsed.get("text"):
        parsed["text"] = _strip_boilerplate(parsed["text"])
        parsed.setdefault("summary", _summarize(parsed["text"], 280))

    # HN front page enrichment
    if registry_id == "hn-front":
        extra = _enrich_hnrss(raw_text, anchors)
        if extra:
            parsed.update(extra)

    # Normalize primary link and expose domain
    if parsed.get("link"):
        parsed["link"] = _clean_url(parsed["link"])
        parsed["domain"] = _hostname(parsed["link"])

    # Clean every link we keep
    if parsed.get("links"):
        parsed["links"] = [_clean_url(u) for u in parsed["links"]]

    return parsed


# -----------------------------------------------------------------------------
# Public builder
# -----------------------------------------------------------------------------


def build_event(
    *,
    driver_name: str,
    version: str,
    source: str,
    kind: str,
    link: str | None,
    title: str | None,
    observed_ts: float | None,
    tags: list[str],
    body: Any,
    extra_parsed: dict[str, Any] | None = None,
    guid_hint: str | None = None,
) -> AxonEvent:
    """
    Returns an AxonEvent with sanitized payload embedded in .parsed.
    - Extracts anchors from HTML to preserve URLs lost in sanitization
    - Cleans boilerplate; enriches known feeds (hnrss)
    - De-tracks URLs, adds domain + short summary
    - Stores publish time (if found) in parsed['published_ts']
    """
    q = Quarantine()
    cp, anchors, raw = _canonize_text_or_json(q, body)

    parsed: dict[str, Any] = {
        "title": title,
        "link": link,
        "tags": tags or [],
    }
    if cp.content_type == "text":
        parsed["text"] = "\n\n".join(cp.text_blocks or [])
    elif cp.content_type == "structured_data":
        parsed["structured_data"] = cp.structured_data or {}

    # Merge extra fields (feed_url, registry_id, raw_item, etc.)
    reg_id = None
    if extra_parsed:
        parsed.update(extra_parsed)
        reg_id = extra_parsed.get("registry_id")

    # Feed-specific postprocess (anchors, boilerplate, hnrss, url cleaning, summary, domain)
    parsed = _postprocess_parsed(parsed, registry_id=reg_id, raw_text=raw, anchors=anchors)

    # Try to capture publish time from the raw item if present (store inside parsed to avoid schema changes)
    pub_ts = None
    if extra_parsed:
        pub_ts = _parse_pub_ts(extra_parsed.get("raw_item") or extra_parsed)
    if pub_ts:
        parsed.setdefault("published_ts", pub_ts)

    guid_basis = (
        guid_hint or link or title or parsed.get("text") or json.dumps(parsed, ensure_ascii=False)
    )
    event_id = str(uuid.uuid4())
    t_obs = float(observed_ts or _now_ts())

    return AxonEvent(
        event_id=event_id,
        t_observed=t_obs,
        source=source,
        event_type=kind,
        modality="text" if cp.content_type == "text" else "json",
        payload_ref=link,
        parsed=parsed,
        embeddings={},
        provenance={
            "driver_id": driver_name,
            "version": version,
            "guid_hash": _stable_id(driver_name, version, guid_basis),
            "taints": [t.model_dump() for t in cp.taints],
        },
        salience_hints={"keywords": tags} if tags else {},
        quality={},
        triangulation={},
        cost_ms=None,
        cost_usd=0.0,
    )
