from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# -------------------------
# Small utils
# -------------------------


def _ts() -> str:
    return datetime.utcnow().isoformat(timespec="milliseconds") + "Z"


def _sha16(obj: Any) -> str:
    try:
        data = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    except Exception:
        data = repr(obj).encode("utf-8")
    return hashlib.sha1(data).hexdigest()[:16]


SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "x-api-key",
    "authorization",
    "auth",
    "password",
    "token",
    "bearer",
    "secret",
}


def _redact(obj: Any) -> Any:
    """Recursive redaction of common secret-shaped keys, preserving structure."""
    try:
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                lk = k.lower()
                if lk in SENSITIVE_KEYS or lk.endswith("_key") or lk.endswith("_token"):
                    out[k] = "REDACTED"
                else:
                    out[k] = _redact(v)
            return out
        if isinstance(obj, list):
            return [_redact(x) for x in obj]
        return obj
    except Exception:
        return obj


def _trim_text(txt: str | None, max_chars: int) -> tuple[str, int]:
    if not txt:
        return "", 0
    if len(txt) <= max_chars:
        return txt, 0
    overflow = len(txt) - max_chars
    return txt[:max_chars] + f" … (+{overflow} chars)", overflow


def _sizeof_json(obj: Any) -> int:
    try:
        return len(json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))
    except Exception:
        return len(repr(obj).encode("utf-8"))


# -------------------------
# Config (env-tunable)
# -------------------------

MAX_PREVIEW_CHARS = int(os.getenv("SIMULA_RUN_MAX_PREVIEW_CHARS", "600"))
MAX_JSON_BYTES = int(os.getenv("SIMULA_RUN_MAX_JSON_BYTES", "24576"))  # ~24 KB
DEDUP_WINDOW_S = float(
    os.getenv("SIMULA_RUN_DEDUP_WINDOW_S", "3.0"),
)  # drop near-duplicate spam within this window
TEE_STDOUT = os.getenv("SIMULA_RUN_TEE_STDOUT", "0") == "1"  # also print compact one-liners

# -------------------------
# Header
# -------------------------


@dataclass
class RunHeader:
    kind: str
    session_id: str
    run_id: str
    started_at: str
    goal: str
    target_fqname: str | None


# -------------------------
# RunLogger
# -------------------------


