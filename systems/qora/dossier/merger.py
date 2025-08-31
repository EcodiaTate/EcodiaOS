# systems/qora/dossier/merger.py
from __future__ import annotations


def merge(
    graph_slice: dict[str, object] | None,
    vector_snippets: list[dict[str, object]] | None,
) -> dict[str, object]:
    """
    Simple de-dup/merge for WM dossier parts.
    """
    return {
        "graph": graph_slice or {},
        "snippets": vector_snippets or [],
        "size": len(vector_snippets or []),
    }
