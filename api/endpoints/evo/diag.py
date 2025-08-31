from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Query, Response

from core.utils.neo.cypher_query import cypher_query
from core.utils.net_api import ENDPOINTS, get_http_client
from systems.evo.runtime import get_engine

diag_router = APIRouter(tags=["evo-diagnostics"])
_engine = get_engine()


def _stamp_cost(res: Response, start: float) -> None:
    res.headers["X-Cost-MS"] = str(int((time.perf_counter() - start) * 1000))


@diag_router.get("/health", response_model=dict)
async def health(
    response: Response,
    deep: bool = Query(
        default=False,
        description="If true, POSTs minimal payloads to Atune/Nova/Simula/Equor.",
    ),
) -> dict[str, Any]:
    """
    One call to restore confidence:
      - Checks Neo4j connectivity
      - Verifies ENDPOINTS are present
      - Optionally probes Atune/Nova/Simula/Equor with safe, minimal payloads (deep=True)
    """
    t0 = time.perf_counter()
    checks: list[dict[str, Any]] = []

    # 1) Graph connectivity
    try:
        rows = await cypher_query("RETURN 1 AS ok")
        checks.append({"neo4j": bool(rows and rows[0].get("ok") == 1)})
    except Exception as e:
        checks.append({"neo4j": False, "error": str(e)})

    # 2) ENDPOINTS presence (no calls yet)
    needed = [
        "ATUNE_ROUTE",
        "ATUNE_ESCALATE",
        "NOVA_PROPOSE",
        "NOVA_EVALUATE",
        "NOVA_AUCTION",
        "SIMULA_JOBS_CODEGEN",
        "EQUOR_ATTEST",
    ]
    present = {name: hasattr(ENDPOINTS, name) for name in needed}
    checks.append({"endpoints_present": present})

    # 3) Deep probes (non-blocking advisory calls)
    if deep:
        try:
            async with await get_http_client() as http:
                # Atune escalate (advisory)
                if present["ATUNE_ESCALATE"]:
                    r = await http.post(
                        ENDPOINTS.ATUNE_ESCALATE,
                        json={"note": "evo.diag", "dry_run": True},
                    )
                    checks.append({"atune_escalate": r.status_code // 100 == 2})
                # Nova propose
                if present["NOVA_PROPOSE"]:
                    brief = {
                        "brief_id": "diag",
                        "source": "evo",
                        "problem": "diag",
                        "context": {},
                        "constraints": {},
                        "success": {},
                    }
                    r = await http.post(ENDPOINTS.NOVA_PROPOSE, json=brief)
                    checks.append({"nova_propose": r.status_code // 100 == 2})
                # Simula codegen validate
                if present["SIMULA_JOBS_CODEGEN"]:
                    r = await http.post(
                        ENDPOINTS.SIMULA_JOBS_CODEGEN,
                        json={"patch_diff": "", "validate": True},
                    )
                    checks.append({"simula_codegen": r.status_code // 100 == 2})
                # Equor attest
                if present["EQUOR_ATTEST"]:
                    r = await http.post(
                        ENDPOINTS.EQUOR_ATTEST,
                        json={"agent": "evo", "capability": "publish_bid", "diagnostic": True},
                    )
                    checks.append({"equor_attest": r.status_code // 100 == 2})
        except Exception as e:
            checks.append({"deep_probe_error": str(e)})

    _stamp_cost(response, t0)
    return {
        "ok": all(
            v is True or (isinstance(v, dict) and all(v.values()))
            for c in checks
            for v in c.values()
            if isinstance(v, bool | dict)
        ),
        "checks": checks,
    }
