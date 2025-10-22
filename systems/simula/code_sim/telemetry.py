# systems/simula/code_sim/telemetry.py
"""
Drop-in, zero-dependency (stdlib-only) telemetry for Simula.
"""

from __future__ import annotations

import contextvars
import datetime as _dt
import inspect
import json
import os
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Dict, List

# ---------------- Core state ----------------
_current_job: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "simula_job",
    default=None,
)

# MODIFIED: The registry now stores metadata (like modes) for each tool.
_TOOL_REGISTRY: dict[str, dict[str, Any]] = {}
_ALIAS_INDEX: dict[str, str] = {}  # alias -> canonical tool name


def get_tracked_tools() -> dict[str, dict[str, Any]]:
    return _TOOL_REGISTRY

def resolve_tool(name_or_alias: str) -> str | None:
    """
    Return the canonical tool name for an exact registered name or alias.
    """
    if not name_or_alias:
        return None
    if name_or_alias in _TOOL_REGISTRY:
        return name_or_alias
    return _ALIAS_INDEX.get(name_or_alias)

def _now_iso() -> str:
    return _dt.datetime.now(tz=_dt.UTC).isoformat()


def _redact(obj: Any) -> Any:
    try:
        s = json.dumps(obj)
        if len(s) > 50_000:
            return {"_redacted": True, "reason": "payload_too_large", "approx_bytes": len(s)}
        return obj
    except Exception:
        return str(obj)


