# systems/evo/conflicts.py
from __future__ import annotations
from typing import Dict, List
from systems.evo.schemas import ConflictID, ConflictNode

class ConflictsService:
    """
    A type-safe, in-memory store for ConflictNode objects.
    This service is the source of truth for conflict data within the engine and
    is responsible for ensuring data integrity.
    """
    def __init__(self):
        self._by_id: Dict[ConflictID, ConflictNode] = {}

    def _coerce(self, conflict_data: ConflictNode | dict) -> ConflictNode:
        """Coerces a dictionary or partial object into a full ConflictNode."""
        if isinstance(conflict_data, ConflictNode):
            return conflict_data
        # If it's a dict, instantiate a ConflictNode. Pydantic will fill in
        # all the missing default values, including 'spec_coverage'.
        return ConflictNode(**conflict_data)

    def batch(self, conflicts: List[ConflictNode | dict]) -> List[ConflictID]:
        """Intakes a list of conflicts, ensuring they are all valid nodes."""
        ids: List[ConflictID] = []
        for c in conflicts:
            node = self._coerce(c)
            self._by_id[node.conflict_id] = node
            ids.append(node.conflict_id)
        return ids

    def get(self, cid: ConflictID) -> ConflictNode:
        """Retrieves a conflict by its ID, guaranteeing a valid ConflictNode."""
        if cid not in self._by_id:
            raise KeyError(f"Conflict ID '{cid}' not found in the store.")
        
        # Coerce on get as well, to protect against older, non-validated data
        # that might exist in the store from before this fix.
        return self._coerce(self._by_id[cid])