# systems/unity/core/workspace/global_workspace.py
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import numpy as np

from core.services.synapse import synapse
from core.utils.bus_utils import publish as bus_publish
from core.utils.bus_utils import subscribe as bus_subscribe
from systems.equor.schemas import QualiaState
from systems.unity.schemas import BroadcastEvent, Cognit


class AttentionMechanism:
    """
    Decides which cognit in the workspace is most salient.
    L3: if Synapse exposes a ranker, use it; otherwise fall back to salience sort.
    """

    def __init__(self) -> None:
        # IMPORTANT: synapse is a singleton instance, do not call it.
        self.synapse = synapse

    async def select_for_broadcast(self, cognits: list[Cognit]) -> Cognit | None:
        if not cognits:
            return None

        # Try Synapse ranking if available
        try:
            predict_fn = getattr(self.synapse, "predict", None)
            if callable(predict_fn):
                req = {
                    "model_id": "unity_attention_ranker_v1",
                    "inputs": {
                        "cognits": [
                            {
                                "id": c.id,
                                "source_process": c.source_process,
                                "salience": c.salience,
                                "timestamp": c.timestamp,
                            }
                            for c in cognits
                        ],
                    },
                }
                print(f"[Attention] Querying Synapse ranker for {len(cognits)} cognits...")
                resp = await predict_fn(req)  # May raise if endpoint not enabled
                ranked_ids = (resp or {}).get("ranked_cognit_ids")
                if isinstance(ranked_ids, list) and ranked_ids:
                    # Take the highest-ranked that still exists
                    for cid in ranked_ids:
                        winner = next((c for c in cognits if c.id == cid), None)
                        if winner:
                            print(
                                f"[Attention] Synapse selected cognit '{winner.id}' from '{winner.source_process}'.",
                            )
                            return winner
        except Exception as e:
            print(f"[Attention] Synapse ranking unavailable: {e!r}")

        # Fallback: pick max salience
        winner = max(cognits, key=lambda c: c.salience)
        print(
            f"[Attention] Fallback selected cognit '{winner.id}' (salience={winner.salience:.2f}).",
        )
        return winner


class GlobalWorkspace:
    _instance: GlobalWorkspace | None = None

    _cognits: list[Cognit]
    _lock: asyncio.Lock
    attention_mechanism: AttentionMechanism

    def __new__(cls):
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._cognits = []
            inst._lock = asyncio.Lock()
            inst.attention_mechanism = AttentionMechanism()

            # Subscribe to Equor's qualia stream (async callback is fine)
            try:
                bus_subscribe("equor.qualia.state.created", inst.handle_qualia_event)
                print("[Workspace] Subscribed to Equor's qualia stream.")
            except Exception as e:
                print(f"[Workspace] WARNING: Failed to subscribe to qualia stream: {e}")

            cls._instance = inst
        return cls._instance

    async def handle_qualia_event(self, qualia_state: dict[str, Any]) -> None:
        qs = QualiaState.model_validate(qualia_state)
        # Simple salience heuristic from first coordinate (dissonance-like)
        dissonance_component = float(qs.manifold_coordinates[0] if qs.manifold_coordinates else 0.0)
        salience = float(np.clip(dissonance_component / 2.0, 0.0, 1.0))

        content = (
            "Internal State Report: Detected a subjective state "
            f"with coordinates {qs.manifold_coordinates}. "
            f"Dissonance level estimated at {salience:.2f}."
        )
        print(
            f"[Workspace] Received internal state {qs.id}. Posting as cognit with salience {salience:.2f}.",
        )
        await self.post_cognit("Equor.StateLogger", content, salience, is_internal=True)

    async def post_cognit(
        self,
        source_process: str,
        content: str,
        salience: float,
        is_internal: bool = False,
    ) -> None:
        async with self._lock:
            cognit = Cognit(
                id=f"cog_{uuid.uuid4().hex}",
                source_process=source_process,
                content=content,
                salience=float(np.clip(salience, 0.0, 1.0)),
                timestamp=datetime.now(UTC).isoformat(),
            )
            self._cognits.append(cognit)
            if not is_internal:
                print(
                    f"[Workspace] Cognit posted by '{source_process}' with salience {salience:.2f}.",
                )

    async def run_broadcast_cycle(self) -> None:
        async with self._lock:
            if not self._cognits:
                return

            selected_cognit = await self.attention_mechanism.select_for_broadcast(self._cognits)
            if not selected_cognit:
                return

            # Clear workspace after selection
            self._cognits = []

            event = BroadcastEvent(
                broadcast_id=f"bc_{uuid.uuid4().hex}",
                selected_cognit=selected_cognit,
                notes="This cognit was selected by the attention mechanism.",
            )

            # Use safe bus wrapper; payload is the broadcast dict itself.
            await bus_publish("unity.workspace.ignition", event.model_dump())
            print(
                f"[Workspace] IGNITION: Broadcasting cognit '{selected_cognit.id}' from '{selected_cognit.source_process}'.",
            )


# Singleton export
global_workspace = GlobalWorkspace()
