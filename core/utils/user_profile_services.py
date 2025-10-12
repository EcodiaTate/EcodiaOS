# core/services/user_profile_service.py
import json
from typing import Any, Dict, List

from core.prompting.orchestrator import build_prompt
from core.utils.llm_gateway_client import call_llm_service
from core.utils.neo.cypher_query import cypher_query
from core.utils.net_api import ENDPOINTS, get_http_client


async def _summarize_trajectory(exchanges: list[dict[str, str]]) -> str:
    """Uses an LLM to analyze the emotional arc of a conversation history."""
    if len(exchanges) < 3:
        return "The relationship is just beginning."

    summary = ""
    try:
        history_text = "\n".join(
            [f"User: {e.get('user', '')}\nEcodia: {e.get('ecodia', '')}" for e in exchanges],
        )

        prompt_data = await build_prompt(
            scope="voxis.trajectory_analysis.v1",
            context={"conversation_history": history_text},
            summary="Analyze the emotional trajectory of the provided conversation history.",
        )

        # Call the gateway
        llm_resp = await call_llm_service(
            prompt_response=prompt_data,
            agent_name="Ecodia.Analyst",
            scope="voxis.trajectory_analysis.v1",
        )

        # Prefer structured json → fallback to text parse
        analysis_content = None
        payload = getattr(llm_resp, "json", None)
        if isinstance(payload, dict):
            analysis_content = payload.get("analysis")

        if analysis_content is None:
            text = getattr(llm_resp, "text", "") or ""
            try:
                from core.llm.utils import extract_json_block

                block = extract_json_block(text or "")
                parsed = json.loads(block) if block else {}
            except Exception:
                parsed = {}
            if isinstance(parsed, dict):
                analysis_content = parsed.get("analysis")

        if isinstance(analysis_content, dict):
            summary = ", ".join(f"{k}: {v}" for k, v in analysis_content.items())
        elif isinstance(analysis_content, str):
            summary = analysis_content.strip()

    except Exception as e:
        print(f"[UserProfileService] Trajectory summarization failed: {e}")
        return "Could not analyze the emotional trajectory at this time."

    return summary if summary else "No summary could be generated."


async def get_user_profile(soul_event_id: str, limit: int = 15) -> dict[str, Any]:
    """
    Retrieves a user's history and generates an LLM-powered summary of their emotional trajectory.
    """
    query = """
    MATCH (sp:SoulNode {event_id: $soul_event_id})
    OPTIONAL MATCH (sp)-[:RESPONSE_FOR]->(r:SoulResponse)<-[:GENERATES]-(i:SoulInput)
    WITH r, i, sp ORDER BY r.timestamp ASC
    WITH sp, COLLECT({user: i.text, ecodia: r.text}) AS all_exchanges
    RETURN size(all_exchanges) AS count, all_exchanges[-$limit..] AS recent
    """
    params = {"soul_event_id": soul_event_id, "limit": limit}
    results = await cypher_query(query, params)

    if not results:
        return {
            "summary": "New interaction.",
            "emotional_trajectory": "N/A",
            "recent_exchanges": [],
        }

    record = results[0]
    recent_exchanges = record.get("recent", [])

    # Generate the emotional summary
    emotional_summary = await _summarize_trajectory(recent_exchanges)

    return {
        "summary": f"User has an interaction history of {record.get('count', 0)} turns.",
        "emotional_trajectory": emotional_summary,
        "recent_exchanges": recent_exchanges,
    }
