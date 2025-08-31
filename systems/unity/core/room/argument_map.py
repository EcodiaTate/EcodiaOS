# systems/unity/core/room/argument_map.py
from __future__ import annotations

from collections import defaultdict
from typing import Any


class ArgumentMiner:
    """
    Construct an argument graph (DAG-like for SUPPORTS) from deliberation transcripts
    and compute a defended minimal set of base assumptions needed to support a conclusion.

    Graph model:
      - Nodes: claims (string IDs) with metadata.
      - Edges:
          SUPPORTS: directed support relation (u -> v means u supports v)
          ATTACKS : directed attack relation  (u -> v means u undermines v)

    Minimal assumption set:
      - Start from the conclusion, traverse *backwards along SUPPORTS*.
      - Collect leaves with no incoming SUPPORTS (base assumptions).
      - Exclude leaves that are *attacked* by any node that is not counter-attacked
        by at least one node in the SUPPORTS ancestry (simple defense criterion).
      - If traversal encounters cycles in SUPPORTS, cycles are ignored during backtracking.
    """

    def __init__(self):
        # Node store
        self.claims: dict[str, dict[str, Any]] = {}  # claim_id -> {text, is_assumption}
        # Back-compat containers (kept updated)
        self.edges: dict[str, list[str]] = defaultdict(list)  # from_claim_id -> [to_claim_id]
        self.edge_types: dict[tuple[str, str], str] = {}  # (from, to) -> "SUPPORTS" | "ATTACKS"

        # Structured adjacency
        self._sup_out: dict[str, set[str]] = defaultdict(set)
        self._sup_in: dict[str, set[str]] = defaultdict(set)
        self._atk_out: dict[str, set[str]] = defaultdict(set)
        self._atk_in: dict[str, set[str]] = defaultdict(set)

    # -----------------------
    # Graph construction
    # -----------------------
    def add_claim(self, claim_id: str, text: str):
        """Add a claim (node). Idempotent."""
        if claim_id not in self.claims:
            self.claims[claim_id] = {"text": text, "is_assumption": True}
        else:
            # Update text if newly provided and previous text was empty
            if text and not self.claims[claim_id].get("text"):
                self.claims[claim_id]["text"] = text

    def _ensure_node(self, claim_id: str):
        if claim_id not in self.claims:
            self.claims[claim_id] = {"text": "", "is_assumption": True}

    def add_inference(self, from_claim_id: str, to_claim_id: str, rel_type: str):
        """
        Add a directed inference edge. rel_type is case-insensitive: 'SUPPORTS' or 'ATTACKS'.
        Back-compat attributes (edges, edge_types) remain populated.
        """
        r = str(rel_type).upper().strip()
        if r not in ("SUPPORTS", "ATTACKS"):
            raise ValueError(f"Unsupported relation type: {rel_type}")

        self._ensure_node(from_claim_id)
        self._ensure_node(to_claim_id)

        # Back-compat mirrors
        self.edges[from_claim_id].append(to_claim_id)
        self.edge_types[(from_claim_id, to_claim_id)] = r

        if r == "SUPPORTS":
            self._sup_out[from_claim_id].add(to_claim_id)
            self._sup_in[to_claim_id].add(from_claim_id)
            # A supported node is not a base assumption anymore
            self.claims[to_claim_id]["is_assumption"] = False
        else:  # ATTACKS
            self._atk_out[from_claim_id].add(to_claim_id)
            self._atk_in[to_claim_id].add(from_claim_id)

    # -----------------------
    # Analysis
    # -----------------------
    def _support_ancestry(self, conclusion_id: str) -> set[str]:
        """
        Collect all nodes that lie on some SUPPORTS-ancestry path to the conclusion.
        Skips SUPPORTS back-edges that would introduce a cycle in the current DFS path.
        """
        if conclusion_id not in self.claims:
            return set()

        ancestry: set[str] = set()
        stack: list[str] = [conclusion_id]
        visiting: set[str] = set()

        while stack:
            node = stack.pop()
            if node in ancestry:
                continue
            ancestry.add(node)
            visiting.add(node)
            for parent in self._sup_in.get(node, ()):
                if parent in visiting:
                    # Cycle detected along SUPPORTS; ignore this back-edge
                    continue
                stack.append(parent)
            visiting.discard(node)
        return ancestry

    def _collect_base_leaves(self, ancestry: set[str]) -> set[str]:
        """
        Base assumptions are nodes in ancestry with zero incoming SUPPORTS.
        """
        leaves: set[str] = set()
        for node in ancestry:
            if len(self._sup_in.get(node, set())) == 0:
                leaves.add(node)
        return leaves

    def _defended_filter(self, leaves: set[str], ancestry: set[str]) -> set[str]:
        """
        Keep only leaves that are not attacked, or whose attackers are counter-attacked
        by any node in the SUPPORTS ancestry (simple grounded defense).
        """
        if not leaves:
            return leaves

        defenders = ancestry  # any ancestor may serve as a defender via ATTACKS
        kept: set[str] = set()

        for leaf in leaves:
            attackers = self._atk_in.get(leaf, set())
            if not attackers:
                kept.add(leaf)
                continue

            # A leaf is defended if *at least one* defender attacks *each* attacker (collective defense)
            defended = True
            for att in attackers:
                # any defender d in ancestry with edge d -> att as ATTACKS?
                defended_by_any = any(att in self._atk_out.get(d, set()) for d in defenders)
                if not defended_by_any:
                    defended = False
                    break
            if defended:
                kept.add(leaf)

        # Fallback: if everything was pruned, return original leaves to avoid empty basis.
        return kept if kept else leaves

    def get_minimal_assumption_set(self, conclusion_id: str) -> set[str]:
        """
        Compute a defended minimal set of assumptions sufficient to support `conclusion_id`.
        - Traverses SUPPORTS ancestors to find base leaves.
        - Applies a defense filter against ATTACKS from outside the support ancestry.
        - Ignores SUPPORTS cycles during traversal to guarantee termination.
        """
        if conclusion_id not in self.claims:
            return set()

        ancestry = self._support_ancestry(conclusion_id)
        if not ancestry:
            # No ancestry means the conclusion itself is a standalone assumption.
            return {conclusion_id}

        leaves = self._collect_base_leaves(ancestry)
        if not leaves:
            # If no leaves found (e.g., pure cycle), treat conclusion as assumption of last resort.
            return {conclusion_id}

        defended = self._defended_filter(leaves, ancestry)
        return defended
