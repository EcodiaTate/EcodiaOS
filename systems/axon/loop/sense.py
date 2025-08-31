# systems/axon/loop/sense.py
from __future__ import annotations

import time
from typing import Any

from systems.axon.dependencies import get_driver_registry, get_quarantine, get_journal
from systems.axon.events.emitter import emit_followups_bg
from systems.axon.schemas import AxonEvent


class SenseLoop:
    """
    Pull drivers → quarantine/canonicalize → shape AxonEvent → emit follow-ups (best-effort) + journal.
    """

    def __init__(self) -> None:
        self.registry = get_driver_registry()
        self.quarantine = get_quarantine()
        self.journal = get_journal()

    async def poll_once(self) -> int:
        produced = 0
        for drv in self.registry.list_all():
            if not hasattr(drv, "pull"):
                continue
            async for raw in drv.pull({}):
                # allow drivers to yield AxonEvent already
                if isinstance(raw, AxonEvent):
                    event = raw
                else:
                    # assume {payload, mime} or free-form; quarantine defensively
                    payload = getattr(raw, "payload", raw)
                    mime = getattr(raw, "mime", "text/plain")
                    canon = self.quarantine.process_and_canonicalize(payload, mime)
                    event = AxonEvent(
                        event_id=f"ev_{int(time.time()*1000)}",
                        t_observed=time.time(),
                        source=getattr(drv, "NAME", "driver"),
                        event_type="driver.pull",
                        modality="text" if canon.content_type == "text" else "json",
                        payload_ref=None,
                        parsed={"text": canon.text_blocks, "structured": canon.structured_data, "taints": [t.model_dump() for t in canon.taints]},
                        embeddings={},
                        provenance={"driver": getattr(drv, "NAME", ""), "version": getattr(drv, "VERSION", "")},
                    )

                # emit (best-effort) back to Atune and journal
                emit_followups_bg([{"event": event.model_dump()}])
                try:
                    self.journal.write_entry(event)  # MEJ accepts Pydantic models
                except Exception:
                    pass
                produced += 1
        return produced
