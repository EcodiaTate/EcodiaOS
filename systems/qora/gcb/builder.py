from __future__ import annotations

# EcodiaOS helpers
from core.utils.net_api import ENDPOINTS, get_http_client  # type: ignore[attr-defined]
from systems.qora.manifest.models import SystemManifest

from .models import GoldenContextBundle, Koan, SnippetRef


def build_gcb(
    decision_id: str,
    scope: dict,
    targets: list[dict],
    manifest: SystemManifest,
    *,
    http_method_default: str = "POST",
) -> GoldenContextBundle:
    # Map manifest → endpoint contracts (path via overlay)
    contracts_endpoints: list[dict] = []
    for row in manifest.endpoints_used:
        alias = row["alias"]
        try:
            path = ENDPOINTS.path(alias)  # type: ignore[attr-defined]
        except Exception:
            path = None
        contracts_endpoints.append({"alias": alias, "path": path, "method": http_method_default})

    # Minimal koan: header discipline roundtrip
    koans = [
        Koan(
            name="header_discipline",
            kind="http",
            request={"headers": {"x-decision-id": decision_id, "x-budget-ms": "1000"}},
            expect={"response_headers_contains": ["X-Cost-MS"]},
        ),
    ]

    # Snippets: include first few files deterministically (Simula must use contentRef hashes)
    snippets: list[SnippetRef] = []
    for ref in manifest.content_refs[:8]:
        snippets.append(SnippetRef(**ref.model_dump()))

    gcb = GoldenContextBundle(
        decision_id=decision_id,
        scope=scope,
        targets=targets,
        manifests=[{"system": manifest.system, "hash": manifest.manifest_hash}],
        edges_touched=manifest.edges,
        contracts={"endpoints": contracts_endpoints, "tools": []},
        examples={"requests": [], "tool_calls": []},
        tests={"acceptance": [], "koans": koans},
        snippets=snippets,
        risk_notes=[],
    )
    return gcb


def dispatch_gcb_to_simula(gcb: GoldenContextBundle, *, timeout: float = 60.0) -> dict:
    """
    Bridge to Simula obeying SIMULA_JOBS_CODEGEN contract:
      Body: {"spec": <any JSON>, "targets": [...]}
    We send the GCB as the 'spec' and mirror targets from gcb.targets.
    """
    client = get_http_client()  # inherits base_url, timeouts, auth from EcodiaOS
    path = ENDPOINTS.path("SIMULA_JOBS_CODEGEN")  # type: ignore[attr-defined]
    body = {"spec": gcb.model_dump(), "targets": gcb.targets}
    resp = client.post(path, json=body, timeout=timeout)
    resp.raise_for_status()
    return resp.json()
