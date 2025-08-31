from __future__ import annotations

import random

import networkx as nx

from systems.qora.manifest.models import SystemManifest


def select_pairs(manifest: SystemManifest, max_pairs: int = 200) -> list[dict]:
    """
    Prioritize comparisons that are likely to surface contradictions:
      - import-bound pairs
      - central files by PageRank
      - random long tail
    """
    g = nx.DiGraph()
    for a, b in manifest.imports:
        g.add_edge(a, b)

    pairs: list[dict] = []
    if g.number_of_nodes():
        pr = nx.pagerank(g)
        ranked = sorted(pr.items(), key=lambda x: x[1], reverse=True)
        for a, _ in ranked[: max_pairs // 2]:
            succ = list(g.successors(a))
            if succ:
                pairs.append({"left": a, "right": succ[0], "reason": "import-bound"})

    files = manifest.files[:]
    random.shuffle(files)
    for i in range(min(len(files) // 2, max_pairs - len(pairs))):
        pairs.append({"left": files[i], "right": files[-i - 1], "reason": "random"})

    return pairs
