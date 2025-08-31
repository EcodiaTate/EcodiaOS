# core/llm/utils.py
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from typing import Any, Literal

__all__ = [
    # existing
    "filter_kwargs",
    "normalise_messages",  # legacy alias
    "normalize_messages",  # preferred name
    # new general-purpose utils
    "clamp",
    "coerce_str",
    "redact_secrets",
    "detect_json",
    "safe_truncate",
    "estimate_tokens",
    "toxicity_hint",
    "length_fit_score",
    "baseline_metrics",
    "combine_with_system",
    # additions that remain internal-friendly (ok to import)
    "strip_code_fences",
    "extract_json_block",
    "first_system_message",
    "split_system_and_chat",
    "dedupe_system_message",
    "messages_checksum",
]

# ---------------------------------------------------------------------
# Core hygiene
# ---------------------------------------------------------------------


def filter_kwargs(allowed_keys: Iterable[str], kwargs: dict[str, Any]) -> dict[str, Any]:
    """Return only keys in allowed_keys."""
    allowed = set(allowed_keys or [])
    return {k: v for k, v in (kwargs or {}).items() if k in allowed}


def normalize_messages(
    prompt: str | None = None,
    messages: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """
    Back-compat normalizer for legacy call sites.
    - If messages provided: clean them (coerce to strings, trim, drop empties).
    - Else if prompt provided: wrap as a single user message.
    - Else: raise.

    NOTE: Provider-specific shaping now happens in the bus or formatters;
    this is *just hygiene*.
    """
    if messages is not None:
        if not isinstance(messages, list):
            raise ValueError("`messages` must be a list of dicts.")
        out: list[dict[str, str]] = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            role = str(m.get("role", "user")).strip().lower() or "user"
            if role not in ("system", "user", "assistant"):
                role = "user"
            content = m.get("content", "")
            if content is None:
                continue
            if not isinstance(content, str):
                try:
                    content = str(content)
                except Exception:
                    continue
            content = content.replace("\x00", "").strip()
            if not content:
                continue
            out.append({"role": role, "content": content})
        if not out:
            raise ValueError("No non-empty messages after normalization.")
        return out

    if prompt is not None:
        p = prompt if isinstance(prompt, str) else str(prompt)
        p = p.strip()
        if not p:
            raise ValueError("`prompt` is empty after trimming.")
        return [{"role": "user", "content": p}]

    raise ValueError("Either `prompt` or `messages` must be provided.")


# British/Aussie spelling kept for legacy imports
def normalise_messages(
    prompt: str | None = None,
    messages: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    return normalize_messages(prompt=prompt, messages=messages)


def combine_with_system(
    system_prompt: str | None,
    messages: list[dict[str, str]],
) -> list[dict[str, str]]:
    """
    Prepend a system message (if any) to normalized messages. Provider adapters
    can reshape later; this only ensures canonical ordering.

    AGI note: If the first message is already a system, we do NOT add another.
    PromptSpec generally injects system preambles; this keeps us from duplicating.
    """
    msgs = normalise_messages(messages=messages)
    if system_prompt and system_prompt.strip():
        if not msgs or msgs[0].get("role") != "system":
            msgs = [{"role": "system", "content": system_prompt.strip()}] + msgs
    return msgs


# ---------------------------------------------------------------------
# Small, pure helpers (no heavy deps)
# ---------------------------------------------------------------------


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return hi if x > hi else lo if x < lo else x


def coerce_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return repr(value)


_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*=\s*([A-Za-z0-9_\-]{12,})"),
    re.compile(r"(?i)(bearer)\s+([A-Za-z0-9\._\-]{12,})"),
    re.compile(r"(?i)(sk-[A-Za-z0-9]{16,})"),
]


def redact_secrets(text: str) -> str:
    """
    Mask common secret-like substrings (very conservative).
    """
    s = text or ""
    for rx in _SECRET_PATTERNS:
        s = rx.sub(lambda m: f"{m.group(1)}=***REDACTED***", s)
    return s


# ---------------- JSON helpers (robust against noise/fences) -----------------

FENCE_RX = re.compile(r"^```[a-zA-Z0-9_+-]*\s*$")


def strip_code_fences(text: str) -> str:
    """
    If text is a single fenced block, strip the ```lang … ``` wrapper.
    Otherwise returns text unchanged.
    """
    if not text:
        return ""
    lines = text.strip().splitlines()
    if len(lines) >= 2 and FENCE_RX.match(lines[0]) and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text


_JSON_BLOCK_RX = re.compile(r"(?s)(```json\s*(?P<fjson>.+?)\s*```)|(?P<obj>\{.*\})|(?P<arr>\[.*\])")


def extract_json_block(s: str) -> str | None:
    """
    Try to pull a JSON-looking block from text (fenced ```json ...``` wins).
    Returns the raw JSON substring if found, else None.
    """
    if not s:
        return None
    m = _JSON_BLOCK_RX.search(s.strip())
    if not m:
        return None
    if m.group("fjson"):
        return m.group("fjson").strip()
    if m.group("obj"):
        return m.group("obj").strip()
    if m.group("arr"):
        return m.group("arr").strip()
    return None


def detect_json(s: str) -> tuple[bool, dict | list | None]:
    """
    Try to parse JSON object/array; returns (ok, obj_or_list_or_None).
    Handles noisy outputs with fences or extra commentary.
    """
    if not s:
        return False, None
    candidate = extract_json_block(strip_code_fences(s)) or s.strip()
    if not (candidate.startswith("{") or candidate.startswith("[")):
        return False, None
    try:
        return True, json.loads(candidate)
    except Exception:
        return False, None


def safe_truncate(text: str, max_chars: int = 4000) -> str:
    """
    Cut by characters with a clean ellipsis boundary.
    """
    if not text or len(text) <= max_chars:
        return text or ""
    return (text[: max(0, max_chars - 1)].rstrip()) + "…"


def estimate_tokens(text: str, *, mode: Literal["chars/4", "words*0.75"] = "chars/4") -> int:
    """
    Very rough token estimate without model-specific libs.
    - "chars/4": common heuristic (default)
    - "words*0.75": count word-ish chunks and scale
    """
    if not text:
        return 0
    if mode == "words*0.75":
        n_words = max(1, len(re.findall(r"\w+", text)))
        return max(1, int(n_words * 0.75))
    return max(1, int(len(text) / 4))


# ---------------------------------------------------------------------
# Tiny heuristics for learner baselines (keep generic; no Equor import)
# ---------------------------------------------------------------------

_BAD_WORDS = {"kill", "hate", "ugly", "stupid", "idiot"}


def toxicity_hint(text: str) -> float:
    toks = re.findall(r"[A-Za-z]+", (text or "").lower())
    return 0.0 if (set(toks) & _BAD_WORDS) else 1.0


def length_fit_score(text: str, target: int = 200, tol: float = 0.5) -> float:
    """
    Reward being within target ± tol range (by characters). Soft penalties outside.
    """
    n = len((text or "").strip())
    if n == 0:
        return 0.0
    lo, hi = int(target * (1 - tol)), int(target * (1 + tol))
    if n < lo:
        return clamp(n / max(1, lo) * 0.8)
    if n > hi:
        return clamp(hi / max(1, n))
    return 1.0


def baseline_metrics(
    output_text: str,
    *,
    agent: str | None = None,
    scope: str | None = None,
    facet_keys: list[str] | None = None,
    target_len: int = 220,
    base_helpfulness: float = 0.7,
    base_brand: float = 0.7,
) -> dict[str, Any]:
    """
    Lightweight, non-empty metrics scaffold so the learner never starves.
    Callers can enrich and re-save later.
    """
    return {
        "helpfulness": clamp(base_helpfulness),
        "brand_consistency": clamp(base_brand),
        "toxicity": toxicity_hint(output_text),
        "length_fit": length_fit_score(output_text, target=target_len),
        "agent": agent,
        "scope": scope,
        "facet_keys": list(facet_keys or []),
    }


# ---------------------------------------------------------------------
# Extra PromptSpec-era niceties
# ---------------------------------------------------------------------


def first_system_message(messages: list[dict[str, Any]]) -> str | None:
    """
    Return the first system message content, if present.
    """
    for m in messages or []:
        if m.get("role") == "system":
            c = m.get("content")
            return c if isinstance(c, str) else None
    return None


def split_system_and_chat(
    messages: list[dict[str, Any]],
) -> tuple[str | None, list[dict[str, str]]]:
    """
    Return (system_prompt, chat_messages_without_system), with chat messages normalized.
    """
    norm = normalise_messages(messages=messages)
    sys = None
    rest: list[dict[str, str]] = []
    for m in norm:
        if m["role"] == "system" and sys is None:
            sys = m["content"]
        else:
            rest.append(m)
    return sys, rest


def dedupe_system_message(
    system_prompt: str | None,
    messages: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """
    Ensure only one system message exists: prefer the explicit system_prompt if provided,
    else keep the first system in messages.
    """
    sys_in_msgs, chat = split_system_and_chat(messages)
    sys = (system_prompt or sys_in_msgs or "").strip()
    if sys:
        return [{"role": "system", "content": sys}] + chat
    return chat


def messages_checksum(messages: list[dict[str, Any]]) -> str:
    """
    Stable checksum for provenance (WhyTrace/ReplayCapsule).
    Ignores ordering of dict keys but preserves order of messages.
    """
    blob = "\n".join(
        f"{m.get('role', '')}:{json.dumps(m.get('content', ''), ensure_ascii=False)}"
        for m in messages or []
    )
    return hashlib.blake2b(blob.encode("utf-8"), digest_size=16).hexdigest()
