# systems/atune/memory/store.py


import numpy as np

from systems.atune.memory.schemas import FocusNode, Schema


class MemoryStore:
    """
    An in-memory store for FocusNodes (episodic memory) and induced
    Schemas (semantic memory).
    """

    def __init__(self):
        self._focus_nodes: dict[str, FocusNode] = {}
        self._schemas: dict[str, Schema] = {}
        self._schema_centroids: np.ndarray | None = None
        self._schema_ids: list[str] = []

    def add_focus_node(self, node: FocusNode):
        """Adds a new salient experience to the episodic memory store."""
        self._focus_nodes[node.node_id] = node

    def get_all_nodes(self) -> list[FocusNode]:
        """Returns all stored focus nodes for the induction process."""
        return list(self._focus_nodes.values())

    def update_schemas(self, new_schemas: list[Schema]):
        """Replaces the current set of schemas with a newly induced set."""
        self._schemas = {s.schema_id: s for s in new_schemas}

        # Pre-compute centroids for efficient matching
        if new_schemas:
            self._schema_centroids = np.array(
                [s.centroid_embedding for s in new_schemas],
                dtype=np.float32,
            )
            self._schema_ids = [s.schema_id for s in new_schemas]
        else:
            self._schema_centroids = None
            self._schema_ids = []
        print(f"MemoryStore: Updated with {len(new_schemas)} new schemas.")

    def match_event_to_schema(
        self,
        event_embedding: np.ndarray,
        threshold: float = 0.85,
    ) -> Schema | None:
        """
        Finds the best matching schema for a new event's embedding using
        cosine similarity against pre-computed schema centroids.
        """
        if self._schema_centroids is None or not self._schema_ids:
            return None

        # Normalize vectors for cosine similarity calculation
        norm_event_emb = event_embedding / np.linalg.norm(event_embedding)
        norm_centroids = (
            self._schema_centroids / np.linalg.norm(self._schema_centroids, axis=1)[:, np.newaxis]
        )

        # Compute cosine similarities
        similarities = np.dot(norm_centroids, norm_event_emb)

        best_match_index = np.argmax(similarities)
        best_score = similarities[best_match_index]

        if best_score >= threshold:
            matched_schema_id = self._schema_ids[best_match_index]
            print(
                f"MemoryStore: Event matched to schema '{self._schemas[matched_schema_id].schema_name}' with score {best_score:.4f}.",
            )
            return self._schemas[matched_schema_id]

        return None
