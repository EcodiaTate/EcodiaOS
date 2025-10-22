# systems/voxis/runtime/agent.py
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any, Dict, List, Optional

ToolFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class Tool:
    def __init__(
        self,
        name: str,
        desc: str,
        schema: dict[str, Any],
        fn: ToolFn,
        timeout_s: float = 15.0,
    ):
        self.name = name
        self.desc = desc
        self.schema = schema
        self.fn = fn
        self.timeout_s = timeout_s


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        return self._tools[name]

    def list_specs(self) -> list[dict[str, Any]]:
        return [
            {"name": t.name, "description": t.desc, "parameters": t.schema}
            for t in self._tools.values()
        ]


class VoxisAgent:
    """
    LLM-orchestrated agent that can call tools via function/tool-calling.
    Expected llm client interface:
      await llm.complete(messages=[...], tools=[...], tool_choice="auto", stream=False)
      -> returns an object with:
         - type: "tool_call" | "final"
         - if tool_call: .name, .id, .arguments (dict)
         - if final: .text
    """

    def __init__(self, llm_client, tools: ToolRegistry):
        self.llm = llm_client
        self.tools = tools

    async def _exec_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        tool = self.tools.get(name)
        start = time.perf_counter()
        try:
            res = await asyncio.wait_for(tool.fn(args), timeout=tool.timeout_s)
            ok = True
            return {
                "ok": ok,
                "latency_ms": int((time.perf_counter() - start) * 1000),
                "result": res,
            }
        except Exception as e:
            return {
                "ok": False,
                "latency_ms": int((time.perf_counter() - start) * 1000),
                "error": str(e),
            }

    async def chat(self, user_msg: str, system_prompt: str = "") -> str:
        msgs = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_msg}]
        tools = self.tools.list_specs()

        thought = await self.llm.complete(
            messages=msgs,
            tools=tools,
            tool_choice="auto",
            stream=False,
        )

        # Loop until the model returns a final answer
        while getattr(thought, "type", None) == "tool_call":
            tname: str = thought.name
            targs: dict[str, Any] = thought.arguments if isinstance(thought.arguments, dict) else {}
            tool_call_id: str = getattr(thought, "id", "tool-call")

            # Execute tool
            outcome = await self._exec_tool(tname, targs)

            # Provide tool call + tool result back to the LLM
            msgs += [
                {
                    "role": "assistant",
                    "tool_call_id": tool_call_id,
                    "name": tname,
                    "content": json.dumps(targs),
                },
                {"role": "tool", "tool_call_id": tool_call_id, "content": json.dumps(outcome)},
            ]
            thought = await self.llm.complete(
                messages=msgs,
                tools=tools,
                tool_choice="auto",
                stream=False,
            )

        return getattr(thought, "text", "")
