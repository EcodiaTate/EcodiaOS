# core/utils/logging_tools.py
from __future__ import annotations

import logging
import os
import uuid

VOXIS_DEBUG = os.getenv("VOXIS_DEBUG", "1").strip().lower() not in ("0", "false", "no", "off")


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = logging.StreamHandler()
        fmt = logging.Formatter("[%(levelname)s] %(asctime)s %(name)s: %(message)s")
        h.setFormatter(fmt)
        logger.addHandler(h)
    logger.setLevel(logging.DEBUG if VOXIS_DEBUG else logging.INFO)
    return logger


def new_trace_id() -> str:
    return f"vx-{uuid.uuid4().hex[:12]}"
