# app/app_state.py
# This file holds shared application state to prevent circular imports.
from __future__ import annotations

import asyncio

# This Event will act as a gate to pause requests until bootstrap is complete.
# Both app.py and planning.py will import it from here.
BOOTSTRAP_EVENT = asyncio.Event()
