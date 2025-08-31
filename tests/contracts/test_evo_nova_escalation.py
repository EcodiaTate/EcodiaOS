# tests/contracts/test_evo_nova_escalation.py
import pytest
import httpx
import respx
from uuid import UUID

from systems.evo.schemas import ConflictNode, EscalationResult

# The base URL of the API service inside the Docker network
API_BASE_URL = "http://localhost:8000"

@pytest.mark.asyncio
async def test_evo_escalates_to_nova_market_triplet(respx_router):
    """
    Contract Test: Verifies that Evo's escalate endpoint correctly
    triggers the Nova propose -> evaluate -> auction sequence.
    """
    # === Arrange ===
    conflict_id = "conflict_test_001"
    decision_id = ""

    # 1. Mock the Nova endpoints to intercept Evo's calls.
    # We can inspect these mock routes later to see what was called.
    propose_route = respx_router.post(f"{API_BASE_URL}/nova/propose").mock(
        return_value=httpx.Response(200, json=[
            {"candidate_id": "cand_1", "playbook": "test.playbook", "brief_id": "brief_1"}
        ])
    )
    evaluate_route = respx_router.post(f"{API_BASE_URL}/nova/evaluate").mock(
        return_value=httpx.Response(200, json=[
            {"candidate_id": "cand_1", "playbook": "test.playbook", "brief_id": "brief_1", "evaluations": [{"ok": True}]}
        ])
    )
    auction_route = respx_router.post(f"{API_BASE_URL}/nova/auction").mock(
        return_value=httpx.Response(200, json={
            "winners": ["cand_1"],
            "market_receipt": {"hash": "mock_receipt_hash"}
        })
    )

    # === Act ===
    # Trigger the escalation in the running Evo service.
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_BASE_URL}/evo/escalate",
            json={"conflict_ids": [conflict_id]}
        )
        response.raise_for_status()
        result = EscalationResult(**response.json())
        decision_id = result.decision_id

    # === Assert ===
    # 1. Verify the Nova endpoints were called in the correct sequence.
    assert propose_route.called, "Evo did not call Nova's /propose endpoint."
    assert evaluate_route.called, "Evo did not call Nova's /evaluate endpoint."
    assert auction_route.called, "Evo did not call Nova's /auction endpoint."

    # 2. Inspect the /propose request for contract adherence.
    propose_call = propose_route.calls[0]
    propose_request = propose_call.request
    propose_body = propose_request.content.decode("utf-8")

    # Assert that the mandatory X-Decision-Id header was propagated.
    assert "x-decision-id" in propose_request.headers
    assert propose_request.headers["x-decision-id"] == decision_id, \
        "The decision_id was not correctly passed to Nova."

    # Validate UUID format
    assert UUID(decision_id, version=4)

    # Assert the request body contains the correct conflict data.
    assert f'"conflict_ids": ["{conflict_id}"]' in propose_body.replace(" ", ""), \
        "The InnovationBrief sent to Nova did not contain the correct conflict_id."

    # 3. Verify the final result from Evo is valid.
    assert result.status == "success"
    assert len(result.nova_auction_result.winners) > 0, "Evo's final result did not include a winner from the Nova auction."
    assert result.nova_auction_result.market_receipt["hash"] == "mock_receipt_hash"