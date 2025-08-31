# systems/atune/memory/induction.py
from __future__ import annotations

import json
import uuid
from collections import defaultdict

import numpy as np

from core.prompting.orchestrator import PolicyHint, build_prompt
from core.utils.net_api import ENDPOINTS, get_http_client
from systems.atune.memory.schemas import Schema
from systems.atune.memory.store import MemoryStore


class SchemaInducer:
    """
    Periodic offline job:
    1) clusters FocusNodes by embedding
    2) names each significant cluster with a short abstract 'schema' label
    """

    async def _name_cluster_via_prompt(self, node_summaries: list[str]) -> str:
        """
        Uses the spec-based prompting system to produce {"schema_name": "<short_label>"}.
        Falls back to a random name on any failure.
        """
        # 1) Render messages via PromptSpec (no stray prompt strings)
        hint = PolicyHint(
            scope="atune.schema.naming",
            task_key="schema_naming",  # enables Synapse budget flow
            summary=f"Name a cluster of {min(len(node_summaries), 10)} related events",
            context={
                # Template variables for the spec/template
                "vars": {"summaries": node_summaries[:10]},
            },
        )
        o = await build_prompt(hint)

        # 2) Call LLM Bus with provider overrides + provenance headers
        client = await get_http_client()
        body = {
            "messages": o.messages,
            "json_mode": bool(o.provider_overrides.get("json_mode", True)),
            "max_tokens": int(o.provider_overrides.get("max_tokens", 64)),
        }
        temp = o.provider_overrides.get("temperature", None)
        if temp is not None:
            body["temperature"] = float(temp)

        headers = {
            "x-budget-ms": str(o.provenance.get("budget_ms", 1000)),
            "x-spec-id": o.provenance.get("spec_id", ""),
            "x-spec-version": o.provenance.get("spec_version", ""),
        }

        try:
            resp = await client.post(ENDPOINTS.LLM_CALL, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json() or {}
            payload = data.get("json")
            if not payload and data.get("text"):
                try:
                    payload = json.loads(data["text"])
                except Exception:
                    payload = {}

            if isinstance(payload, dict):
                name = payload.get("schema_name")
                if isinstance(name, str) and name.strip():
                    return name.strip()

            # Fallback
            return f"unnamed_schema_{uuid.uuid4()}"
        except Exception as e:
            print(f"SchemaInducer: LLM call for naming failed: {e}")
            return f"unnamed_schema_{uuid.uuid4()}"

    async def run_induction_cycle(self, node_store: MemoryStore) -> list[Schema]:
        """
        Executes a full induction cycle: fetch nodes, cluster them by embedding,
        and generate a named schema for each significant cluster.
        """
        nodes = node_store.get_all_nodes()
        if len(nodes) < 10:  # Don't run on too few experiences
            return []

        embeddings = np.array([n.text_embedding for n in nodes], dtype=np.float32)

        # Simple leader-follower clustering
        clusters: dict[int, list[int]] = defaultdict(list)
        cluster_leaders: list[np.ndarray] = []
        cluster_threshold = 0.8  # cosine similarity threshold

        for i, (node, emb) in enumerate(zip(nodes, embeddings)):
            if not cluster_leaders:
                cluster_leaders.append(emb)
                clusters[0].append(i)
                continue

            sims = np.dot(cluster_leaders, emb) / (
                np.linalg.norm(cluster_leaders, axis=1) * np.linalg.norm(emb)
            )
            best = int(np.argmax(sims))
            if float(sims[best]) > cluster_threshold:
                clusters[best].append(i)
            else:
                cluster_leaders.append(emb)
                clusters[len(cluster_leaders) - 1].append(i)

        new_schemas: list[Schema] = []
        for cluster_id, node_indices in clusters.items():
            if len(node_indices) < 3:  # ignore tiny clusters
                continue

            cluster_nodes = [nodes[i] for i in node_indices]
            cluster_embeddings = np.array(
                [n.text_embedding for n in cluster_nodes],
                dtype=np.float32,
            )

            # Build human-readable summaries for naming
            summaries = [
                f"Event {n.source_event_id} used plan '{n.final_plan_mode}'" for n in cluster_nodes
            ]

            schema_name = await self._name_cluster_via_prompt(summaries)

            # Aggregate priors
            salience_priors = defaultdict(list)
            utility_priors = []
            for node in cluster_nodes:
                for head, score in node.salience_vector.items():
                    salience_priors[head].append(score)
                utility_priors.append(node.fae_score)  # using FAE as proxy for utility

            new_schema = Schema(
                schema_id=f"schema_{uuid.uuid4()}",
                schema_name=schema_name,
                centroid_embedding=np.mean(cluster_embeddings, axis=0).tolist(),
                member_node_ids=[n.node_id for n in cluster_nodes],
                salience_priors={k: float(np.mean(v)) for k, v in salience_priors.items()},
                fae_utility_prior=float(np.mean(utility_priors) if utility_priors else 0.0),
            )
            new_schemas.append(new_schema)

        return new_schemas
