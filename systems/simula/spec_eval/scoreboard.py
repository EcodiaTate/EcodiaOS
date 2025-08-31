# systems/simula/spec_eval/scoreboard.py
from __future__ import annotations

import json
import statistics as stats
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from systems.simula.config import settings

SPEC_EVAL_DIRNAME = "spec_eval"  # under artifacts_root


@dataclass
class RunSummary:
    run_id: str
    path: str
    num_candidates: int
    best_score: float
    avg_score: float
    median_score: float
    delta_cov_pct: float | None = None
    created_at: str | None = None
    meta: dict[str, Any] = None  # loose bag for anything else


def _iter_json(dirpath: Path):
    if not dirpath.exists():
        return
    for p in dirpath.rglob("*.json"):
        # ignore huge blobs; scoreboard is metadata-focused
        if p.stat().st_size > 8 * 1024 * 1024:
            continue
        yield p


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _extract_scores(payload: dict[str, Any]) -> list[float]:
    # Flexible: accept several shapes
    scores: list[float] = []
    # common shapes:
    # - {"candidates":[{"score": 0.91}, ...]}
    # - {"summary":{"scores":[...]}}
    # - {"results":[{"metrics":{"score":...}}, ...]}
    if isinstance(payload.get("candidates"), list):
        for c in payload["candidates"]:
            if isinstance(c, dict):
                if "score" in c:
                    scores.append(_safe_float(c["score"]))
                elif isinstance(c.get("metrics"), dict) and "score" in c["metrics"]:
                    scores.append(_safe_float(c["metrics"]["score"]))
    if not scores and isinstance(payload.get("summary"), dict):
        s = payload["summary"]
        if isinstance(s.get("scores"), list):
            scores = [_safe_float(v) for v in s["scores"]]
    if not scores and isinstance(payload.get("results"), list):
        for r in payload["results"]:
            m = r.get("metrics") if isinstance(r, dict) else None
            if isinstance(m, dict) and "score" in m:
                scores.append(_safe_float(m["score"]))
    return scores


def _extract_cov(payload: dict[str, Any]) -> float | None:
    # Try to find an evidence-like delta coverage fig
    # e.g. {"coverage_delta":{"pct_changed_covered": 72.5}}
    ev = payload.get("coverage_delta") or (payload.get("evidence") or {}).get("coverage_delta")
    if isinstance(ev, dict) and "pct_changed_covered" in ev:
        try:
            return float(ev["pct_changed_covered"])
        except Exception:
            return None
    return None


def _extract_created(payload: dict[str, Any]) -> str | None:
    for k in ("created_at", "timestamp", "ts"):
        if k in payload:
            v = payload.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def load_scoreboard() -> dict[str, Any]:
    root = Path(settings.artifacts_root or (settings.repo_root or ".")) / SPEC_EVAL_DIRNAME
    runs: list[RunSummary] = []
    for fp in _iter_json(root):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        scores = _extract_scores(data)
        if not scores:
            continue
        run_id = data.get("run_id") or data.get("id") or fp.stem
        cov = _extract_cov(data)
        created = _extract_created(data)
        rs = RunSummary(
            run_id=str(run_id),
            path=str(fp.relative_to(Path(settings.repo_root or ".").resolve())),
            num_candidates=len(scores),
            best_score=max(scores),
            avg_score=sum(scores) / len(scores),
            median_score=stats.median(scores),
            delta_cov_pct=cov,
            created_at=created,
            meta={"title": data.get("title"), "notes": data.get("notes")},
        )
        runs.append(rs)

    runs.sort(key=lambda r: (r.best_score, r.avg_score), reverse=True)
    return {
        "count": len(runs),
        "runs": [asdict(r) for r in runs[:200]],
        "artifacts_root": str(Path(settings.artifacts_root or ".").resolve()),
        "dir": SPEC_EVAL_DIRNAME,
    }
