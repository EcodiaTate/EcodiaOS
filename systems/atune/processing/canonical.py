# systems/atune/processing/canonical.py

import hashlib

from pydantic import BaseModel

from systems.axon.schemas import AxonEvent


class CanonicalEvent(BaseModel):
    """
    A structured, canonical representation of an event, ready for salience scoring.
    """

    event_id: str
    source: str
    event_type: str
    text_blocks: list[str]
    numerical_features: dict[str, float]
    text_hash: str
    original_event: AxonEvent


class Canonicalizer:
    """
    Transforms AxonEvents into a canonical format for consistent processing.
    """

    def canonicalise(self, event: AxonEvent) -> CanonicalEvent:
        """
        Applies the canonicalization logic from the core utility script.
        """
        text_blocks: list[str] = list(event.parsed.get("text_blocks", []))
        numerical_features: dict[str, float] = {}

        # Extract numeric features from the original event's quality/other fields if they exist
        # This part can be expanded based on expected numeric data in AxonEvent
        if event.quality:
            for k, v in event.quality.items():
                if isinstance(v, int | float):
                    numerical_features[k] = float(v)

        # Ensure order-independent hash of the content
        hash_input = "\n".join(sorted([b for b in text_blocks if b]))
        text_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

        return CanonicalEvent(
            event_id=event.event_id,
            source=event.source,
            event_type=event.event_type,
            text_blocks=text_blocks,
            numerical_features=numerical_features,
            text_hash=text_hash,
            original_event=event,
        )
