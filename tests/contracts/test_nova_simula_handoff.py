# tests/contracts/test_nova_simula_handoff.py
from uuid import uuid4

import httpx
import pytest
import respx

from systems.nova.schemas import AuctionResult, InnovationBrief, InventionCandidate
from systems.nova.types.patch import SimulaPatchBrief

API_BASE_URL = "http://localhost:8000"


@pytest.mark.asyncio
async def test_nova_winner_handoff_to_simula(
    api_client: httpx.AsyncClient,
    respx_router: respx.MockRouter,
):
    """
    Contract Test: Verifies that Nova's winner pipeline correctly
    formulates and submits a codegen job to Simula.
    """
    # === Arrange ===
    decision_id = str(uuid4())
    brief_id = "brief_nova_sim_001"
    winner_candidate_id = "cand_winner_001"

    # 1. Define the inputs for Nova's winner pipeline.
    brief = InnovationBrief(
        brief_id=brief_id,
        source="evo",
        problem="Refactor legacy authentication module.",
        context={"files": ["systems/legacy/auth.py"]},
        constraints={"max_complexity": 10},
        success={"tests_pass": ["tests/test_auth.py"]},
    )
    winner_candidate = InventionCandidate(
        candidate_id=winner_candidate_id,
        playbook="dreamcoder.library",
        brief_id=brief_id,
        steps=[{"tool": "apply_diff", "args": {"diff": "..."}}],
    )
    auction_result = AuctionResult(winners=[winner_candidate_id], market_receipt={})

    # 2. Mock the Simula /jobs/codegen endpoint to intercept the handoff.
    simula_codegen_route = respx_router.post(f"/simula/jobs/codegen").mock(
        return_value=httpx.Response(200, json={"ticket_id": "sim_ticket_123"}),
    )

    # === Act ===
    # Call the Nova endpoint that triggers the handoff to Simula.
    # This is more robust than a unit test as it tests the full API contract.
    response = await api_client.post(
        "/nova/winner/submit",
        headers={"x-decision-id": decision_id},
        json={
            "brief": brief.model_dump(),
            "candidates": [winner_candidate.model_dump()],
            "auction": auction_result.model_dump(),
        },
    )
    response.raise_for_status()

    # === Assert ===
    # 1. Verify that Simula's endpoint was actually called.
    assert simula_codegen_route.called, (
        "Nova did not submit a job to Simula's /jobs/codegen endpoint."
    )

    # 2. Inspect the request sent to Simula to verify the contract.
    simula_request = simula_codegen_route.calls[0].request
    simula_body = simula_request.content.decode("utf-8")

    # Assert the X-Decision-Id header was correctly propagated for end-to-end tracing.
    assert simula_request.headers["x-decision-id"] == decision_id

    # Assert the body conforms to Simula's expected `CodegenRequest` shape.
    assert '"spec":' in simula_body
    assert '"targets":' in simula_body

    # 3. Assert the content of the 'spec' was correctly translated into a SimulaPatchBrief.
    # This proves the data contract between Nova and Simula is being met.
    assert f'"brief_id": "{brief_id}"' in simula_body
    assert f'"candidate_id": "{winner_candidate_id}"' in simula_body
    assert f'"problem": "{brief.problem}"' in simula_body
