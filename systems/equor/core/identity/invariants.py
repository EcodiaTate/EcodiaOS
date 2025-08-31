# systems/equor/core/identity/invariants.py


from core.utils.neo.cypher_query import cypher_query
from systems.equor.schemas import Invariant, InvariantCheckResult


class InvariantAuditor:
    """
    A singleton service that runs cross-system invariant checks against the
    Neo4j graph to ensure holistic system coherence.
    P2 UPGRADE: Now dynamically loads Invariants from the graph.
    """

    _instance = None
    _invariants: list[Invariant] = []

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def initialize(self):
        """Loads all active Invariant nodes from the graph."""
        print("[Equor-Invariant] Loading invariants from graph...")
        query = "MATCH (i:Invariant {is_active: true}) RETURN i"
        results = await cypher_query(query)
        if not results:
            print("[Equor-Invariant] WARNING: No active invariants found in graph.")
            self._invariants = []
            return

        self._invariants = [Invariant(**record["i"]) for record in results]
        print(f"[Equor-Invariant] Loaded {len(self._invariants)} invariants.")

    async def run_audit(self) -> list[InvariantCheckResult]:
        """
        Executes all registered invariant checks and returns the results.
        """
        # Ensure invariants are loaded before running
        if not self._invariants:
            await self.initialize()

        results = []
        print(
            f"[Equor-Invariant] Starting full system audit across {len(self._invariants)} invariants...",
        )
        for invariant in self._invariants:
            try:
                violations = await cypher_query(invariant.cypher_query)
                result = InvariantCheckResult(
                    invariant_id=invariant.id,
                    holds=not violations,
                    violations_found=len(violations),
                    details=violations,
                )
                results.append(result)
            except Exception as e:
                results.append(
                    InvariantCheckResult(
                        invariant_id=invariant.id,
                        holds=False,
                        violations_found=-1,  # Indicates an error
                        details=[{"error": f"Query failed: {e!r}"}],
                    ),
                )
        print(f"[Equor-Invariant] Audit complete.")
        return results


# Singleton export
invariant_auditor = InvariantAuditor()
