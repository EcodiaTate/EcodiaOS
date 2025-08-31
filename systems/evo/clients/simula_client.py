from __future__ import annotations

from typing import Any

from core.utils.net_api import ENDPOINTS, get_http_client


class SimulaClient:
    """
    Uses Simula endpoints only (no guesses):
      - POST /simula/jobs/codegen
      - POST /simula/historical-replay
    """

    async def generate_patch_from_hypothesis(
        self,
        *,
        hypothesis_title: str,
        hypothesis_rationale: str,
        decision_id: str,
    ) -> dict[str, Any]:
        payload = {"spec": f"{hypothesis_title}\n\n{hypothesis_rationale}", "targets": []}
        http = await get_http_client()
        r = await http.post(
            ENDPOINTS.SIMULA_JOBS_CODEGEN,
            json=payload,
            headers={"x-decision-id": decision_id},
        )
        r.raise_for_status()
        data = r.json() or {}
        return {"patch_diff": data.get("patch_diff", data.get("diff", ""))}

    async def test_patch(self, patch_diff: str) -> dict[str, Any]:
        payload = {"patch_diff": patch_diff}
        http = await get_http_client()
        if hasattr(ENDPOINTS, "SIMULA_HISTORICAL_REPLAY"):
            r = await http.post(ENDPOINTS.SIMULA_HISTORICAL_REPLAY, json=payload)
        else:
            r = await http.post(
                ENDPOINTS.SIMULA_JOBS_CODEGEN,
                json={"patch_diff": patch_diff, "validate": True},
            )
        r.raise_for_status()
        return r.json() or {}
