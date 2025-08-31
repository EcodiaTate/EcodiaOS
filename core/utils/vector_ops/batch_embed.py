import asyncio
import os

from dotenv import load_dotenv

from core.llm.embeddings_gemini import get_embedding  # ✅ centralized embeddings
from core.utils.neo.cypher_query import cypher_query  # ✅ driverless Neo

BATCH_SIZE = 32
OLD_VECTOR_PROPERTY = "vector_gemini"
NEW_VECTOR_PROPERTY = "vector_gemini"
TEXT_SOURCE_PROPERTY = "COALESCE(n.content, n.summary, n.description, n.name)"


async def fetch_nodes_to_re_embed():
    """
    Driverless: find nodes with OLD_VECTOR set but NEW_VECTOR missing.
    """
    print("Finding nodes that need to be upgraded...")
    query = f"""
    MATCH (n)
    WHERE n.{OLD_VECTOR_PROPERTY} IS NOT NULL AND n.{NEW_VECTOR_PROPERTY} IS NULL
    RETURN n.event_id AS event_id, {TEXT_SOURCE_PROPERTY} AS text
    """
    results = await cypher_query(query, {})
    nodes_to_process = [
        item for item in (results or []) if item.get("event_id") and item.get("text")
    ]
    print(f"Found {len(nodes_to_process)} nodes to re-embed.")
    return nodes_to_process


async def re_embed_batch(batch: list[dict]):
    """
    Compute embeddings for a batch of nodes.
    """
    print(f"Processing a batch of {len(batch)} nodes...")
    texts_to_embed = [item["text"] for item in batch]
    embeddings = await asyncio.gather(
        *[get_embedding(text, task_type="RETRIEVAL_DOCUMENT") for text in texts_to_embed],
    )
    return [{"event_id": node["event_id"], "vector": embeddings[i]} for i, node in enumerate(batch)]


async def update_nodes_in_neo4j(update_data: list[dict]):
    """
    Driverless: write new vectors back into Neo4j.
    """
    if not update_data:
        return
    query = f"""
    UNWIND $rows AS row
    MATCH (n {{event_id: row.event_id}})
    SET n.{NEW_VECTOR_PROPERTY} = row.vector
    """
    await cypher_query(query, {"rows": update_data})
    print(f"Successfully updated {len(update_data)} nodes in the database.")


async def main():
    # Load env for GEMINI_API_KEY/GOOGLE_API_KEY, etc. (path override supported)
    load_dotenv(os.getenv("ENV_FILE") or "D:/EcodiaOS/config/.env")

    nodes_to_process = await fetch_nodes_to_re_embed()
    if not nodes_to_process:
        print("No nodes to update. Your database is already up to date!")
        return

    for i in range(0, len(nodes_to_process), BATCH_SIZE):
        batch = nodes_to_process[i : i + BATCH_SIZE]
        try:
            update_payload = await re_embed_batch(batch)
            await update_nodes_in_neo4j(update_payload)
        except Exception as e:
            print(f"--- ERROR processing batch {i // BATCH_SIZE + 1}: {e!r} ---")
            continue

    print("\n🚀 Batch re-embedding process complete! 🚀")


if __name__ == "__main__":
    asyncio.run(main())
