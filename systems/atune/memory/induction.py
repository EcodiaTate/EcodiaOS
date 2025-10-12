# systems/atune/memory/induction.py
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from typing import Optional

import numpy as np

from core.prompting.orchestrator import build_prompt
from core.utils.llm_gateway_client import call_llm_service_direct
from systems.atune.memory.schemas import Schema
from systems.atune.memory.store import MemoryStore


def _try_load_json(obj) -> dict | None:
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        return obj[0]
    return None


def extract_json_flex(text: str) -> dict | None:
    """
    Best-effort JSON extraction used across the stack:
      1) direct parse
      2) ```json ...``` fenced block
      3) first balanced {...} or [...]
      4) first '{' .. last '}' (or '[' .. ']')
    Returns dict or first dict element from a list.
    """
    if not text:
        return None

    t = text.strip()

    # 1) direct
    try:
        j = json.loads(t)
        j = _try_load_json(j)
        if j is not None:
            return j
    except Exception:
        pass

    # 2) fenced
    import re

    fence = re.compile(r"```(?:\s*json\s*)?\n(?P<payload>(?:\{.*?\}|\[.*?\]))\n```", re.I | re.S)
    m = fence.search(t)
    if m:
        try:
            j = json.loads(m.group("payload"))
            j = _try_load_json(j)
            if j is not None:
                return j
        except Exception:
            pass

    # helpers for 3/4
    def _find_balanced(s, open_ch, close_ch):
        depth = 0
        in_str = False
        esc = False
        start = s.find(open_ch)
        if start < 0:
            return None
        for i in range(start, len(s)):
            c = s[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == open_ch:
                depth += 1
            elif c == close_ch:
                depth -= 1
                if depth == 0:
                    return s[start : i + 1]
        return None

    # 3) balanced
    for o, c in (("{", "}"), ("[", "]")):
        bal = _find_balanced(t, o, c)
        if bal:
            try:
                j = json.loads(bal)
                j = _try_load_json(j)
                if j is not None:
                    return j
            except Exception:
                pass

    # 4) coarse slice
    try:
        i, j2 = t.find("{"), t.rfind("}")
        if 0 <= i < j2:
            j = json.loads(t[i : j2 + 1])
            j = _try_load_json(j)
            if j is not None:
                return j
    except Exception:
        pass
    try:
        i, j2 = t.find("["), t.rfind("]")
        if 0 <= i < j2:
            j = json.loads(t[i : j2 + 1])
            j = _try_load_json(j)
            if j is not None:
                return j
    except Exception:
        pass

    return None


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
        # 1) Render messages with the new orchestrator API
        prompt = await build_prompt(
            scope="atune.schema.naming",
            context={"vars": {"summaries": node_summaries[:10]}},
            summary=f"Name a cluster of {min(len(node_summaries), 10)} related events",
        )

        # 2) Call the LLM via the centralized client (policy-bypass utility)
        resp = await call_llm_service_direct(
            prompt_response=prompt,
            agent_name="Atune.SchemaNamer",
            scope="atune.schema.naming",
        )

        # 3) Parse JSON robustly
        payload = None
        try:
            # Prefer structured field if your gateway returns it
            payload = getattr(resp, "json", None)
            if callable(payload):
                # Some gateways expose .json() method instead of attr
                try:
                    maybe = resp.json()
                    if isinstance(maybe, dict):
                        payload = maybe
                except Exception:
                    payload = None
        except Exception:
            payload = None

        if not isinstance(payload, dict):
            text = getattr(resp, "text", "") or getattr(resp, "content", "")
            payload = extract_json_flex(text) or {}

        if isinstance(payload, dict):
            name = payload.get("schema_name")
            if isinstance(name, str) and name.strip():
                return name.strip()

        # Fallback
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
