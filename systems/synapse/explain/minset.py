# systems/synapse/explain/minset.py
# FINAL VERSION FOR PHASE II - AUDITABILITY
from __future__ import annotations

from typing import Any

import numpy as np


def min_explanation(
    x: np.ndarray,
    theta_chosen: np.ndarray,
    theta_alt: np.ndarray,
    feature_names: list[str] | None = None,
) -> dict[str, Any]:
    """
    Calculates the minimal set of features that would have flipped the decision
    from the chosen arm to the alternative, as specified in the vision doc.
    """
    if (
        not isinstance(x, np.ndarray)
        or not isinstance(theta_chosen, np.ndarray)
        or not isinstance(theta_alt, np.ndarray)
    ):
        return {"error": "Invalid input types, expected numpy arrays"}

    if x.shape[0] != theta_chosen.shape[0] or x.shape[0] != theta_alt.shape[0]:
        return {"error": "Dimension mismatch between context and thetas"}

    x = x.ravel()
    theta_chosen = theta_chosen.ravel()
    theta_alt = theta_alt.ravel()

    # The contribution of each feature to the score difference
    delta = x * (theta_chosen - theta_alt)

    # Score difference must be positive for the 'chosen' to have won
    if np.sum(delta) <= 0:
        return {
            "minset": [],
            "flip_to": "alternative_arm",
            "reason": "Alternative arm already had a higher or equal score.",
        }

    # Indices of features sorted by their absolute impact
    idx = np.argsort(-np.abs(delta))

    sel_indices = []
    running_delta_sum = np.sum(delta)

    for i in idx:
        sel_indices.append(int(i))
        running_delta_sum -= delta[i]
        if running_delta_sum < 0:  # Decision has flipped
            break

    # Map indices back to names if provided
    if feature_names and len(feature_names) == len(delta):
        minset = [feature_names[i] for i in sel_indices]
    else:
        minset = [f"feature_{i}" for i in sel_indices]

    return {
        "minset": minset,
        "flip_to": "alternative_arm",  # Placeholder for the alt arm's ID
    }
