# systems/simula/learning/jobs/validate_advice.py
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shlex
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from core.utils.neo.cypher_query import cypher_query

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_TIMEOUT_SECS = 120  # per validation rule
DEFAULT_CONCURRENCY = 4


# ──────────────────────────────────────────────────────────────────────────────
# Data
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class AdviceRecord:
    id: str
    level: int
    text: str
    validation: list[str]
    scope: list[str]


@dataclass
class RuleResult:
    advice_id: str
    rule: str
    ok: bool
    details: dict[str, Any]


# ──────────────────────────────────────────────────────────────────────────────
# Neo4j IO
# ──────────────────────────────────────────────────────────────────────────────


async def _load_advice_for_validation(
    advice_ids: list[str] | None = None,
    limit: int | None = None,
    rule_filter: str | None = None,
) -> list[AdviceRecord]:
    """
    Fetch advice nodes that have non-empty validation arrays.
    Optional: filter by advice_ids; optional rule substring filter.
    """
    params: dict[str, Any] = {}
    where = ["size(coalesce(a.validation, [])) > 0"]

    if advice_ids:
        where.append("a.id IN $ids")
        params["ids"] = advice_ids

    q = f"""
    MATCH (a:Advice)
    WHERE {' AND '.join(where)}
    RETURN a.id AS id, coalesce(a.level,1) AS level, coalesce(a.text,'') AS text,
           coalesce(a.validation,[]) AS validation, coalesce(a.scope,[]) AS scope
    ORDER BY a.level DESC, a.last_seen DESC
    """
    if limit and limit > 0:
        q += "\nLIMIT $limit"
        params["limit"] = int(limit)

    rows = await cypher_query(q, params) or []

    out: list[AdviceRecord] = []
    for r in rows:
        rules: list[str] = list(r.get("validation") or [])
        if rule_filter:
            rf = rule_filter.lower()
            rules = [x for x in rules if rf in x.lower()]
        if not rules:
            continue
        out.append(
            AdviceRecord(
                id=r["id"],
                level=int(r["level"]),
                text=r.get("text") or "",
                validation=rules,
                scope=list(r.get("scope") or []),
            ),
        )
    return out


async def _record_results(
    results: list[RuleResult],
    run_id: str | None = None,
    dry_run: bool = False,
) -> None:
    """
    Persist validation results to the graph. Creates a ValidationRun node and
    (Advice)-[:VALIDATED {rule, ok, details, at}]->(ValidationRun).
    """
    if dry_run or not results:
        return

    run_id = run_id or "vrun_" + os.urandom(6).hex()
    await cypher_query(
        """
        MERGE (r:ValidationRun {id:$run_id})
          ON CREATE SET r.at = timestamp()
        """,
        {"run_id": run_id},
    )

    # Batch insert relationships
    for res in results:
        await cypher_query(
            """
            MATCH (a:Advice {id:$aid})
            MATCH (r:ValidationRun {id:$run})
            MERGE (a)-[v:VALIDATED {rule:$rule}]->(r)
            SET v.ok = $ok,
                v.details = $details,
                v.at = timestamp()
            """,
            {
                "aid": res.advice_id,
                "run": run_id,
                "rule": res.rule,
                "ok": bool(res.ok),
                "details": json.dumps(res.details, ensure_ascii=False),
            },
        )


# ──────────────────────────────────────────────────────────────────────────────
# Rule execution
# Supported prefixes:
#   - "pytest::<selector>"   -> run pytest -k <selector>
#   - "cmd::<shell command>" -> run an arbitrary command
#   - "ast::<hint>"          -> placeholder for AST checks (Phase B/C)
#   - otherwise: treated as "cmd::<rule>"
# ──────────────────────────────────────────────────────────────────────────────


async def _run_subprocess(cmd: list[str], timeout: int) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        try:
            proc.kill()
        finally:
            return (124, "", f"Timed out after {timeout}s")
    rc = proc.returncode
    return rc, stdout_b.decode(errors="replace"), stderr_b.decode(errors="replace")


async def _exec_pytest(selector: str, timeout: int) -> RuleResult:
    cmd = ["pytest", "-q", "-k", selector]
    rc, out, err = await _run_subprocess(cmd, timeout)
    ok = rc == 0
    return RuleResult(
        advice_id="",  # filled by caller
        rule=f"pytest::{selector}",
        ok=ok,
        details={"rc": rc, "stdout": out[-4000:], "stderr": err[-4000:]},
    )


async def _exec_cmd(command: str, timeout: int) -> RuleResult:
    # Use shlex to split safely; if complex shell features are required, wrap in "bash -lc"
    parts = shlex.split(command)
    rc, out, err = await _run_subprocess(parts, timeout)
    ok = rc == 0
    return RuleResult(
        advice_id="",  # filled by caller
        rule=f"cmd::{command}",
        ok=ok,
        details={"rc": rc, "stdout": out[-4000:], "stderr": err[-4000:]},
    )


