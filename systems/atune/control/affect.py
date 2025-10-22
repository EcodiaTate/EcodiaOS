# systems/atune/control/affect.py
from pydantic import BaseModel, Field


class AffectiveState(BaseModel):
    """
    A vector representing the high-level homeostatic and drive states of
    the EcodiaOS, as published by Equor. All values are normalized to [0, 1].

    """

    # Using valence (unpleasant<->pleasant) and arousal (calm<->excited)
    # is a more standard and flexible representation of affect.
    valence: float = Field(0.5, ge=0.0, le=1.0, description="0=unpleasant, 1=pleasant")
    arousal: float = Field(0.2, ge=0.0, le=1.0, description="0=calm, 1=excited")

    curiosity: float = Field(0.5, ge=0.0, le=1.0)
    caution: float = Field(0.2, ge=0.0, le=1.0)
    integrity_load: float = Field(0.1, ge=0.0, le=1.0)
    focus_fatigue: float = Field(0.0, ge=0.0, le=1.0)


class ControlModulations(BaseModel):
    """
    A set of concrete parameter modulations derived from an AffectiveState.
    These are the outputs of the control loop that tune the cognitive architecture.
    """

    mag_temperature: float = Field(..., gt=0)
    risk_head_weight_multiplier: float = Field(..., ge=0)
    sfkg_leak_gamma: float = Field(..., ge=0, le=1)

    # 🔽 NEW MODULATIONS 🔽
    reflection_threshold_delta: float = Field(
        ...,
        ge=-0.5,
        le=0.5,
        description="Value to subtract from the base reflection threshold.",
    )
    valence: float = Field(..., ge=0.0, le=1.0, description="Direct pass-through for MAG context.")
    arousal: float = Field(..., ge=0.0, le=1.0, description="Direct pass-through for MAG context.")


class AffectiveControlLoop:
    """
    Manages the current affective state and calculates the corresponding
    cognitive parameter modulations for a given cognitive cycle.
    """

    def __init__(self):
        self._current_state = AffectiveState()

    def update_state(self, new_state: AffectiveState):
        """Callback to update the system's current affective state."""
        self._current_state = new_state
        print(f"AffectiveControlLoop: State updated -> {new_state.model_dump_json()}")

    def get_current_modulations(self) -> ControlModulations:
        """
        Applies a set of control laws to translate the affective state
        into concrete parameter adjustments.
        """
        state = self._current_state

        # Law 1: Curiosity drives exploration
        mag_temp = 1.0 + (state.curiosity * 1.5)

        # Law 2: Caution amplifies risk sensitivity
        risk_multiplier = 1.0 + (state.caution * 2.0)

        # Law 3: Focus Fatigue increases leak rate
        base_gamma = 0.05
        sfkg_gamma = base_gamma + (state.focus_fatigue * 0.2)

        # 🔽 NEW LAW 4: Curiosity and low-valence (unpleasant) states lower the
        # reflection threshold, making the system more introspective.
        # High caution can slightly raise it to prevent distraction.
        reflection_delta = (
            (state.curiosity * 0.15) + ((1.0 - state.valence) * 0.1) - (state.caution * 0.05)
        )

        return ControlModulations(
            mag_temperature=mag_temp,
            risk_head_weight_multiplier=risk_multiplier,
            sfkg_leak_gamma=sfkg_gamma,
            reflection_threshold_delta=reflection_delta,  # ⬅️ ADDED
            valence=state.valence,  # ⬅️ ADDED
            arousal=state.arousal,  # ⬅️ ADDED
        )
