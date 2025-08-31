# core/llm/school_bus

from __future__ import annotations

from core.llm.bus import event_bus
from core.utils.net_api import ENDPOINTS, get_http_client


class LLMService:
    """
    A dedicated, event-driven service that acts as the sole gateway
    to the OS's centralized LLM endpoint. It subscribes to requests on the
    event bus and publishes responses, decoupling all other systems from
    the underlying HTTP infrastructure.
    """

    async def initialize(self):
        """Subscribes the service to the event bus."""
        event_bus.subscribe("llm_call_request", self.handle_llm_request)

    async def handle_llm_request(self, call_id: str, llm_payload: dict):
        """
        Handles an incoming LLM request event from the bus.
        """
        print(f"[LLMService] Received request {call_id}")
        client = await get_http_client()
        response_data = {}
        try:
            resp = await client.post(ENDPOINTS.LLM_CALL, json=llm_payload)
            resp.raise_for_status()
            response_data = {"status": "success", "content": resp.json()}
        except Exception as e:
            print(f"[LLMService] ERROR during LLM call for {call_id}: {e}")
            response_data = {"status": "error", "content": str(e)}

        # Publish the result back to the bus on a response topic.
        await event_bus.publish(event_type=f"llm_call_response:{call_id}", response=response_data)


# In your main application startup, you would initialize this service:
# llm_service = LLMService()
# await llm_service.initialize()