async def _exec_ast(hint: str) -> RuleResult:
    # Placeholder for repo-specific AST checks
    # Implement in Phase B/C; for now we mark as skipped with ok=True (neutral)
    return RuleResult(
        advice_id="",  # filled by caller
        rule=f"ast::{hint}",
        ok=True,
        details={"skipped": True, "reason": "AST validation not implemented yet"},
    )


async def _run_rule(advice_id: str, rule: str, timeout: int) -> RuleResult:
    if rule.startswith("pytest::"):
        rr = await _exec_pytest(rule.split("::", 1)[1], timeout)
    elif rule.startswith("cmd::"):
        rr = await _exec_cmd(rule.split("::", 1)[1], timeout)
    elif rule.startswith("ast::"):
        rr = await _exec_ast(rule.split("::", 1)[1])
    else:
        # default to cmd
        rr = await _exec_cmd(rule, timeout)
    rr.advice_id = advice_id
    return rr


# ──────────────────────────────────────────────────────────────────────────────
# Orchestration
# ──────────────────────────────────────────────────────────────────────────────


async def _validate_advice(
    records: Iterable[AdviceRecord],
    *,
    timeout: int,
    concurrency: int,
) -> list[RuleResult]:
    sem = asyncio.Semaphore(max(1, concurrency))
    results: list[RuleResult] = []

    async def _run_one(advice: AdviceRecord) -> None:
        for rule in advice.validation:
            async with sem:
                try:
                    rr = await _run_rule(advice.id, rule, timeout)
                    results.append(rr)
                    status = "OK" if rr.ok else "FAIL"
                    log.info("[validate_advice] %s %s :: %s", status, advice.id, rule)
                except Exception as e:
                    log.exception("[validate_advice] rule crashed %s :: %s", advice.id, rule)
                    results.append(
                        RuleResult(
                            advice_id=advice.id,
                            rule=rule,
                            ok=False,
                            details={"exception": repr(e)},
                        ),
                    )

    await asyncio.gather(*[asyncio.create_task(_run_one(rec)) for rec in records])
    return results


# ──────────────────────────────────────────────────────────────────────────────
# CLI / Entry
# ──────────────────────────────────────────────────────────────────────────────


async def run(
    *,
    advice_ids: list[str] | None = None,
    limit: int | None = None,
    rule_filter: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECS,
    concurrency: int = DEFAULT_CONCURRENCY,
    dry_run: bool = False,
    run_id: str | None = None,
) -> None:
    """Validate advice using its 'validation' rules and persist results."""
    records = await _load_advice_for_validation(advice_ids, limit, rule_filter)
    if not records:
        log.info("[AdviceJob] No advice found with validation rules.")
        return

    log.info(
        "[AdviceJob] Validating %d advice nodes (timeout=%ss, concurrency=%d, dry_run=%s)",
        len(records),
        timeout,
        concurrency,
        dry_run,
    )
    results = await _validate_advice(records, timeout=timeout, concurrency=concurrency)
    ok_count = sum(1 for r in results if r.ok)
    fail_count = len(results) - ok_count
    log.info("[AdviceJob] Validation complete. ok=%d fail=%d", ok_count, fail_count)

    await _record_results(results, run_id=run_id, dry_run=dry_run)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate Advice against its 'validation' rules.")
    p.add_argument(
        "--advice-id",
        dest="advice_ids",
        action="append",
        help="Advice ID to validate (can be provided multiple times). If omitted, validates all with rules.",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of advice to validate (0 = no limit).",
    )
    p.add_argument(
        "--rule-filter",
        help="Substring filter to select only rules that contain this string (case-insensitive).",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECS,
        help=f"Per-rule timeout in seconds (default: {DEFAULT_TIMEOUT_SECS}).",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Max concurrent rule executions (default: {DEFAULT_CONCURRENCY}).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write results back to Neo4j.",
    )
    p.add_argument(
        "--run-id",
        help="Optional ValidationRun id to group results under; autogenerated if omitted.",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        help="Logging level (default: INFO).",
    )
    return p.parse_args()


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    args = _parse_args()
    _configure_logging(args.log_level)
    asyncio.run(
        run(
            advice_ids=args.advice_ids,
            limit=(args.limit if args.limit and args.limit > 0 else None),
            rule_filter=args.rule_filter,
            timeout=args.timeout,
            concurrency=args.concurrency,
            dry_run=args.dry_run,
            run_id=args.run_id,
        ),
    )


if __name__ == "__main__":
    main()
