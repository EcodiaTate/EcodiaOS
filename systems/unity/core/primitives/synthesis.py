from typing import Any

from systems.equor.schemas import QualiaState
from systems.unity.core.room.adjudicator import Adjudicator
from systems.unity.schemas import DeliberationSpec, VerdictModel


async def synthesize_verdict(
    spec: DeliberationSpec,
    transcript: list[dict[str, Any]],
    qualia_state: QualiaState | None = None,
) -> VerdictModel:
    """
    Makes a final decision based on the full deliberation transcript and context.
    This is a wrapper around the intelligent Adjudicator.decide method.

    The `qualia_state` parameter is included to prepare for the Aletheia Protocol,
    where the final synthesis will become state-aware.
    """
    if qualia_state:
        print(
            f"[Synthesis] Performing state-aware synthesis. Current dissonance: {qualia_state.manifold_coordinates[0]:.4f}"
        )

    adjudicator = Adjudicator()
    # --- FIX: Pass the correct arguments to the new intelligent Adjudicator ---
    verdict = await adjudicator.decide(
        spec=spec,
        transcript=transcript,
    )
    return verdict
