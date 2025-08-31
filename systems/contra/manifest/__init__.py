from __future__ import annotations

"""
Contra init/daemon utilities (overlay-aware, Simula-compatible).

Drop this file into your repo at: systems/contra/init.py

Exports:
  - ensure_manifest(system: str, code_root: str = "./") -> dict
      Build and return a deterministic manifest (dict) for a system.
      Safe to call from app.py startup to "prime" context.

  - start_contra_daemon() -> None | asyncio.Task
      (Optional) Launch a leader-gated background loop that runs Contra checks and,
      on failures, assembles a GCB and submits to SIMULA_JOBS_CODEGEN.

Env knobs (all optional):
  CONTRA_ENABLED=1
  CONTRA_INTERVAL_SEC=120
  CONTRA_MAX_PAIRS=200
  CONTRA_SYSTEMS="synapse,simula,unity,atune,axon,evo,equor,nova"
  CONTRA_CODE_ROOT="./"
  CONTRA_LEADER=1
  CONTRA_AUTOFIX=1
  CONTRA_SIMULA=1
  CONTRA_BUDGET_MS=2000
"""

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional

from systems.contra.manifest.engine import run_checks
from systems.contra.manifest.selector import select_pairs
from systems.qora.gcb.builder import build_gcb

# --- Qora/Contra core imports (local, no HTTP) ---
from systems.qora.manifest.builder import build_manifest

# --- Overlay + HTTP (EcodiaOS) ---
try:
    from core.utils.net_api import ENDPOINTS, get_http_client  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    ENDPOINTS = None  # type: ignore[assignment]
    get_http_client = None  # type: ignore[assignment]

# ------------------------------- Config -------------------------------


@dataclass(frozen=True)
class ContraConfig:
    enabled: bool = os.getenv("CONTRA_ENABLED", "1") == "1"
    interval_sec: int = int(os.getenv("CONTRA_INTERVAL_SEC", "120"))
    max_pairs: int = int(os.getenv("CONTRA_MAX_PAIRS", "200"))
    systems: list[str] = tuple(
        s.strip()
        for s in os.getenv(
            "CONTRA_SYSTEMS",
            "synapse,simula,unity,atune,axon,evo,equor,nova",
        ).split(",")
        if s.strip()
    )
    code_root: str = os.getenv("CONTRA_CODE_ROOT", "./")
    leader: bool = os.getenv("CONTRA_LEADER", "1") == "1"
    autofix: bool = os.getenv("CONTRA_AUTOFIX", "1") == "1"
    simula: bool = os.getenv("CONTRA_SIMULA", "1") == "1"
    budget_ms: int = int(os.getenv("CONTRA_BUDGET_MS", "2000"))


_CFG = ContraConfig()

# --------------------------- Public API ---------------------------


async def ensure_manifest(system: str, code_root: str = "./") -> dict:
    """
    Build and return the deterministic manifest for `system`.
    Intended for app startup priming.

    Usage (in app.py):
        from systems.contra.init import ensure_manifest
        ensure_manifest("simula", code_root="D:/EcodiaOS")
    """
    m = await build_manifest(system, code_root)
    return m.model_dump()


# --------------------- Simula bridge (overlay-aware) ---------------------

_SENTINEL = "EOS::GCB::v1"


def _encode_gcb_spec(gcb: dict, *, summary: str | None = None) -> str:
    """
    Encode a Golden Context Bundle (GCB) into Simula's `spec` string.
    First line = human summary, then sentinel + compact JSON. The Simula
    agent can detect the sentinel and parse deterministically.
    """
    compact = json.dumps(gcb, separators=(",", ":"), ensure_ascii=False)
    head = (
        summary
        or f"GCB for system={gcb.get('scope', {}).get('system', '?')} targets={len(gcb.get('targets', []))}"
    )
    return f"{head}\n{_SENTINEL}\n{compact}"


