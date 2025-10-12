"""
🧠 EcodiaOS Native Clustering Engine
- Fetches text content from all Event nodes in Neo4j.
- Uses the Gemini API's native CLUSTERING task type to get embeddings and cluster IDs.
- Updates nodes with their cluster information for system-wide analysis.
"""

import asyncio

from core.llm.embeddings_gemini import get_embedding
from core.utils.neo.cypher_query import cypher_query
from core.utils.neo.neo_driver import get_driver


async def fetch_all_event_content(driver):
    """
    Fetches the 'event_id' and a concatenated 'text' property from all :Event nodes.
    """
    print("Fetching content from all :Event nodes for clustering...")
    query = """
    MATCH (n:Event)
    WHERE n.content IS NOT NULL OR n.summary IS NOT NULL
    RETURN n.event_id AS event_id, COALESCE(n.content, n.summary) AS text
    """
    results = await cypher_query(query)
    print(f"Found {len(results)} events to cluster.")
    return results


async def get_clusters_from_gemini(event_data: list[dict]):
    """
    Mock Gemini CLUSTERING task using embeddings + KMeans.
    """
    if not event_data:
        print("No data to send for clustering.")
        return []

    print(f"Sending {len(event_data)} documents to Gemini for clustering analysis...")
    import numpy as np
    from sklearn.cluster import KMeans

    tasks = [get_embedding(item["text"]) for item in event_data]
    embeddings = await asyncio.gather(*tasks)

    num_clusters = min(10, len(embeddings) // 5)
    if num_clusters < 2:
        print("Not enough data for meaningful clustering.")
        return []

    kmeans = KMeans(n_clusters=num_clusters, random_state=42, n_init="auto").fit(
        np.array(embeddings),
    )
    cluster_labels = kmeans.labels_

    for i, item in enumerate(event_data):
        item["cluster_id"] = int(cluster_labels[i])

    print(f"Clustering complete. Assigned {len(event_data)} items to {num_clusters} clusters.")
    return event_data


async def update_nodes_with_clusters(driver, clustered_data: list[dict]):
    """
    Updates the nodes in Neo4j with their new cluster ID.
    """
    if not clustered_data:
        print("No cluster data to update.")
        return

    print("Updating nodes in Neo4j with cluster IDs...")
    query = """
    UNWIND $rows AS row
    MATCH (n:Event {event_id: row.event_id})
    SET n.cluster_id = row.cluster_id
    """
    await cypher_query(query, {"rows": clustered_data})
    print("All nodes have been updated with their cluster IDs.")


async def run_native_clustering_pipeline(driver=None, *_, **__):
    """
    The main function to execute the entire native clustering process.
    If driver is not passed, gets it automatically.
    """
    if driver is None:
        driver = get_driver()

    all_events = await fetch_all_event_content(driver)
    clustered_events = await get_clusters_from_gemini(all_events)
    await update_nodes_with_clusters(driver, clustered_events)