@dataclass
class Telemetry:
    enabled: bool = False
    sink: str = "both"  # stdout|file|both
    trace_dir: str = "/app/.simula/traces"
    sample: float = 1.0
    redact: bool = True
    _job_start_ts: dict[str, float] = field(default_factory=dict)

    # -------- lifecycle --------
    @classmethod
    def from_env(cls) -> Telemetry:
        enabled = os.getenv("SIMULA_TRACE", "0") not in ("0", "false", "False", "off", None)
        sink = os.getenv("SIMULA_TRACE_SINK", "both")
        trace_dir = os.getenv("SIMULA_TRACE_DIR", "/app/.simula/traces")
        sample = float(os.getenv("SIMULA_TRACE_SAMPLE", "1.0"))
        redact = os.getenv("SIMULA_TRACE_REDACT", "1") not in ("0", "false", "False", "off")
        t = cls(enabled=enabled, sink=sink, trace_dir=trace_dir, sample=sample, redact=redact)
        if enabled:
            t._ensure_dirs()
        return t

    def enable_if_env(self) -> None:
        if self.enabled:
            self._ensure_dirs()

    # -------- writing --------
    def _ensure_dirs(self) -> None:
        day = _dt.datetime.now().strftime("%Y-%m-%d")
        day_dir = os.path.join(self.trace_dir, day)
        os.makedirs(day_dir, exist_ok=True)

    def _job_file(self, job_id: str) -> str:
        day = _dt.datetime.now().strftime("%Y-%m-%d")
        day_dir = os.path.join(self.trace_dir, day)
        os.makedirs(day_dir, exist_ok=True)
        return os.path.join(day_dir, f"{job_id}.jsonl")

    def _write(self, job_id: str, event: dict[str, Any]) -> None:
        if not self.enabled:
            return
        try:
            event.setdefault("ts", _now_iso())
            line = json.dumps(event, ensure_ascii=False)
            if self.sink in ("stdout", "both"):
                print(f"SIMULA.TRACE {job_id} {line}")
            if self.sink in ("file", "both"):
                with open(self._job_file(job_id), "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception as e:
            print(f"[telemetry] write error: {e}", file=sys.stderr)

    # -------- public API --------
    def start_job(
        self,
        job_id: str | None = None,
        job_meta: dict[str, Any] | None = None,
    ) -> str:
        if job_id is None:
            job_id = uuid.uuid4().hex[:12]
        _current_job.set(job_id)
        self._job_start_ts[job_id] = time.perf_counter()
        self._write(job_id, {"type": "job_start", "job": job_meta or {}})
        return job_id

    def end_job(self, status: str = "ok", extra: dict[str, Any] | None = None) -> None:
        job_id = _current_job.get() or "unknown"
        dur = None
        if job_id in self._job_start_ts:
            dur = (time.perf_counter() - self._job_start_ts.pop(job_id)) * 1000.0
        self._write(
            job_id,
            {"type": "job_end", "status": status, "duration_ms": dur, "extra": extra or {}},
        )

    def llm_call(
        self,
        model: str,
        tokens_in: int,
        tokens_out: int,
        meta: dict[str, Any] | None = None,
    ) -> None:
        job_id = _current_job.get() or "unknown"
        self._write(
            job_id,
            {
                "type": "llm_call",
                "model": model,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "meta": meta or {},
            },
        )

    def reward(self, value: float, reason: str = "", meta: dict[str, Any] | None = None) -> None:
        job_id = _current_job.get() or "unknown"
        self._write(
            job_id,
            {"type": "reward", "value": value, "reason": reason, "meta": meta or {}},
        )

    def log_event(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        """Logs a generic, structured event."""
        job_id = _current_job.get() or "unknown"
        self._write(
            job_id,
            {
                "type": "generic_event",
                "event_type": event_type,
                "payload": payload or {},
            },
        )

    def tool_event(
        self,
        phase: str,
        name: str,
        args: Any = None,
        result: Any = None,
        ok: bool | None = None,
        err: str | None = None,
        extra: dict[str, Any] | None = None,
        started_ms: float | None = None,
    ) -> None:
        job_id = _current_job.get() or "unknown"
        payload: dict[str, Any] = {
            "type": "tool_" + phase,
            "name": name,
            "ok": ok,
            "err": err,
            "extra": extra or {},
        }
        if started_ms is not None:
            payload["duration_ms"] = (time.perf_counter() - started_ms) * 1000.0
        if self.redact:
            if args is not None:
                payload["args"] = {"_redacted": True}
            if result is not None:
                payload["result"] = {"_redacted": True}
        else:
            if args is not None:
                payload["args"] = _redact(args)
            if result is not None:
                payload["result"] = _redact(result)
        self._write(job_id, payload)

    def graph_write(
        self,
        nodes: int = 0,
        rels: int = 0,
        labels: dict[str, int] | None = None,
    ) -> None:
        job_id = _current_job.get() or "unknown"
        self._write(
            job_id,
            {"type": "graph_write", "nodes": nodes, "rels": rels, "labels": labels or {}},
        )


telemetry = Telemetry.from_env()


# --------------- Context manager for jobs ---------------
class with_job_context:
    def __init__(self, job_id: str | None = None, job_meta: dict[str, Any] | None = None):
        self.job_id = job_id
        self.job_meta = job_meta or {}
        self._token = None

    def __enter__(self):
        jid = telemetry.start_job(self.job_id, self.job_meta)
        self.job_id = jid
        return jid

    def __exit__(self, exc_type, exc, tb):
        status = "ok" if exc is None else "error"
        extra = {"exc": repr(exc)} if exc else None
        telemetry.end_job(status=status, extra=extra)
        return False


# --------------- Decorator for tools ---------------


# MODIFIED: The decorator now accepts a 'modes' argument and has a clearer structure.
def track_tool(
    tool_name: str,
    modes: list[str] | None = None,
    aliases: list[str] | None = None,
) -> Callable:

    """
    A decorator to register a tool for Simula's use and wrap it with telemetry.

    Args:
        tool_name: The name the agent will use to call the tool.
        modes: A list of operational modes (e.g., 'code_analysis', 'file_system')
               this tool is relevant for. Defaults to ['general'].
    """
    def _register(canonical: str, fn_wrapped: Callable[..., Any]):
            _TOOL_REGISTRY[canonical] = {
                "func": fn_wrapped,
                "modes": modes or ["general"],
                "aliases": list(aliases or []),
            }
            # index aliases for reverse lookup
            for a in aliases or []:
                if a and a != canonical:
                    _ALIAS_INDEX[a] = canonical

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(fn):
            @wraps(fn)
            async def async_wrapper(*args, **kwargs):
                t0 = time.perf_counter()
                telemetry.tool_event("start", tool_name, args={"argc": len(args), "keys": list(kwargs.keys())})
                try:
                    res = await fn(*args, **kwargs)
                    telemetry.tool_event("end", tool_name, result=res, ok=True, started_ms=t0)
                    return res
                except Exception as e:
                    telemetry.tool_event("end", tool_name, ok=False, err=repr(e), started_ms=t0)
                    raise
            _register(tool_name, async_wrapper)
            return async_wrapper
        else:
            @wraps(fn)
            def sync_wrapper(*args, **kwargs):
                t0 = time.perf_counter()
                telemetry.tool_event("start", tool_name, args={"argc": len(args), "keys": list(kwargs.keys())})
                try:
                    res = fn(*args, **kwargs)
                    telemetry.tool_event("end", tool_name, result=res, ok=True, started_ms=t0)
                    return res
                except Exception as e:
                    telemetry.tool_event("end", tool_name, ok=False, err=repr(e), started_ms=t0)
                    raise
            _register(tool_name, sync_wrapper)
            return sync_wrapper

    return decorator
