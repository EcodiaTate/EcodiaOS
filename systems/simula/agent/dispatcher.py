# systems/simula/agent/dispatcher.py
# --- UNIFIED TOOL DISPATCHER FOR SIMULA ---

from __future__ import annotations

import logging
from typing import Any, Dict

from systems.simula.code_sim.telemetry import get_tracked_tools

log = logging.getLogger(__name__)

# --- Load all tools (via @track_tool in agent_tools) ---
TOOL_MAP: dict[str, Any] = get_tracked_tools()
_SIMULA_PREFIX = "simula.agent."


def _resolve_tool_from_arm_id(arm_id: str) -> str | None:
    """
    Accepts arm IDs like 'simula.agent.run_tests.v1' and returns the tool key ('run_tests').
    """
    # Direct match
    if arm_id in TOOL_MAP:
        return arm_id
    # Remove prefix and extract base name
    if arm_id.startswith(_SIMULA_PREFIX):
        # Handle both "simula.agent.tool_name" and "simula.agent.tool_name.v1" formats
        tail = arm_id[len(_SIMULA_PREFIX) :]
        tool_key = tail.split(".", 1)[0]
        if tool_key in TOOL_MAP:
            return tool_key
    # Final check for direct tool name match if all else fails
    if arm_id in TOOL_MAP:
        return arm_id
    return None


async def dispatch_tool(arm_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """
    Dispatches a tool by resolving the arm ID and calling the registered function.
    """
    tool_key = _resolve_tool_from_arm_id(arm_id)

    if not tool_key or tool_key not in TOOL_MAP:
        log.error("Unknown tool for arm_id '%s'. Registry has: %s", arm_id, list(TOOL_MAP.keys()))
        return {"status": "error", "reason": f"Tool '{tool_key or arm_id}' not found in registry."}

    # The tool_meta object is the dictionary containing the function and metadata.
    tool_meta = TOOL_MAP[tool_key]

    # FIXED: The error was trying to call the metadata dict instead of the function inside it.
    # We must extract the actual callable function from the 'func' key.
    tool_fn = tool_meta.get("func")

    if not callable(tool_fn):
        log.error(
            "Tool '%s' resolved but its 'func' attribute is not a callable function.", tool_key
        )
        return {"status": "error", "reason": f"Tool '{tool_key}' is not configured correctly."}

    try:
        # Now we are correctly calling the function object.
        return await tool_fn(**(params or {}))
    except Exception as e:
        log.exception("Tool '%s' crashed during execution", tool_key)
        return {"status": "error", "reason": f"Tool '{tool_key}' crashed: {e!r}"}
