from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def _ts() -> str:
    return datetime.utcnow().isoformat(timespec="milliseconds") + "Z"


def _sha16(obj: Any) -> str:
    data = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
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
    """
    Shallow+recursive redaction of known-sensitive keys.
    Keeps shapes intact for debug, nukes obvious secrets.
    """
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


@dataclass
class RunHeader:
    kind: str
    session_id: str
    run_id: str
    started_at: str
    goal: str
    target_fqname: str | None


class RunLogger:
    """
    Simple JSONL run logger + Markdown summary.

    Directory layout:
      runs/
        simula/
          YYYY-MM-DD/
            <session_id>/
              <run_id>/
                run.jsonl
                summary.md
                meta.json
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

        self._summary_chunks: list[str] = []
        self._t0 = time.time()

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
            f"# Simula Codegen Run\n\n- **Session:** `{session_id}`\n- **Run:** `{run_id}`\n- **Goal:** {goal}\n- **Target:** `{target_fqname or '—'}`\n- **Started:** {header.started_at}\n"
        )

        # meta snapshot
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

    # --- core write helpers ---

    def _write_jsonl(self, obj: dict[str, Any]) -> None:
        obj = _redact(obj)
        with self.jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False))
            f.write("\n")

    def _append_summary(self, md: str) -> None:
        self._summary_chunks.append(md)

    # --- public event apis ---

    def log_synapse_selection(
        self, task_ctx: dict[str, Any], selection: dict[str, Any], error: str | None = None
    ) -> None:
        evt = {
            "kind": "synapse.select_or_plan",
            "t": _ts(),
            "task_ctx": task_ctx,
            "selection": selection if not error else None,
            "error": error,
        }
        self._write_jsonl(evt)
        if error:
            self._append_summary(f"\n## Strategy Selection (ERROR)\n```\n{error}\n```\n")
        else:
            arm_id = selection.get("champion_arm", {}).get("arm_id", "unknown")
            ep = selection.get("episode_id")
            self._append_summary(
                f"\n## Strategy Selection\n- **Episode:** `{ep}`\n- **Champion Arm:** `{arm_id}`\n"
            )

    def log_llm(
        self,
        *,
        phase: str,
        scope: str,
        agent: str,
        prompt_preview: str | None,
        prompt_struct: dict[str, Any] | None,
        completion_text: str | None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        evt = {
            "kind": "llm.call",
            "t": _ts(),
            "phase": phase,
            "scope": scope,
            "agent": agent,
            "prompt": {
                "preview": prompt_preview,
                "struct": prompt_struct,
            },
            "completion_text": completion_text,
            "extra": extra or {},
        }
        self._write_jsonl(evt)

        # summary (trim long)
        pv = (prompt_preview or "").strip()
        if len(pv) > 800:
            pv = pv[:800] + " …"
        ct = (completion_text or "").strip()
        if len(ct) > 800:
            ct = ct[:800] + " …"

        self._append_summary(
            f"\n### LLM · {phase} · `{scope}`\n<details><summary>Prompt (preview)</summary>\n\n```\n{pv}\n```\n</details>\n\n<details><summary>Completion</summary>\n\n```\n{ct}\n```\n</details>\n"
        )

    def log_tool_call(
        self, *, index: int, tool_name: str, parameters: dict[str, Any], outcome: dict[str, Any]
    ) -> None:
        evt = {
            "kind": "tool.call",
            "t": _ts(),
            "index": index,
            "tool_name": tool_name,
            "parameters": parameters,
            "outcome": outcome,
        }
        self._write_jsonl(evt)

        ok = (outcome.get("status", "") or "").lower()
        self._append_summary(
            f"\n### Tool {index}: `{tool_name}` — **{ok or 'unknown'}**\n<details><summary>Parameters</summary>\n\n```json\n{json.dumps(_redact(parameters), indent=2, ensure_ascii=False)}\n```\n</details>\n<details><summary>Outcome</summary>\n\n```json\n{json.dumps(_redact(outcome), indent=2, ensure_ascii=False)}\n```\n</details>\n"
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
    ) -> None:
        evt = {
            "kind": "http.call",
            "t": _ts(),
            "method": method,
            "url": url,
            "status": status,
            "request": request,
            "response": response,
            "error": error,
        }
        self._write_jsonl(evt)
        st = status if status is not None else "—"
        self._append_summary(f"\n### HTTP {method} {url} → {st}\n")

    def log_outcome(
        self, *, status: str, episode_id: str | None, utility_score: Any, notes: dict[str, Any]
    ) -> None:
        evt = {
            "kind": "run.outcome",
            "t": _ts(),
            "status": status,
            "episode_id": episode_id,
            "utility_score": utility_score,
            "notes": notes,
            "elapsed_s": round(time.time() - self._t0, 3),
        }
        self._write_jsonl(evt)
        self._append_summary(
            f"\n## Outcome\n- **Status:** **{status}**\n- **Episode:** `{episode_id or '—'}`\n- **Utility:** `{utility_score}`\n- **Elapsed:** `{evt['elapsed_s']}s`\n"
        )

    def save(self) -> None:
        with self.summary_path.open("w", encoding="utf-8") as f:
            f.write("\n".join(self._summary_chunks))

    # convenience: compute a stable id for any blob you want to cross-reference
    def stable_id(self, obj: Any) -> str:
        return _sha16(_redact(obj))
