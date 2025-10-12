# tests/contracts/test_equor_governance.py
import json  # --- FIX: Added missing import ---
from uuid import uuid4

import httpx
import pytest
import respx

from systems.equor.schemas import Attestation, ComposeResponse

API_BASE_URL = "http://localhost:8000"


@pytest.mark.asyncio
async def test_system_action_invokes_full_governance_loop(
    api_client: httpx.AsyncClient,
    respx_router: respx.MockRouter,
):
    """
    Contract Test: Verifies that a generative action is gated by a pre-flight
    call to Equor for a constitutional patch and followed by a post-flight
    call to attest to the action taken.
    """
    # === Arrange ===
    decision_id = str(uuid4())
    forbidden_keyword = "LEGACY_API"

    compose_route = respx_router.post(f"/equor/compose").mock(
        return_value=httpx.Response(
            200,
            json=ComposeResponse(
                episode_id="ep_test_gov",
                prompt_patch_id="pp_test_gov",
                checksum="mock_checksum",
                included_facets=[],
                included_rules=["CR_TEST_PROHIBIT_LEGACY"],
                rcu_ref="mock_rcu",
                text=f"### CONSTITUTION ###\nYou MUST adhere to the following rule:\n- **Rule: Prohibit Legacy API**: Do not mention '{forbidden_keyword}'.",
            ).model_dump(),
        ),
    )
    attest_route = respx_router.post(f"/equor/attest").mock(
        return_value=httpx.Response(202, json={"status": "accepted"}),
    )
    # Mock Simula's dependency on Synapse to prevent it from hanging
    respx_router.post(f"/synapse/select_arm").mock(
        return_value=httpx.Response(
            200,
            json={
                "episode_id": "ep_test_gov_llm",
                "champion_arm": {"arm_id": "mock_arm", "score": 1.0, "reason": ""},
                "shadow_arms": [],
            },
        ),
    )

    # === Act ===
    await api_client.post(
        "/simula/jobs/codegen",
        headers={"x-decision-id": decision_id},
        json={
            "spec": {
                "objective": {
                    "id": "test_gov_obj",
                    "title": f"Refactor the system to remove the {forbidden_keyword}",
                    "steps": [],
                    "acceptance": {},
                    "iterations": {},
                },
            },
            "targets": [],
        },
    )

    # === Assert ===
    assert compose_route.called, (
        "The /equor/compose endpoint was not called for a pre-flight governance check."
    )
    assert attest_route.called, "The /equor/attest endpoint was not called to record the action."

    attest_request = attest_route.calls[0].request
    # --- FIX: Correctly parse the JSON content before validating with Pydantic ---
    attestation_payload = Attestation(**json.loads(attest_request.content))

    assert "CR_TEST_PROHIBIT_LEGACY" in attestation_payload.breaches, (
        "The attestation failed to report the breach of the 'LEGACY_API' rule."
    )