class RunLogger:
    """
    Concise JSONL run logger + skimmable Markdown summary.

    Layout:
      runs/simula/YYYY-MM-DD/<session_id>/<run_id>/{run.jsonl, summary.md, meta.json, compact.json}
    """

    def __init__(self, session_id: str, goal: str, target_fqname: str | None = None):
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        root = (
            Path(os.getenv("SIMULA_RUNS_DIR", "runs")) / "simula" / date_str / session_id / run_id
        )
        root.mkdir(parents=True, exist_ok=True)

        self.session_id = session_id
        self.goal = goal
        self.target_fqname = target_fqname
        self.run_id = run_id
        self.root = root
        self.jsonl_path = root / "run.jsonl"
        self.summary_path = root / "summary.md"
        self.meta_path = root / "meta.json"
        self.compact_path = root / "compact.json"

        self._summary_chunks: list[str] = []
        self._t0 = time.time()
        self._event_seq = 0
        self._tags: dict[str, Any] = {}

        # stats/rollups
        self._roll = {
            "llm_calls": 0,
            "tools": {},
            "http": {"count": 0, "by_status": {}, "last_error": None},
            "errors": {},  # message -> count
        }

        # dedup suppression memory
        self._last_fingerprint: dict[str, tuple[str, float]] = {}  # key -> (fingerprint, t)

        header = RunHeader(
            kind="run_header",
            session_id=session_id,
            run_id=run_id,
            started_at=_ts(),
            goal=goal,
            target_fqname=target_fqname,
        )
        self._write_jsonl(asdict(header))
        self._summary_chunks.append(
            f"# Simula Codegen Run\n"
            f"- **Session:** `{session_id}`\n"
            f"- **Run:** `{run_id}`\n"
            f"- **Goal:** {goal}\n"
            f"- **Target:** `{target_fqname or '—'}`\n"
            f"- **Started:** {header.started_at}\n",
        )

        # meta snapshot (redacted)
        meta = {
            "env": {
                k: v
                for k, v in os.environ.items()
                if k.startswith(("APP_", "SIMULA_", "SYNAPSE_", "OPENAI_", "GOOGLE_", "GEMINI_"))
            },
            "cwd": os.getcwd(),
        }
        with self.meta_path.open("w", encoding="utf-8") as f:
            json.dump(_redact(meta), f, indent=2, ensure_ascii=False)

    # -------------------------
    # core write + helpers
    # -------------------------

    def _write_jsonl(self, obj: dict[str, Any]) -> None:
        self._event_seq += 1
        obj = dict(obj)  # shallow copy
        obj["seq"] = self._event_seq
        obj = _redact(obj)

        # size guard
        if _sizeof_json(obj) > MAX_JSON_BYTES:
            obj = {"kind": "log_dropped_too_large", "seq": self._event_seq, "t": _ts()}

        with self.jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False))
            f.write("\n")

        if TEE_STDOUT:
            # one-liner tee for quick tail
            kind = obj.get("kind", "evt")
            msg = obj.get("msg") or obj.get("error") or ""
            print(f"[RUN {self.run_id}] {kind}#{obj['seq']} {msg}"[:180])

    def _append_summary(self, md: str) -> None:
        self._summary_chunks.append(md)

    def _dedup_ok(self, key: str, payload: Any) -> bool:
        """Return True if we should log, False if suppressed as near-duplicate."""
        now = time.time()
        fp = _sha16(payload)
        last = self._last_fingerprint.get(key)
        if last and last[0] == fp and (now - last[1]) <= DEDUP_WINDOW_S:
            return False
        self._last_fingerprint[key] = (fp, now)
        return True

    # -------------------------
    # public: tags & phases
    # -------------------------

    def set_tag(self, key: str, value: Any) -> None:
        self._tags[key] = value

    def phase(self, name: str, status: str, **meta: Any) -> None:
        """Mark phase transitions with timing baked in."""
        evt = {
            "kind": "phase",
            "t": _ts(),
            "name": name,
            "status": status,
            **meta,
            "elapsed_s": round(time.time() - self._t0, 3),
        }
        self._write_jsonl(evt)
        if status in ("start",):
            self._append_summary(f"\n## Phase: **{name}** (start)\n")
        elif status in ("ok", "error", "end"):
            note = meta.get("note") or ""
            self._append_summary(
                f"\n## Phase: **{name}** — {status.upper()} {('· ' + note) if note else ''}\n",
            )

    @contextmanager
    def step(self, name: str, **meta: Any) -> Generator[None, None, None]:
        """Context manager to time a step; emits start/end events."""
        t0 = time.time()
        self._write_jsonl({"kind": "step", "t": _ts(), "name": name, "status": "start", **meta})
        try:
            yield
            dur = round(time.time() - t0, 3)
            self._write_jsonl(
                {"kind": "step", "t": _ts(), "name": name, "status": "ok", "elapsed_s": dur},
            )
        except Exception as e:
            dur = round(time.time() - t0, 3)
            self._write_jsonl(
                {
                    "kind": "step",
                    "t": _ts(),
                    "name": name,
                    "status": "error",
                    "elapsed_s": dur,
                    "error": repr(e),
                },
            )
            # bubble up
            raise

    # -------------------------
    # existing public APIs (kept), now more concise
    # -------------------------

    def log_synapse_selection(
        self,
        task_ctx: dict[str, Any],
        selection: dict[str, Any],
        error: str | None = None,
    ) -> None:
        # dedup noisy identical task_ctx/selection bursts
        key = "synapse.select_or_plan"
        if not self._dedup_ok(key, {"task_ctx": task_ctx, "selection": selection, "error": error}):
            return

        evt = {
            "kind": key,
            "t": _ts(),
            "task_ctx": task_ctx,
            "selection": selection if not error else None,
            "error": error,
        }
        self._write_jsonl(evt)

        if error:
            self._roll["errors"][error] = self._roll["errors"].get(error, 0) + 1
            self._append_summary(f"\n## Strategy Selection (ERROR)\n```\n{error}\n```\n")
        else:
            arm_id = selection.get("champion_arm", {}).get("arm_id", "unknown")
            ep = selection.get("episode_id")
            self._append_summary(
                f"\n## Strategy Selection\n- **Episode:** `{ep}`\n- **Champion Arm:** `{arm_id}`\n",
            )

    def log_llm(
        self,
        *,
        phase: str,
        scope: str,
        agent: str,
        prompt_preview: str | None = None,
        prompt_struct: dict[str, Any] | None = None,
        completion_text: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        # compact, trimmed storage
        pp, _ = _trim_text((prompt_preview or "").strip(), MAX_PREVIEW_CHARS)
        ct, _ = _trim_text((completion_text or "").strip(), MAX_PREVIEW_CHARS)

        payload = {
            "kind": "llm.call",
            "t": _ts(),
            "phase": phase,
            "scope": scope,
            "agent": agent,
            "prompt": {"preview": pp, "struct": None},  # omit giant structs by default
            "completion_text": ct,
            "extra": extra or {},
        }

        # Only keep struct if small enough to be useful.
        if prompt_struct and _sizeof_json(prompt_struct) <= MAX_JSON_BYTES // 4:
            payload["prompt"]["struct"] = _redact(prompt_struct)

        # dedup near-identical calls within window
        if not self._dedup_ok(f"llm:{scope}:{phase}", payload):
            return

        self._write_jsonl(payload)
        self._roll["llm_calls"] += 1

        self._append_summary(
            f"\n### LLM · {phase} · `{scope}` · *{agent}*\n"
            f"<details><summary>Prompt (preview)</summary>\n\n```\n{pp}\n```\n</details>\n"
            f"<details><summary>Completion</summary>\n\n```\n{ct}\n```\n</details>\n",
        )

    def log_tool_call(
        self,
        *,
        index: int,
        tool_name: str,
        parameters: dict[str, Any],
        outcome: dict[str, Any],
    ) -> None:
        status = (outcome.get("status", "") or "").lower()
        concise_params = (
            parameters if _sizeof_json(parameters) <= MAX_JSON_BYTES // 4 else {"_": "truncated"}
        )
        concise_outcome = (
            outcome if _sizeof_json(outcome) <= MAX_JSON_BYTES // 2 else {"_": "truncated"}
        )

        evt = {
            "kind": "tool.call",
            "t": _ts(),
            "index": index,
            "tool_name": tool_name,
            "status": status or "unknown",
            "parameters": _redact(concise_params),
            "outcome": _redact(concise_outcome),
        }
        self._write_jsonl(evt)

        self._roll["tools"][tool_name] = self._roll["tools"].get(tool_name, 0) + 1

        self._append_summary(
            f"\n### Tool {index}: `{tool_name}` — **{status or 'unknown'}**\n"
            f"<details><summary>Parameters</summary>\n\n```json\n{json.dumps(_redact(concise_params), indent=2, ensure_ascii=False)}\n```\n</details>\n"
            f"<details><summary>Outcome</summary>\n\n```json\n{json.dumps(_redact(concise_outcome), indent=2, ensure_ascii=False)}\n```\n</details>\n",
        )

    def log_http(
        self,
        *,
        method: str,
        url: str,
        status: int | None,
        request: dict[str, Any] | None = None,
        response: dict[str, Any] | None = None,
        error: str | None = None,
        duration_ms: float | None = None,
    ) -> None:
        concise_req = (
            request if _sizeof_json(request) <= MAX_JSON_BYTES // 4 else {"_": "truncated"}
        )
        concise_res = (
            response if _sizeof_json(response) <= MAX_JSON_BYTES // 2 else {"_": "truncated"}
        )

        evt = {
            "kind": "http.call",
            "t": _ts(),
            "method": method,
            "url": url,
            "status": status,
            "duration_ms": duration_ms,
            "request": _redact(concise_req) if concise_req else None,
            "response": _redact(concise_res) if concise_res else None,
            "error": error,
        }

        # dedup identical method+url+status bursts
        if not self._dedup_ok(f"http:{method}:{url}:{status}", evt):
            return

        self._write_jsonl(evt)
        self._roll["http"]["count"] += 1
        code = str(status) if status is not None else "—"
        self._roll["http"]["by_status"][code] = self._roll["http"]["by_status"].get(code, 0) + 1
        if error:
            self._roll["errors"][error] = self._roll["errors"].get(error, 0) + 1
            self._roll["http"]["last_error"] = error

        st = status if status is not None else "—"
        self._append_summary(
            f"\n### HTTP {method} {url} → {st}{(' · ' + error) if error else ''}\n",
        )

    def log_outcome(
        self,
        *,
        status: str,
        episode_id: str | None,
        utility_score: Any,
        notes: dict[str, Any],
    ) -> None:
        evt = {
            "kind": "run.outcome",
            "t": _ts(),
            "status": status,
            "episode_id": episode_id,
            "utility_score": utility_score,
            "notes": notes,
            "elapsed_s": round(time.time() - self._t0, 3),
            "tags": dict(self._tags),
        }
        self._write_jsonl(evt)

        self._append_summary(
            f"\n## Outcome\n"
            f"- **Status:** **{status}**\n"
            f"- **Episode:** `{episode_id or '—'}`\n"
            f"- **Utility:** `{utility_score}`\n"
            f"- **Elapsed:** `{evt['elapsed_s']}s`\n",
        )

        # also drop a compact roll-up for sharing
        compact = {
            "session_id": self.session_id,
            "run_id": self.run_id,
            "goal": self.goal,
            "target": self.target_fqname,
            "status": status,
            "utility_score": utility_score,
            "elapsed_s": evt["elapsed_s"],
            "llm_calls": self._roll["llm_calls"],
            "tools_used": self._roll["tools"],
            "http": self._roll["http"],
            "top_errors": sorted(self._roll["errors"].items(), key=lambda kv: kv[1], reverse=True)[
                :5
            ],
            "tags": dict(self._tags),
        }
        with self.compact_path.open("w", encoding="utf-8") as f:
            json.dump(compact, f, indent=2, ensure_ascii=False)

    def log_note(self, msg: str, **kv: Any) -> None:
        """Freeform concise note."""
        evt = {"kind": "note", "t": _ts(), "msg": msg, **kv}
        if self._dedup_ok("note:" + msg[:80], evt):
            self._write_jsonl(evt)

    def save(self) -> None:
        # Prepend a tiny roll-up section to the summary
        http_counts = ", ".join(
            f"{k}:{v}" for k, v in sorted(self._roll["http"]["by_status"].items())
        )
        errs = self._roll["errors"]
        top_errs = (
            "\n".join(
                f"  - {e} ×{c}"
                for e, c in sorted(errs.items(), key=lambda kv: kv[1], reverse=True)[:5]
            )
            or "  - None"
        )
        tools = (
            ", ".join(
                f"{k}×{v}"
                for k, v in sorted(self._roll["tools"].items(), key=lambda kv: (-kv[1], kv[0]))
            )
            or "—"
        )
        header = (
            "\n---\n"
            f"**Roll-up:** LLM calls: `{self._roll['llm_calls']}` · HTTP: `{self._roll['http']['count']}` ({http_counts or '—'}) · Tools: {tools}\n\n"
            f"**Top Errors:**\n{top_errs}\n"
        )
        body = "\n".join(self._summary_chunks)
        with self.summary_path.open("w", encoding="utf-8") as f:
            f.write(header + "\n" + body)

    # convenience: stable id for cross-referencing any blob
    def stable_id(self, obj: Any) -> str:
        return _sha16(_redact(obj))
