# systems/axon/journal/mej.py

from datetime import UTC, datetime
from hashlib import blake2b
from typing import Any

from pydantic import BaseModel, Field

# -----------------------------------------------------------------------------
# Data Contract for Journal Entries
# -----------------------------------------------------------------------------


class JournalEntry(BaseModel):
    """A single, hashed entry in the Merkle Event Journal."""

    entry_hash: str = Field(
        ...,
        description="BLAKE2b hash of the canonicalized payload and previous hash.",
    )
    prev_entry_hash: str | None = Field(
        ...,
        description="The hash of the preceding journal entry, forming a chain.",
    )
    timestamp_utc: str = Field(..., description="ISO 8601 timestamp of when the entry was created.")
    entry_type: str = Field(
        ...,
        description="The Python type of the object being logged, e.g., 'AxonEvent'.",
    )
    payload: dict[str, Any] = Field(
        ...,
        description="The original data payload of the logged object.",
    )


# -----------------------------------------------------------------------------
# Deterministic JSON Serializer
# -----------------------------------------------------------------------------


def to_deterministic_json(model: BaseModel) -> bytes:
    """
    Serializes a Pydantic model to a deterministic JSON byte string.
    This is crucial for ensuring that hashes are reproducible.
    """
    json_string = model.model_dump_json(sort_keys=True)
    return json_string.encode("utf-8")


# -----------------------------------------------------------------------------
# Journal Writer Class
# -----------------------------------------------------------------------------


class MerkleJournal:
    """
    Manages writing entries to the Merkle Event Journal, creating a hash chain.
    """

    def __init__(self, hash_digest_size: int = 32):
        """Initializes the journal."""
        self.digest_size = hash_digest_size
        self._last_hash: str | None = None

    def write_entry(self, obj: BaseModel) -> JournalEntry:
        """
        Takes a Pydantic object, links it to the previous entry, serializes,
        hashes it, and returns a complete JournalEntry.

        Args:
            obj: The Pydantic model instance to log (e.g., AxonEvent, AxonIntent).

        Returns:
            A completed JournalEntry ready to be persisted.
        """
        entry_type = type(obj).__name__
        payload_bytes = to_deterministic_json(obj)

        hasher = blake2b(digest_size=self.digest_size)

        # Chain the hash: include the previous entry's hash in the new hash
        if self._last_hash:
            hasher.update(self._last_hash.encode("utf-8"))

        hasher.update(payload_bytes)
        entry_hash = hasher.hexdigest()

        entry = JournalEntry(
            entry_hash=entry_hash,
            prev_entry_hash=self._last_hash,
            timestamp_utc=datetime.now(UTC).isoformat(),
            entry_type=entry_type,
            payload=obj.model_dump(),
        )

        # Update the state to the new hash for the next entry
        self._last_hash = entry_hash

        print(
            f"MEJ Entry Created: {entry.entry_hash} ({entry.entry_type}) -> Links to: {entry.prev_entry_hash}",
        )
        return entry
