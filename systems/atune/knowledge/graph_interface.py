# systems/atune/knowledge/graph_interface.py


from core.utils.neo.cypher_query import cypher_query


class KnowledgeGraphInterface:
    """
    Provides an API for Atune to interact with the Neo4j knowledge graph,
    specifically for fetching node embeddings and topological data for SFKG.
    """

    async def get_node_embeddings(self, node_ids: list[str]) -> dict[str, list[float]]:
        """

        Fetches the vector embeddings for a given list of node UIDs.
        """
        if not node_ids:
            return {}

        # This query assumes nodes have an 'embedding' property of consistent dimensionality.
        # It is a direct dependency on the core database utility.
        query = """
        UNWIND $node_ids AS node_id
        MATCH (n {uuid: node_id})
        WHERE n.embedding IS NOT NULL
        RETURN n.uuid AS node_id, n.embedding AS embedding
        """
        params = {"node_ids": node_ids}
        records = await cypher_query(query, params)

        return {rec["node_id"]: rec["embedding"] for rec in records}

    async def get_adjacency_list(self, node_ids: list[str]) -> dict[str, list[str]]:
        """
        For a given set of nodes, returns their direct neighbors (1-hop).
        This is required for the diffusion step in the Salience Field Manager.
        """
        if not node_ids:
            return {}

        query = """
        UNWIND $node_ids AS node_id
        MATCH (n {uuid: node_id})-[r]-(neighbor)
        RETURN n.uuid AS source_node, collect(DISTINCT neighbor.uuid) AS neighbors
        """
        params = {"node_ids": node_ids}
        records = await cypher_query(query, params)

        return {rec["source_node"]: rec["neighbors"] for rec in records}
