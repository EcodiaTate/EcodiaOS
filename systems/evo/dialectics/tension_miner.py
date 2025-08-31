from __future__ import annotations

from uuid import uuid4

from core.utils.neo.cypher_query import cypher_query
from systems.evo.schemas import ConflictKind, ConflictNode, Reproducer, SpecCoverage


class TensionMiner:
    """
    Manufactures 'dialectical conflicts' to surface contradictions with high learning value.
    """

    async def mine(self, *, limit: int = 5) -> list[ConflictNode]:
        found: list[ConflictNode] = []
        q = """
        MATCH (m:Module)
        WHERE coalesce(m.p95_latency_ms, 0) > 1200 AND coalesce(m.retry_rate, 0.0) > 0.15
        RETURN m.name AS module, m.p95_latency_ms AS p95, m.retry_rate AS retry
        LIMIT $k
        """
        rows = await cypher_query(q, {"k": int(limit)})
        for r in rows or []:
            cid = f"tension_{uuid4().hex[:10]}"
            found.append(
                ConflictNode(
                    conflict_id=cid,
                    t_created=0.0,
                    source_system="evo",
                    kind=ConflictKind.disagreement,
                    description=f"Spec tension for {r.get('module')}: latency vs retry policy",
                    context={
                        "modules": [r.get("module")],
                        "signals": {"p95": r.get("p95"), "retry": r.get("retry")},
                    },
                    severity="medium",
                    depends_on=[],
                    tags=["spec", "latency", "retries", "tension"],
                    reproducer=Reproducer(kind="sim", minimal=True, stable=True),
                    spec_coverage=SpecCoverage(has_spec=False, gaps=["temporal", "policy"]),
                ),
            )
        return found

    async def persist(self, conflicts: list[ConflictNode]) -> int:
        n = 0
        for c in conflicts:
            q = """
            MERGE (x:Conflict {event_id: $id})
            SET x += {
              source: $src, kind: $kind, description: $desc,
              severity: $sev, tags: $tags, context: $ctx
            }
            """
            await cypher_query(
                q,
                {
                    "id": c.conflict_id,
                    "src": c.source_system,
                    "kind": c.kind.value,
                    "desc": c.description,
                    "sev": c.severity,
                    "tags": c.tags,
                    "ctx": c.context,
                },
            )
            n += 1
        return n
