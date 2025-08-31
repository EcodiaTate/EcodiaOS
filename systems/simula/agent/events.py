# Minimal shared topics/constants for Simula’s step loop.

from __future__ import annotations


def llm_tool_response_topic(request_id: str) -> str:
    return f"llm_tool_response:{request_id}"
