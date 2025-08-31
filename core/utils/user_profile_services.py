# core/services/user_profile_service.py

from typing import Any, Dict, List
from core.utils.neo.cypher_query import cypher_query
from core.prompting.orchestrator import PolicyHint, build_prompt
from core.utils.net_api import ENDPOINTS, get_http_client

async def _summarize_trajectory(exchanges: List[Dict[str, str]]) -> str:
    """Uses an LLM to analyze the emotional arc of a conversation history."""
    if len(exchanges) < 3:
        return "The relationship is just beginning."

    try:
        history_text = "\n".join([f"User: {e.get('user', '')}\nEcodia: {e.get('ecodia', '')}" for e in exchanges])
        
        hint = PolicyHint(
            scope="voxis.trajectory_analysis.v1", # Assumes a new PromptSpec for this task
            context={"conversation_history": history_text}
        )
        prompt_data = await build_prompt(hint)

        http = await get_http_client()
        llm_payload = {
            "agent_name": "Ecodia.Analyst",
            "messages": prompt_data.messages,
            "provider_overrides": prompt_data.provider_overrides,
        }
        resp = await http.post(ENDPOINTS.LLM_CALL, json=llm_payload)
        resp.raise_for_status()
        summary = (resp.json().get("text") or "").strip()
        return summary if summary else "No summary could be generated."

    except Exception as e:
        print(f"[UserProfileService] Trajectory summarization failed: {e}")
        return "Could not analyze the emotional trajectory at this time."

async def get_user_profile(phrase_event_id: str, limit: int = 15) -> Dict[str, Any]:
    """
    Retrieves a user's history and generates an LLM-powered summary of their emotional trajectory.
    """
    # ... (The initial query to fetch recent_exchanges remains the same as before) ...
    query = """
    MATCH (sp:SoulPhrase {event_id: $phrase_event_id})
    OPTIONAL MATCH (sp)-[:RESPONSE_FOR]->(r:SoulResponse)<-[:GENERATES]-(i:SoulInput)
    WITH r, i, sp ORDER BY r.timestamp ASC
    WITH sp, COLLECT({user: i.text, ecodia: r.text}) AS all_exchanges
    RETURN size(all_exchanges) AS count, all_exchanges[-$limit..] AS recent
    """
    params = {"phrase_event_id": phrase_event_id, "limit": limit}
    results = await cypher_query(query, params)
    
    if not results:
        return {"summary": "New interaction.", "emotional_trajectory": "N/A", "recent_exchanges": []}

    record = results[0]
    recent_exchanges = record.get("recent", [])
    
    # Generate the emotional summary
    emotional_summary = await _summarize_trajectory(recent_exchanges)
    
    return {
        "summary": f"User has an interaction history of {record.get('count', 0)} turns.",
        "emotional_trajectory": emotional_summary,
        "recent_exchanges": recent_exchanges,
    }