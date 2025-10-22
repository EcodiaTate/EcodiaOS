# systems/axon/loop/bridge.py
from __future__ import annotations

import asyncio
import logging

from core.llm.bus import event_bus
from core.utils.net_api import ENDPOINTS, get_http_client
from systems.axon.schemas import AxonEvent

# --- Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("Axon.Bridge")

AXON_EVENT_TOPIC = "axon.event"


async def forward_event_to_atune(event_payload: dict) -> None:
    """
    Takes a payload from the 'axon.event' bus topic, validates it as an
    AxonEvent, and forwards it to the Atune /route endpoint via HTTP.
    """
    try:
        # The bus payload is the full AxonEvent object
        axon_event = AxonEvent.model_validate(event_payload)
        logger.info(
            f"[Bridge] Forwarding event {axon_event.event_id} from source '{axon_event.source}' to Atune.",
        )

        client = await get_http_client()
        response = await client.post(
            ENDPOINTS.ATUNE_ROUTE,
            json=axon_event.model_dump(mode="json"),
            headers={"x-budget-ms": "1500"},
            timeout=10.0,
        )
        response.raise_for_status()
        logger.info(
            f"[Bridge] Successfully forwarded event {axon_event.event_id}. Atune response: {response.status_code}",
        )

    except Exception as e:
        logger.error(f"[Bridge] Failed to forward event to Atune: {e}", exc_info=True)


async def run_bridge_service():
    """
    Initializes and runs the Axon->Atune bridge service.
    """
    logger.info(f"🚀 [Axon Bridge] Starting and subscribing to topic '{AXON_EVENT_TOPIC}'...")

    unsubscribe_handle = event_bus.subscribe(AXON_EVENT_TOPIC, forward_event_to_atune)

    try:
        await asyncio.Future()  # Keep the service alive indefinitely
    finally:
        logger.info("🔌 [Axon Bridge] Shutting down and unsubscribing...")
        unsubscribe_handle()


if __name__ == "__main__":

    async def main():
        print("--- Running Axon Event Bridge in standalone mode ---")
        print(f"--- Listening for events on topic: '{AXON_EVENT_TOPIC}' ---")
        print(
            "--- This service will forward any published Axon events to Atune. Press Ctrl+C to exit. ---",
        )

        await run_bridge_service()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n--- [Axon Bridge] Shutdown requested by user. ---")
