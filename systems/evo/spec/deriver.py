from __future__ import annotations

from collections import defaultdict

from systems.evo.schemas import ConflictNode

Obligation = dict[str, dict[str, str]]  # {"kind": {"target": str, "rule": str, "note": str}}


class SpecDeriver:
    """
    Derives/strengthens obligations before any repair ("Spec-First or Spec-Make").
    Outputs are intentionally machine-checkable: kind/target/rule/note.
    """

    # Kinds we standardise: resource, temporal, interface, policy
    def derive_obligations(self, conflicts: list[ConflictNode]) -> dict[str, list[Obligation]]:
        out: dict[str, list[Obligation]] = defaultdict(list)
        for c in conflicts:
            modules = list(dict.fromkeys(c.context.get("modules", [])))
            # 1) Temporal obligations for latency/backpressure
            if "latency_ms" in c.context or c.tags and any("latency" in t for t in c.tags):
                for m in modules or ["unknown"]:
                    out["temporal"].append(
                        {
                            "kind": {
                                "target": m,
                                "rule": "p95_latency_ms <= 1200",
                                "note": "bounded p95",
                            },
                        },
                    )
                    out["temporal"].append(
                        {
                            "kind": {
                                "target": m,
                                "rule": "max_retry_backoff <= 8s",
                                "note": "progress bound",
                            },
                        },
                    )
            # 2) Resource bounds (queues, memory growth)
            if "queue_growth" in c.context or c.kind in {"perf_regression"}:
                for m in modules or ["unknown"]:
                    out["resource"].append(
                        {
                            "kind": {
                                "target": m,
                                "rule": "queue_depth(t) is bounded",
                                "note": "no unbounded growth",
                            },
                        },
                    )
            # 3) Interface contracts (idempotence, status codes)
            if "api" in c.tags or "protocol" in (c.context.get("category") or ""):
                for m in modules or ["unknown"]:
                    out["interface"].append(
                        {
                            "kind": {
                                "target": m,
                                "rule": "retries are idempotent",
                                "note": "no duplicate side-effects",
                            },
                        },
                    )
                    out["interface"].append(
                        {
                            "kind": {
                                "target": m,
                                "rule": "error_policy ∈ {retry,fail_fast,fallback}",
                                "note": "explicit",
                            },
                        },
                    )
            # 4) Policy obligations (safety/identity)
            if "safety" in c.tags or c.kind == "safety_breach":
                out["policy"].append(
                    {
                        "kind": {
                            "target": "system",
                            "rule": "no net_access during repair",
                            "note": "sandbox evolution",
                        },
                    },
                )
        return dict(out)

    def derive_rollback(self, conflicts: list[ConflictNode]) -> dict[str, str]:
        """
        Declarative rollback contract so proposals can guarantee reversibility.
        """
        modules = sorted({m for c in conflicts for m in c.context.get("modules", [])})
        return {
            "strategy": "patch_reversal_and_config_restore",
            "targets": ",".join(modules) or "unknown",
            "checks": "pre-change tests must pass; config drift zero; data migrations reversible",
        }

    def impact_table(self, obligations: dict[str, list[Obligation]]) -> dict[str, dict[str, str]]:
        """
        Skeleton spec impact table slots; ProposalAssembler fills pre→post.
        """
        table: dict[str, dict[str, str]] = {}
        for kind, items in obligations.items():
            for it in items:
                tgt = it["kind"]["target"]
                key = f"{kind}:{tgt}:{it['kind']['rule']}"
                table[key] = {"pre": "unknown", "post": "unknown", "evidence": ""}
        return table
