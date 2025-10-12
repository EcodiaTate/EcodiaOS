# systems/synapse/genesis/tool_genesis_module.py
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Dict

from core.llm.bus import event_bus
from core.llm.utils import extract_json_block
from core.prompting.orchestrator import build_prompt
from core.prompting.validators import load_schema, validate_json
from core.utils.neo.cypher_query import cypher_query
from systems.qora.client import fetch_llm_tools  # Qora catalog (LLM-ready tool specs)
from systems.synk.core.switchboard.gatekit import gated_loop

GENESIS_SCHEMA_PATH = "core/prompting/schemas/genesis_tool_specification_output.json"


class ToolGenesisModule:
    """
    Synapse's tool genesis engine (spec-first).
    - Builds prompt via central orchestrator (PromptSpec).
    - Shows Qora tool catalog to discourage duplicate tools.
    - Validates spec JSON before commissioning.
    """

    _instance: ToolGenesisModule | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def _request_llm_spec(self, task_key: str) -> dict[str, Any]:
        """
        Build spec-typed prompt and request an LLM response via the event bus.
        Expects a dict (validated later).
        """
        call_id = str(uuid.uuid4())
        response_event = f"llm_call_response:{call_id}"
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()

        def on_response(response: dict[str, Any]) -> None:
            if not future.done():
                future.set_result(response)

        # Subscribe for this specific LLM call's response
        event_bus.subscribe(response_event, on_response)

        # Pull live Qora catalog so model avoids duplicates and reuses affordances
        try:
            tools_manifest = await fetch_llm_tools(agent="Synapse", safety_max=2)
        except Exception:
            tools_manifest = []

        prompt = await build_prompt(
            scope="synapse.genesis_tool_specification",
            summary=f"Design a tool for persistent failure on task '{task_key}'",
            context={
                # if your prompt partials expect {{ task_key }}, keep it here:
                "vars": {"task_key": task_key},
                # rendered by partials/tools_manifest.j2 when present
                "tools_manifest": tools_manifest,
            },
        )

        llm_payload: dict[str, Any] = {
            "messages": prompt.messages,
            "json_mode": bool(prompt.provider_overrides.get("json_mode", True)),
            "max_tokens": int(prompt.provider_overrides.get("max_tokens", 700)),
            # omit 'model' to allow LLM Bus routing
        }
        temp = prompt.provider_overrides.get("temperature")
        if temp is not None:
            llm_payload["temperature"] = float(temp)

        headers = {
            "x-budget-ms": str(prompt.provenance.get("budget_ms", 2000)),
            "x-spec-id": prompt.provenance.get("spec_id", ""),
            "x-spec-version": prompt.provenance.get("spec_version", ""),
        }

        # Publish request to the LLM Bus through the event bus
        print(f"[Genesis] Publishing 'llm_call_request' via orchestrator with ID: {call_id}")
        await event_bus.publish(
            event_type="llm_call_request",
            call_id=call_id,
            llm_payload=llm_payload,
            extra_headers=headers,
        )

        # Wait for response
        resp: dict[str, Any] = await asyncio.wait_for(future, timeout=120.0)

        # Normalize result into a dict
        content: Any = resp.get("json") or resp.get("content") or {}
        if not content and isinstance(resp.get("text"), str):
            text = resp["text"]
            # Prefer fenced/inline JSON block if present
            block = extract_json_block(text)
            try:
                content = json.loads(block if block else text)
            except Exception:
                content = {}

        return content if isinstance(content, dict) else {}

    async def run_genesis_cycle(self) -> None:
        """
        One genesis pass: find a stubborn failure → request tool spec → validate → commission.
        """
        print("[Genesis] Starting genesis cycle: analyzing for capability gaps...")
        query = """
        MATCH (e:Episode)
        WITH e.task_key AS task, max(e.reward) AS best_reward
        WHERE best_reward < -0.5
        RETURN task, best_reward
        ORDER BY best_reward ASC
        LIMIT 1
        """
        try:
            failures = await cypher_query(query)
            if not failures:
                return
        except Exception as e:
            print(f"[Genesis] ERROR: Could not query for failures: {e}")
            return

        task_key = failures[0].get("task")
        if not task_key:
            return

        print(f"[Genesis] Capability Gap Identified: Persistent failure on task '{task_key}'.")

        try:
            spec = await self._request_llm_spec(task_key)
        except TimeoutError:
            print(
                f"[Genesis] ERROR: Timed out waiting for LLM spec response for task '{task_key}'."
            )
            return

        # Validate against the canonical schema
        try:
            schema = load_schema(GENESIS_SCHEMA_PATH)
            ok, msg = validate_json(spec, schema)
        except Exception as e:
            ok, msg = False, f"Schema load/validation error: {e}"

        if not ok:
            print(f"[Genesis] ERROR: Generated tool spec failed validation: {msg}")
            return

        print(f"[Genesis] Publishing 'tool_commission_request' for: {spec.get('tool_name')}")
        await event_bus.publish(event_type="tool_commission_request", spec=spec)


async def start_genesis_loop() -> None:
    """
    Daemon runner for the Tool Genesis Module.
    """
    genesis_module = ToolGenesisModule()
    await gated_loop(
        task_coro=genesis_module.run_genesis_cycle,
        enabled_key="synapse.genesis.enabled",
        interval_key="synapse.genesis.interval_sec",
        default_interval=3600,
    )
