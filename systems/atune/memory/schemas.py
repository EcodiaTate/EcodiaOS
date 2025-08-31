# systems/atune/memory/schemas.py


from pydantic import BaseModel, Field


class FocusNode(BaseModel):
    """
    A record of a single, salient cognitive event that has been fully
    processed by the Atune cognitive cycle. This is the raw material
    from which long-term memory (Schemas) is constructed.
    """

    node_id: str = Field(..., description="Unique ID for this focus node.")
    source_event_id: str
    canonical_hash: str
    text_embedding: list[float]  # A representative embedding of the event content
    salience_vector: dict[str, float]
    fae_score: float
    final_plan_mode: str
    action_result_status: str | None = None


class Schema(BaseModel):
    """
    A named, abstract conceptual motif induced from a cluster of FocusNodes.
    It acts as a powerful prior for future cognitive cycles.
    """

    schema_id: str
    schema_name: str = Field(
        ...,
        description="An LLM-generated conceptual name (e.g., 'high_risk_security_alert').",
    )
    centroid_embedding: list[float]
    member_node_ids: list[str]
    # Priors that will be used to bootstrap processing for matching events
    salience_priors: dict[str, float] = Field(
        ...,
        description="Average salience scores to bootstrap new events.",
    )
    fae_utility_prior: float = Field(
        ...,
        description="Average historical utility to bootstrap FAE probes.",
    )
