# systems/simula/agent/context_formatters.py

from __future__ import annotations

from typing import Any, Dict, List


def format_dossier_for_llm(dossier: dict[str, Any]) -> str:
    """
    Transforms the rich JSON output from the Qora dossier service into a clean,
    hierarchical, and LLM-friendly markdown format. This provides deep,
    synthesized context for the Deliberative Core.
    """
    if not dossier:
        return "No dossier available for the target."

    chunks = []

    # --- Target ---
    target = dossier.get("target", {})
    if target.get("fqn"):
        chunks.append(f"# Dossier for `{target['fqn']}`")
        if target.get("path"):
            chunks.append(f"**Location:** `{target['path']}`")

        if docstring := target.get("docstring"):
            chunks.append(f"## Docstring\n```\n{docstring}\n```")

        if source := target.get("source_code"):
            chunks.append(f"## Source Code\n```python\n{source}\n```")

    analysis = dossier.get("analysis", {})

    # --- Structural Neighbors ---
    struct = analysis.get("structural_neighbors", {})
    if struct:
        chunks.append("## Structural Analysis")

        def format_neighbor_list(title: str, neighbors: list[dict]) -> str:
            if not neighbors:
                return ""
            md = f"### {title}\n"
            for n in neighbors[:5]:  # Limit for brevity
                md += f"- `{n.get('fqn', n.get('name', 'N/A'))}`\n"
            if len(neighbors) > 5:
                md += f"- ...and {len(neighbors) - 5} more.\n"
            return md

        chunks.append(
            format_neighbor_list("Callers (Code that calls this)", struct.get("callers", []))
        )
        chunks.append(
            format_neighbor_list("Callees (Code that this calls)", struct.get("callees", []))
        )
        chunks.append(
            format_neighbor_list("Siblings (Defined in the same file)", struct.get("siblings", []))
        )

    # --- Semantic Neighbors ---
    semantic = analysis.get("semantic_neighbors", [])
    if semantic:
        chunks.append("## Semantically Similar Code")
        chunks.append(
            "The following code snippets from the repository have a similar purpose or meaning:"
        )
        for n in semantic[:3]:  # Limit for brevity
            chunks.append(
                f"- **`{n.get('fqn', n.get('name', 'N/A'))}`** (Similarity: {n.get('score', 0.0):.2f})\n  - {n.get('docstring', 'No docstring.')}"
            )

    # --- Test Coverage ---
    tests = analysis.get("related_tests", [])
    if tests:
        chunks.append("## Test Coverage")
        chunks.append("This code appears to be tested by the following files:")
        for t in tests:
            chunks.append(f"- `{t.get('test_path')}`")

    # --- Historical Context ---
    history = analysis.get("historical_context", {})
    conflicts = history.get("conflicts_and_solutions", [])
    if conflicts:
        chunks.append("## Historical Conflicts")
        chunks.append("This code has been associated with the following past problems:")
        for c in conflicts[:2]:  # Limit for brevity
            chunks.append(f"- **Conflict:** {c.get('description')}")

    return "\n\n".join(filter(None, chunks))