def _targets_to_hints(targets: list[dict]) -> list[dict]:
    """
    Map generic targets to Simula TargetHint:
      { "path": <repo-relative>, "kind": "auto"|"file"|"module"|"test"|"config", "signature"?: str }
    Accepts inputs with 'file' or 'path'.
    """
    hints: list[dict] = []
    for t in targets or []:
        path = t.get("path") or t.get("file") or ""
        if not path:
            continue
        hint = {"path": path, "kind": t.get("kind", "auto")}
        sig = t.get("signature")
        if sig:
            hint["signature"] = sig
        hints.append(hint)
    return hints


async def _submit_simula_jobs_codegen(
    decision_id: str,
    *,
    gcb: dict,
    budget_ms: int | None = None,
) -> dict:
    """
    POST to SIMULA_JOBS_CODEGEN via overlay:
      Body must be: { "spec": <str>, "targets": [TargetHint, ...] }
    Headers: x-decision-id (+ x-budget-ms if provided)
    """
    if ENDPOINTS is None or get_http_client is None:
        raise RuntimeError("Overlay client unavailable (ENDPOINTS/get_http_client not imported)")

    path = ENDPOINTS.path("SIMULA_JOBS_CODEGEN")  # type: ignore[attr-defined]
    spec_str = _encode_gcb_spec(gcb, summary=f"[{decision_id}] contra repair/codegen")
    target_hints = _targets_to_hints(gcb.get("targets", []))

    async with get_http_client() as client:  # type: ignore[func-returns-value]
        headers = {"x-decision-id": decision_id}
        if budget_ms is not None:
            headers["x-budget-ms"] = str(int(budget_ms))
        t0 = time.perf_counter()
        resp = await client.post(
            path,
            json={"spec": spec_str, "targets": target_hints},
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        data["_roundtrip_ms"] = int((time.perf_counter() - t0) * 1000)
        return data


# -------------------------- Daemon Helpers --------------------------


async def _contra_cycle_once(cfg: ContraConfig = _CFG) -> None:
    """
    One full pass over configured systems:
      - Build manifest
      - Run deterministic checks
      - If failures exist → build GCB and submit to Simula
    """
    for system in cfg.systems:
        try:
            manifest = build_manifest(system, cfg.code_root)
            diagnostics = run_checks(manifest)
            has_fail = any(d.status == "fail" for d in diagnostics)

            # Selection (import-bound/centrality/random) — useful for logging/telemetry if desired
            _ = select_pairs(manifest, cfg.max_pairs)

            if cfg.simula and has_fail:
                decision_id = str(uuid.uuid4())
                targets = [
                    {"path": "<contra-selects>", "kind": "auto", "why": "contra diagnostics fail"},
                ]
                gcb = build_gcb(decision_id, {"system": system}, targets, manifest)
                await _submit_simula_jobs_codegen(
                    decision_id,
                    gcb=gcb.model_dump(),
                    budget_ms=cfg.budget_ms,
                )
        except Exception as e:  # pragma: no cover
            # Fail gracefully; daemon keeps going to next system
            print(f"[contra-cycle] system={system} error={e!r}")


async def _contra_loop(cfg: ContraConfig = _CFG) -> None:
    """
    Cooperative background loop. Leader-gated. Safe under multi-worker if only one sets CONTRA_LEADER=1.
    """
    try:
        while cfg.enabled and cfg.leader:
            await _contra_cycle_once(cfg)
            await asyncio.sleep(cfg.interval_sec)
    except asyncio.CancelledError:
        pass
    except Exception as e:  # pragma: no cover
        print(f"[contra-daemon] stopped due to error: {e!r}")


def start_contra_daemon(cfg: ContraConfig | None = None):
    """
    Optionally start the Contra daemon.
    Return the created asyncio.Task, or None if disabled/not leader.

    Usage (in app.py):
        from systems.contra.init import start_contra_daemon
        @app.on_event("startup")
        async def _start():
            start_contra_daemon()
    """
    cfg = cfg or _CFG
    if not (cfg.enabled and cfg.leader):
        return None
    task = asyncio.create_task(_contra_loop(cfg))
    return task


__all__ = ["ensure_manifest", "start_contra_daemon", "ContraConfig"]
