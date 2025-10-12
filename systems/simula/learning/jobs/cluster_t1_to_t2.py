# systems/simula/learning/jobs/synthesize_t2.py
from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Iterable
from typing import List, Optional

from systems.simula.learning.advice_engine import AdviceEngine

log = logging.getLogger(__name__)


async def _synthesize_one(engine: AdviceEngine, advice_id: str) -> str | None:
    try:
        t2 = await engine.synthesize_t2(advice_id)
        if t2:
            log.info("[AdviceJob] Synthesized T2 %s from seed %s", t2, advice_id)
        else:
            log.info("[AdviceJob] Not enough support to promote seed %s -> T2", advice_id)
        return t2
    except Exception as e:
        log.exception("[AdviceJob] synth_t2 failed for %s: %r", advice_id, e)
        return None


async def run(seed_ids: Iterable[str], *, concurrency: int = 4) -> list[str]:
    """
    Promote clusters of T1 incidents to T2 advice documents.

    Args:
        seed_ids: Iterable of T1 Advice node IDs to attempt promotion from.
        concurrency: Max number of seeds to process concurrently.

    Returns:
        List of created T2 advice IDs.
    """
    engine = AdviceEngine()
    sem = asyncio.Semaphore(max(1, concurrency))

    async def _guarded(aid: str) -> str | None:
        async with sem:
            return await _synthesize_one(engine, aid)

    tasks = [asyncio.create_task(_guarded(a)) for a in seed_ids]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return [r for r in results if r]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Synthesize T2 advice from T1 seeds.")
    p.add_argument(
        "--seed-id",
        dest="seed_ids",
        action="append",
        required=True,
        help="T1 Advice ID to use as a seed (can be passed multiple times).",
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
    created: list[str] = asyncio.run(run(args.seed_ids, concurrency=args.concurrency))
    if created:
        log.info("[AdviceJob] Created %d T2 advices: %s", len(created), ", ".join(created))
    else:
        log.info("[AdviceJob] No T2 advice created.")


if __name__ == "__main__":
    main()
