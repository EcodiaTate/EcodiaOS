# systems/simula/learning/jobs/merge_t2_to_t3.py
from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Iterable
from typing import List, Optional

from systems.simula.learning.advice_engine import AdviceEngine

log = logging.getLogger(__name__)


async def _merge_one(engine: AdviceEngine, t2_id: str) -> str | None:
    try:
        t3 = await engine.merge_t2_to_t3(t2_id)
        if t3:
            log.info("[AdviceJob] Merged T3 %s from T2 seed %s", t3, t2_id)
        else:
            log.info("[AdviceJob] Not enough support to promote T2 %s -> T3", t2_id)
        return t3
    except Exception as e:
        log.exception("[AdviceJob] merge_t2_to_t3 failed for %s: %r", t2_id, e)
        return None


async def run(t2_ids: Iterable[str], *, concurrency: int = 4) -> list[str]:
    """
    Merge clusters of T2 advice documents into T3 architectural advice.

    Args:
        t2_ids: Iterable of T2 Advice node IDs to attempt promotion from.
        concurrency: Max number of seeds to process concurrently.

    Returns:
        List of created T3 advice IDs.
    """
    engine = AdviceEngine()
    sem = asyncio.Semaphore(max(1, concurrency))

    async def _guarded(aid: str) -> str | None:
        async with sem:
            return await _merge_one(engine, aid)

    tasks = [asyncio.create_task(_guarded(a)) for a in t2_ids]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return [r for r in results if r]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Merge T2 advice into T3 architectural advice.")
    p.add_argument(
        "--t2-id",
        dest="t2_ids",
        action="append",
        required=True,
        help="T2 Advice ID to use as a seed (can be passed multiple times).",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Max number of seeds to process concurrently (default: 4).",
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
    created: list[str] = asyncio.run(run(args.t2_ids, concurrency=args.concurrency))
    if created:
        log.info("[AdviceJob] Created %d T3 advices: %s", len(created), ", ".join(created))
    else:
        log.info("[AdviceJob] No T3 advice created.")


if __name__ == "__main__":
    main()
