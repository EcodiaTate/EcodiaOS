# systems/equor/core/identity/registry.py
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from systems.equor.core.neo import graph_writes

logger = logging.getLogger(__name__)


class RegistryError(Exception):
    """Custom exception for errors during registry lookups."""

    pass


def _ensure_list(x: Any) -> list[Any]:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    if isinstance(x, tuple):
        return list(x)
    return [x]


def _dedupe_preserve_order(seq: Iterable[Any]) -> list[Any]:
    seen = set()
    out: list[Any] = []
    for s in seq:
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _node_id(n: dict[str, Any]) -> str | None:
    """
    Try multiple common shapes to recover a node id.
    """
    if not isinstance(n, dict):
        return None
    # Common keys
    for k in ("id", "node_id", "uid"):
        if k in n and isinstance(n[k], str | int):
            return str(n[k])
    # Nested properties
    props = n.get("properties") or {}
    if isinstance(props, dict):
        for k in ("id", "node_id", "uid"):
            v = props.get(k)
            if isinstance(v, str | int):
                return str(v)
    return None


def _has_label(n: dict[str, Any], label: str) -> bool:
    """
    Labels may arrive as a list (['Facet', ...]) or a string ('Facet').
    Some serializers place them under 'labels', others under 'label'.
    """
    labels = n.get("labels", n.get("label"))
    if labels is None:
        return False
    if isinstance(labels, str):
        return labels == label or labels.endswith(f":{label}") or labels.startswith(f"{label}:")
    if isinstance(labels, list):
        return label in labels
    return False


class IdentityRegistry:
    """
    Provides a high-level API to retrieve identity components (Profiles,
    Facets, Rules) from the Neo4j database.

    This service acts as a singleton to provide a consistent access layer
    to the identity graph. It uses the driverless graph_writes helpers
    for all database interactions.
    """

    _instance: IdentityRegistry | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def get_active_components_for_profile(
        self,
        agent: str,
        profile_name: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Fetch the active profile and its associated facets and rules.

        Args:
            agent: The name of the agent (e.g., "Ember").
            profile_name: The name of the profile (e.g., "prod").

        Returns:
            (profile_dict, facets[], rules[])
        """
        # 1) Active profile
        profile_dict = await graph_writes.get_active_profile(agent, profile_name)
        if not profile_dict:
            raise RegistryError(
                f"No active profile named '{profile_name}' found for agent '{agent}'.",
            )

        facet_ids = [str(i) for i in _ensure_list(profile_dict.get("facet_ids"))]
        rule_ids = [str(i) for i in _ensure_list(profile_dict.get("rule_ids"))]

        # Preserve requested order and de-duplicate
        requested_ids: list[str] = _dedupe_preserve_order(facet_ids + rule_ids)
        if not requested_ids:
            logger.info(
                "[IdentityRegistry] Profile '%s' for agent '%s' has no facets or rules.",
                profile_name,
                agent,
            )
            return profile_dict, [], []

        # 2) Batch fetch all components
        all_components = await graph_writes.get_nodes_by_ids(requested_ids) or []
        if not isinstance(all_components, list):
            logger.warning("[IdentityRegistry] get_nodes_by_ids returned non-list; coercing.")
            all_components = _ensure_list(all_components)

        # 3) Index by id for stable reconstruction in requested order
        by_id: dict[str, dict[str, Any]] = {}
        for node in all_components:
            nid = _node_id(node)
            if nid:
                by_id[nid] = node

        # 4) Rebuild lists in the same order as requested, skipping missing
        fetched_nodes: list[dict[str, Any]] = [by_id[i] for i in requested_ids if i in by_id]

        # 5) Partition into facets and rules (label-aware), preserving order
        facets: list[dict[str, Any]] = []
        rules: list[dict[str, Any]] = []
        for n in fetched_nodes:
            if _has_label(n, "Facet"):
                facets.append(n)
            elif _has_label(n, "ConstitutionRule"):
                rules.append(n)

        # 6) Diagnostics for partial fetches
        missing = [i for i in requested_ids if i not in by_id]
        if missing:
            logger.warning(
                "[IdentityRegistry] Missing %d/%d components for profile '%s' (agent='%s'). Missing IDs: %s",
                len(missing),
                len(requested_ids),
                profile_name,
                agent,
                ", ".join(missing[:10]) + ("..." if len(missing) > 10 else ""),
            )

        # Optional: validate counts roughly match expectations (len, not strict)
        if len(facets) < len(facet_ids) or len(rules) < len(rule_ids):
            logger.warning(
                "[IdentityRegistry] Label partition mismatch for profile '%s' (agent='%s'). "
                "expected facets=%d rules=%d, got facets=%d rules=%d",
                profile_name,
                agent,
                len(facet_ids),
                len(rule_ids),
                len(facets),
                len(rules),
            )

        return profile_dict, facets, rules
