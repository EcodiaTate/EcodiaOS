# systems/atune/causal/model.py


from pydantic import BaseModel, Field


class CausalVariable(BaseModel):
    """Represents a node in the causal graph."""

    name: str
    description: str
    type: str  # e.g., 'continuous', 'binary'


class StructuralEquation(BaseModel):
    """Represents the functional relationship V := f(parents(V), U_v)."""

    outcome: str
    causes: list[str]
    # The functional form would be learned by a more advanced system.
    # Here, we represent the connection and its strength.
    coefficients: dict[str, float]


class StructuralCausalModel(BaseModel):
    """

    Represents Atune's causal beliefs about a specific domain as a DAG.
    """

    domain: str
    variables: dict[str, CausalVariable] = Field(default_factory=dict)
    equations: dict[str, StructuralEquation] = Field(default_factory=dict)
