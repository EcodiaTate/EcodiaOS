from typing import Any

from fastapi import APIRouter, HTTPException

from core.utils.neo.cypher_query import cypher_query  # ✅ driverless

mood_router = APIRouter()


@mood_router.get("/interface_mood")
async def get_latest_interface_mood() -> dict[str, Any]:
    """
    Returns the most recent global InterfaceMood node (not user-specific).
    Driverless Neo4j via cypher_query; no direct driver/session usage.
    """
    query = """
    MATCH (m:InterfaceMood)
    RETURN m { .* } AS m
    ORDER BY m.timestamp DESC
    LIMIT 1
    """

    rows = await cypher_query(query, {})
    if not rows:
        raise HTTPException(status_code=404, detail="No InterfaceMood found.")

    props = rows[0].get("m") or {}

    return {
        "bgColor": props.get("bgColor", "#060a07"),
        "fireflyColor": props.get("fireflyColor", "#f4d35e"),
        "shadowColor": props.get("shadowColor", "#f4d35e"),
        "motionIntensity": props.get("motionIntensity", 0.3),
    }
