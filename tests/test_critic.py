from unittest.mock import AsyncMock, patch

import pytest

# Assume a test fixture for managing the prompt registry
from core.prompting.registry import get_registry
from core.prompting.spec import IdentityBlock, PromptSpec

# Assume a test setup allows access to the refactored primitive
from systems.unity.core.primitives.critique import generate_critiques


@pytest.fixture
def setup_critic_spec():
    """A pytest fixture to load a test PromptSpec into the registry."""
    # Create a spec that explicitly uses the new safety facets lens
    spec = PromptSpec(
        id="test_safety_critic_001",
        version="1.0",
        scope="unity.critique.safety.v1",
        identity=IdentityBlock(agent="Unity.SafetyCritic"),
        context_lenses=["facets.safety"],  # We are testing this lens
    )

    # Use a mock registry or a temporary directory for the test
    registry = get_registry()

    # Directly inject the spec for this test
    # In a real scenario, you might write this to a temp YAML file
    # that the registry is configured to scan.
    entry = registry._SpecEntry(spec, source="test_fixture", mtime=0)
    registry._by_scope[spec.scope] = entry

    yield

    # Teardown: remove the spec after the test
    del registry._by_scope[spec.scope]


@pytest.mark.asyncio
@patch("core.utils.llm_gateway_client.call_llm_service", new_callable=AsyncMock)
@patch("core.prompting.lenses.cypher_query", new_callable=AsyncMock)
async def test_generate_critiques_injects_safety_facets(
    mock_cypher_query, mock_llm_call, setup_critic_spec
):
    """
    Verify that when `generate_critiques` is called for the SafetyCritic,
    the `lens_safety_facets` is triggered and its payload appears in the
    final context sent to the prompt renderer.
    """
    # 1. Arrange: Mock the database response for the safety facet query
    mock_facet_data = [
        {
            "name": "Precautionary Principle",
            "text": "When in doubt, prioritize safety.",
            "version": "1.1",
        },
    ]
    mock_cypher_query.return_value = mock_facet_data

    # 2. Arrange: Mock the final LLM call to return a predictable critique
    mock_llm_call.return_value.text = "This is a safety critique."

    # 3. Act: Run the refactored primitive
    proposal = {"content": {"text": "Let's connect to the public internet directly."}}
    panel = ["SafetyCritic"]  # We are only testing this critic

    with patch("core.prompting.runtime.render_prompt", new_callable=AsyncMock) as mock_render:
        # We patch the *final* render step to inspect the context it received.
        # This is the most important assertion.
        mock_render.return_value.messages = [{"role": "user", "content": "Test"}]
        mock_render.return_value.provider_overrides = {}
        mock_render.return_value.provenance = {}

        await generate_critiques(
            deliberation_id="delib_test_123",
            proposal_artifact=proposal,
            panel=panel,
        )

        # 4. Assert: Check that our mocks were called correctly
        # Assert that the DB was queried for the 'safety' category
        mock_cypher_query.assert_called_once_with(
            pytest.ANY,
            {"category": "safety"},
        )

        # Assert that render_prompt was called with the context containing our facets
        render_call_args = mock_render.call_args[1]  # kwargs
        final_context = render_call_args["context_dict"]

        assert "safety_facets" in final_context
        assert len(final_context["safety_facets"]) == 1
        assert final_context["safety_facets"][0]["name"] == "Precautionary Principle"
