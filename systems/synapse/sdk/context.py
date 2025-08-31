from __future__ import annotations

from typing import Any


def build_context(
    *,
    tenant: str | None = None,
    actor: str | None = None,
    resource_descriptors: list[dict[str, Any]] | None = None,
    risk: str | None = None,
    budget: str | None = None,
    pii_tags: list[str] | None = None,
    data_domains: list[str] | None = None,
    latency_budget_ms: int | None = None,
    sla_deadline: str | None = None,
    graph_refs: dict[str, Any] | None = None,
    observability: dict[str, Any] | None = None,
    context_vector: list[float] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build a maximal context dict. Keep keys stable so bandits/firewall/planner can learn.
    """
    ctx: dict[str, Any] = {
        "tenant": tenant,
        "actor": actor,
        "resource_descriptors": resource_descriptors or [],
        "risk": risk,
        "budget": budget,
        "pii_tags": pii_tags or [],
        "data_domains": data_domains or [],
        "latency_budget_ms": latency_budget_ms,
        "sla_deadline": sla_deadline,
        "graph_refs": graph_refs or {},
        "observability": observability or {},
        "context_vector": context_vector,
    }
    if extra:
        ctx.update(extra)
    # remove Nones
    return {k: v for k, v in ctx.items() if v is not None}
