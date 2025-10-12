# systems/simula/learning/jobs/decay.py
from __future__ import annotations

import argparse
import asyncio
import logging

from systems.simula.learning.advice_engine import AdviceEngine

log = logging.getLogger(__name__)


async def run() -> None:
    """Apply time-based decay to advice weights."""
    engine = AdviceEngine()
    await engine.decay()
    log.info("[AdviceJob] Decay pass completed.")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Apply time-based decay to Advice weights.")
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
    asyncio.run(run())


if __name__ == "__main__":
    main()
