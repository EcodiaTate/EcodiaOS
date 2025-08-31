# systems/equor/core/identity/composer.py
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Dict, List, Tuple

from core.utils.neo.cypher_query import cypher_query
from systems.equor.schemas import ComposeRequest, ComposeResponse


class CompositionError(Exception):
    """Raised when a prompt patch cannot be composed deterministically."""


@dataclass
class _ProfileData:
    agent: str
    name: str
    facet_ids: List[str]
    rule_ids: List[str]
    settings: Dict[str, Any]


async def _get_profile(agent: str, name: str) -> _ProfileData:
    """
    Fetch a profile without relying on relationship types that may not exist yet.
    We return plain properties via `properties(p)` to avoid driver-specific node wrappers.
    """
    rows = await cypher_query(
      """
      MATCH (p:Profile {agent:$agent, name:$name})
      RETURN properties(p) AS p
      LIMIT 1
      """,
      {"agent": agent, "name": name},
    )
    if not rows:
        raise CompositionError(f"No active profile named '{name}' found for agent '{agent}'.")

    p: Dict[str, Any] = rows[0].get("p") or {}
    facet_ids = p.get("facet_ids") or []
    rule_ids = p.get("rule_ids") or []

    # Parse non-primitive settings (stored as JSON string)
    settings_raw = p.get("settings_json")
    try:
        settings = json.loads(settings_raw) if settings_raw else {}
    except Exception:
        settings = {}

    return _ProfileData(agent=agent, name=name, facet_ids=list(facet_ids), rule_ids=list(rule_ids), settings=settings)


async def _load_facets(facet_ids: List[str], agent: str, name: str) -> List[Dict[str, Any]]:
    """
    Prefer IDs; fall back to graph links if none were set on the profile.
    Return each facet as a plain property map.
    """
    if facet_ids:
        rows = await cypher_query(
            """
            MATCH (f:Facet)
            WHERE f.id IN $ids
            RETURN properties(f) AS f
            """,
            {"ids": facet_ids},
        )
        return [r["f"] for r in rows or []]

    # Fallback: follow relationships if present (this won’t warn if rels are absent)
    rows = await cypher_query(
        """
        MATCH (p:Profile {agent:$agent, name:$name})-[:USES_FACET]->(f:Facet)
        RETURN properties(f) AS f
        """,
        {"agent": agent, "name": name},
    )
    return [r["f"] for r in rows or []]


async def _load_rules(rule_ids: List[str], agent: str, name: str) -> List[Dict[str, Any]]:
    if rule_ids:
        rows = await cypher_query(
            """
            MATCH (r:ConstitutionRule)
            WHERE r.id IN $ids
            RETURN properties(r) AS r
            """,
            {"ids": rule_ids},
        )
        return [r["r"] for r in rows or []]

    # Fallback: follow relationships if present
    rows = await cypher_query(
        """
        MATCH (p:Profile {agent:$agent, name:$name})-[:APPLIES_RULE]->(r:ConstitutionRule)
        RETURN properties(r) AS r
        """,
        {"agent": agent, "name": name},
    )
    return [r["r"] for r in rows or []]


def _choose_id(d: Dict[str, Any]) -> str:
    # Best-effort ID chooser across heterogeneous nodes
    return str(
        d.get("id")
        or d.get("rule_id")
        or d.get("facet_id")
        or d.get("uuid")
        or d.get("name")
        or ""
    )


def _materialize_patch_text(
    agent: str,
    profile: str,
    episode_id: str,
    facets: List[Dict[str, Any]],
    rules: List[Dict[str, Any]],
    settings: Dict[str, Any],
) -> Tuple[str, List[str], List[str]]:
    facet_lines: List[str] = []
    rule_lines: List[str] = []

    included_facets: List[str] = []
    included_rules: List[str] = []

    for f in facets:
        fid = _choose_id(f)
        included_facets.append(fid)
        title = f.get("title") or f.get("name") or fid
        body = f.get("text") or f.get("prompt") or f.get("body") or ""
        facet_lines.append(f"- {title}\n{body}".strip())

    for r in rules:
        rid = _choose_id(r)
        included_rules.append(rid)
        title = r.get("title") or r.get("name") or rid
        body = r.get("text") or r.get("content") or r.get("rule") or ""
        rule_lines.append(f"- {title}\n{body}".strip())

    settings_line = json.dumps(settings, sort_keys=True) if settings else "{}"

    parts = [
        f"# Identity Profile: {agent}/{profile}",
        f"episode: {episode_id}",
        "",
        "## Operational Settings",
        settings_line,
        "",
        "## Facets",
        *facet_lines,
        "",
        "## Constitution Rules",
        *rule_lines,
        "",
        "## Application Notes",
        "All generations must adhere to the above rules and facets. Refuse to operate outside them.",
    ]
    text = "\n".join(parts)
    return text, included_facets, included_rules


class PromptComposer:
    """
    Deterministic, rule-first composer.
    Produces a fully-formed ComposeResponse that the middleware can attest.
    """

    async def compose(self, req: ComposeRequest, *, rcu_ref: str) -> ComposeResponse:
        # Validate minimal request shape
        agent = getattr(req, "agent", None) or "system"
        profile_name = getattr(req, "profile_name", None) or "prod"
        episode_id = getattr(req, "episode_id", None)
        if not episode_id:
            raise CompositionError("Missing episode_id in ComposeRequest.")

        # 1) Load profile + selections
        prof = await _get_profile(agent, profile_name)

        # 2) Materialize artifacts
        facets = await _load_facets(prof.facet_ids, prof.agent, prof.name)
        rules = await _load_rules(prof.rule_ids, prof.agent, prof.name)

        text, included_facets, included_rules = _materialize_patch_text(
            agent=prof.agent,
            profile=prof.name,
            episode_id=episode_id,
            facets=facets,
            rules=rules,
            settings=prof.settings,
        )

        # 3) Deterministic IDs
        created_at = datetime.now(UTC).isoformat()
        checksum = hashlib.sha256((text + rcu_ref + episode_id).encode("utf-8")).hexdigest()[:16]
        prompt_patch_id = f"{agent}-{profile_name}-{checksum}"

        # 4) Response (schema-complete)
        return ComposeResponse(
            prompt_patch_id=prompt_patch_id,
            episode_id=episode_id,
            rcu_ref=rcu_ref,
            checksum=checksum,
            included_facets=included_facets,
            included_rules=included_rules,
            text=text,
            created_at=created_at,
            metadata={"settings": prof.settings},
        )
