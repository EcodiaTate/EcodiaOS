# systems/atune/planner/inference.py


import numpy as np
from pydantic import BaseModel

from systems.atune.processing.canonical import CanonicalEvent


class GenerativeModel(BaseModel):
    """A simplified generative model representing the agent's beliefs about the world."""

    # P(observation | state) - Likelihood
    state_observation_matrix: dict[str, dict[str, float]] = {
        "safe_state": {"benign_event": 0.9, "threat_event": 0.1},
        "threat_state": {"benign_event": 0.2, "threat_event": 0.8},
    }
    # P(state) - Prior beliefs about world states
    prior_beliefs: dict[str, float] = {"safe_state": 0.95, "threat_state": 0.05}


class ActiveInferenceHead:
    """
    A policy head that selects actions to minimize Expected Free Energy (EFE).
    EFE = -E_q[ ln(P(o|π)) - KL[q(s|π)||P(s)] ]
    This simplifies to minimizing a combination of risk and ambiguity.
    """

    def __init__(self):
        self.generative_model = GenerativeModel()
        # C matrix: Prior preferences over outcomes (goal state)
        self.goal_preferences = {"benign_event": 1.0, "threat_event": -10.0}

    def calculate_expected_free_energy(self, event: CanonicalEvent, proposed_action: str) -> float:
        """
        Calculates the EFE for a proposed action given an event.
        Lower EFE is better.
        """
        # This is a simplified, illustrative calculation. A full implementation
        # involves complex Bayesian inference (belief updating).

        # 1. Risk: Divergence between predicted outcomes and goal preferences.
        # If the proposed action is 'qora:search', we assume it clarifies the state.
        if proposed_action == "qora:search":
            # Searching reduces ambiguity, making the predicted outcome closer to the true state.
            # Here we simulate this by using a weighted average based on the likelihood matrix.
            predicted_outcome_prob_threat = (
                self.generative_model.prior_beliefs["safe_state"]
                * self.generative_model.state_observation_matrix["safe_state"]["threat_event"]
                + self.generative_model.prior_beliefs["threat_state"]
                * self.generative_model.state_observation_matrix["threat_state"]["threat_event"]
            )
        else:  # For a 'null' action, the outcome is just the prior.
            predicted_outcome_prob_threat = self.generative_model.prior_beliefs["threat_state"]

        risk = -(predicted_outcome_prob_threat * self.goal_preferences["threat_event"])

        # 2. Ambiguity: The uncertainty of the outcome.
        # Searching resolves uncertainty about the state.
        ambiguity = -predicted_outcome_prob_threat * np.log(predicted_outcome_prob_threat + 1e-9)

        expected_free_energy = risk + ambiguity
        print(
            f"ActiveInferenceHead: EFE for action '{proposed_action}' is {expected_free_energy:.4f}",
        )
        return expected_free_energy
