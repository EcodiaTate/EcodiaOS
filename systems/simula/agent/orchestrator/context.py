# systems/simula/agent/orchestrator/context.py
# --- PROJECT SENTINEL UPGRADE ---
from __future__ import annotations

import json
import pathlib
import time
from typing import Any, Optional, Dict


class ContextStore:
    """A stateful, persisted working memory for a single agent run.

    Upgraded caching:
      - Cache entries stored as { "value": <any>, "ts": <epoch_sec>, "ttl": <float|None> }.
      - Lazy prune on reads/writes to prevent bloat.
      - Backward compatible: legacy entries (raw values) are auto-wrapped on load.
    """

    # Defaults for caching
    DEFAULT_CACHE_BUCKET = "tools_cache"
    DEFAULT_PRUNE_INTERVAL_SEC = 60.0  # soft gate for lazy pruning frequency

    def __init__(self, run_dir: str):
        self.run_dir = run_dir
        self.path = pathlib.Path(run_dir) / "session_state.json"
        self.state: dict[str, Any] = {}
        # ephemeral, not persisted
        self._last_prune_ts: Dict[str, float] = {}
        self.load()

    # --------------------------- Persistence ---------------------------

    def load(self) -> None:
        try:
            if self.path.exists():
                self.state = json.loads(self.path.read_text(encoding="utf-8"))
                self._normalize_state()
            else:
                self.state = self._default_state()
        except Exception:
            self.state = self._default_state()

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = json.dumps(self.state, ensure_ascii=False, indent=2, default=str)
            self.path.write_text(tmp, encoding="utf-8")
        except Exception:
            # Never crash the orchestrator on a persistence failure
            pass

    def _default_state(self) -> dict[str, Any]:
        """The canonical structure for a new session's state."""
        return {
            "status": "initializing",   # e.g., planning, generating, validating, failed
            "plan": {},                 # The high-level plan from the user/planner
            "dossier": {},              # Rich context for the current task
            "failures": [],             # A log of failed tool/validation steps
            "facts": {},                # General key-value memory
            "summaries": [],            # High-level history for the LLM
            # Cache bucket: key -> {value:any, ts:float, ttl:float|None}
            self.DEFAULT_CACHE_BUCKET: {},
        }

    def _normalize_state(self) -> None:
        """Migrate any legacy structures to the new canonical layout."""
        # Ensure required top-level keys exist
        self.state.setdefault("status", "initializing")
        self.state.setdefault("plan", {})
        self.state.setdefault("dossier", {})
        self.state.setdefault("failures", [])
        self.state.setdefault("facts", {})
        self.state.setdefault("summaries", [])
        self.state.setdefault(self.DEFAULT_CACHE_BUCKET, {})

        # Wrap any legacy cache values into {value, ts, ttl}
        bucket = self.state.get(self.DEFAULT_CACHE_BUCKET, {})
        if isinstance(bucket, dict):
            changed = False
            now = time.time()
            for k, v in list(bucket.items()):
                if not isinstance(v, dict) or "value" not in v or "ts" not in v:
                    bucket[k] = {"value": v, "ts": now, "ttl": None}
                    changed = True
            if changed:
                self.state[self.DEFAULT_CACHE_BUCKET] = bucket

    # --------------------------- High-level state modifiers ---------------------------

    def set_status(self, status: str) -> None:
        self.state["status"] = status
        self.save()

    def update_dossier(self, dossier: dict[str, Any]) -> None:
        self.state["dossier"] = dossier
        self.save()

    def add_failure(self, tool_name: str, reason: str, params: dict | None = None) -> None:
        self.state.setdefault("failures", []).append(
            {
                "tool_name": tool_name,
                "reason": reason,
                "params": params or {},
                "timestamp": time.time(),
            }
        )
        self.save()

    def remember_fact(self, key: str, value: Any) -> None:
        self.state.setdefault("facts", {})[key] = value
        self.save()

    def get_fact(self, key: str, default=None) -> Any:
        return self.state.get("facts", {}).get(key, default)

    def push_summary(self, text: str, max_items: int = 8) -> None:
        summaries = self.state.setdefault("summaries", [])
        summaries.append(text[:2000])
        self.state["summaries"] = summaries[-max_items:]
        self.save()

    # --------------------------- TTL Cache API ---------------------------

    def _ensure_bucket(self, bucket: str) -> dict:
        bk = self.state.setdefault(bucket, {})
        if not isinstance(bk, dict):
            # heal if bucket was corrupted somehow
            bk = {}
            self.state[bucket] = bk
        return bk

    def _is_expired(self, entry: dict) -> bool:
        """Return True if entry has ttl and is expired."""
        if not isinstance(entry, dict):
            return False
        ttl = entry.get("ttl")
        ts = entry.get("ts")
        if ttl is None or ts is None:
            return False
        try:
            return (time.time() - float(ts)) > float(ttl)
        except Exception:
            # if malformed, consider it expired to be safe
            return True

    def _maybe_prune(self, bucket: str) -> int:
        """Prune expired entries if the soft interval has passed. Returns count pruned."""
        now = time.time()
        last = self._last_prune_ts.get(bucket, 0.0)
        if (now - last) < self.DEFAULT_PRUNE_INTERVAL_SEC:
            return 0
        self._last_prune_ts[bucket] = now
        return self.cache_prune(bucket=bucket)

    def cache_put(
        self,
        key: str,
        value: Any,
        ttl_sec: Optional[float] = None,
        bucket: str = DEFAULT_CACHE_BUCKET,
    ) -> None:
        """Insert/overwrite a cache entry with optional TTL.

        ttl_sec:
          - None => non-expiring
          - >= 0 float seconds => expires after that duration
        """
        b = self._ensure_bucket(bucket)
        b[key] = {"value": value, "ts": time.time(), "ttl": float(ttl_sec) if ttl_sec is not None else None}
        # opportunistic prune to avoid unbounded growth
        self._maybe_prune(bucket)
        self.save()

    def cache_get(
        self,
        key: str,
        bucket: str = DEFAULT_CACHE_BUCKET,
        default: Any = None,
    ) -> Any:
        """Return cached value if present and not expired; otherwise remove and return default."""
        b = self._ensure_bucket(bucket)
        entry = b.get(key)
        if entry is None:
            # opportunistic prune even on miss
            self._maybe_prune(bucket)
            return default

        if self._is_expired(entry):
            # expired -> delete and return default
            try:
                del b[key]
            except Exception:
                pass
            # prune other expired entries occasionally
            self._maybe_prune(bucket)
            self.save()
            return default

        # fresh
        self._maybe_prune(bucket)
        return entry.get("value")

    def cache_delete(self, key: str, bucket: str = DEFAULT_CACHE_BUCKET) -> None:
        b = self._ensure_bucket(bucket)
        if key in b:
            del b[key]
            self.save()

    def cache_clear(self, bucket: str = DEFAULT_CACHE_BUCKET) -> None:
        self.state[bucket] = {}
        self.save()

    def cache_prune(self, bucket: str = DEFAULT_CACHE_BUCKET) -> int:
        """Eagerly remove all expired entries in the bucket. Returns number removed."""
        b = self._ensure_bucket(bucket)
        to_delete = []
        for k, entry in b.items():
            if self._is_expired(entry):
                to_delete.append(k)
        for k in to_delete:
            try:
                del b[k]
            except Exception:
                pass
        if to_delete:
            self.save()
        return len(to_delete)
