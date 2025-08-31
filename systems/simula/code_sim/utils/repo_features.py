from __future__ import annotations

import ast
import subprocess
from pathlib import Path

REPO = Path("/app")


def file_degree(rel: str, max_files: int = 20000) -> int:
    """
    Rough import-degree: count files that import this module or are imported by it.
    """
    rel_p = REPO / rel
    if not rel_p.exists() or not rel.endswith(".py"):
        return 0
    name = rel[:-3].replace("/", ".")
    deg = 0
    scanned = 0
    for p in REPO.rglob("*.py"):
        scanned += 1
        if scanned > max_files:
            break
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for a in n.names:
                    if a.name == name:
                        deg += 1
                        break
            elif isinstance(n, ast.ImportFrom) and n.module:
                if n.module == name or n.module.startswith(name + "."):
                    deg += 1
                    break
    return deg


def file_churn(rel: str, days: int = 180) -> int:
    """Number of commits touching this file in last N days."""
    try:
        out = subprocess.run(
            ["git", "log", f"--since={days}.days", "--pretty=oneline", "--", rel],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if out.returncode != 0:
            return 0
        return len([l for l in out.stdout.splitlines() if l.strip()])
    except Exception:
        return 0


def plan_entropy(plan: list[dict]) -> float:
    """Spread of plan across dirs: simple entropy proxy in [0,1]."""
    from collections import Counter

    if not plan:
        return 0.0
    dirs = [(p.get("path") or "").split("/", 1)[0] for p in plan if p.get("path")]
    c = Counter(dirs)
    total = sum(c.values())
    import math

    H = -sum((v / total) * math.log2(v / total) for v in c.values() if v > 0)
    # normalize by max entropy log2(k)
    k = len(c)
    maxH = math.log2(k) if k > 1 else 1.0
    return float(min(1.0, H / (maxH or 1.0)))


def features_for_file(job_meta: dict, file_plan: dict) -> dict:
    rel = file_plan.get("path", "")
    return {
        "degree": file_degree(rel),
        "churn": file_churn(rel),
        "plan_entropy": plan_entropy(job_meta.get("plan", [])),
    }
