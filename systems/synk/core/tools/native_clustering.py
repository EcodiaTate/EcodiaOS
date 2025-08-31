"""
🧠 EcodiaOS Native Clustering Engine
- Fetches text content from :Event nodes
- Batches Gemini embeddings with bounded concurrency
- Clusters with K-Means (NumPy impl; sklearn optional)
- Writes cluster_id back to Events
"""

from __future__ import annotations

import asyncio

import numpy as np

from core.llm.embeddings_gemini import get_embedding
from core.utils.neo.cypher_query import cypher_query

# -----------------------
# Fetch
# -----------------------


async def fetch_event_vectors(prop: str = "vector_gemini") -> tuple[list[str], np.ndarray]:
    q = f"""
    MATCH (e:Event)
    WHERE e.`{prop}` IS NOT NULL
    RETURN e.event_id AS event_id, e.`{prop}` AS vec
    """
    rows = await cypher_query(q)
    ids = [r["event_id"] for r in rows]
    vecs = [np.asarray(r["vec"], dtype=np.float32) for r in rows]
    if not vecs:
        return [], np.zeros((0,), dtype=np.float32)
    return ids, np.vstack(vecs)


async def fetch_all_event_content() -> list[dict[str, str]]:
    """
    Returns [{event_id, text}] using a broad set of text candidates.
    """
    q = """
    MATCH (n:Event)
    WITH n, coalesce(n.content, n.summary, n.text, n.body, n.description, "") AS txt
    WHERE txt <> ""
    RETURN n.event_id AS event_id, txt AS text
    """
    rows = await cypher_query(q)
    out: list[dict[str, str]] = []
    for r in rows:
        t = (r.get("text") or "").strip()
        if t:
            out.append({"event_id": r["event_id"], "text": t})
    return out


# -----------------------
# Orchestrator
# -----------------------


async def run_native_clustering_pipeline(
    *,
    k: int | None = None,
    normalize: bool = True,
    max_concurrency: int = 8,
    update_batch_size: int = 1000,
) -> dict:
    # 1) Try existing vectors
    ids, mat = await fetch_event_vectors(prop="vector_gemini")
    source = "vectors"

    # 2) Fall back to text → embeddings
    if mat.size == 0:
        events = await fetch_all_event_content()
        if not events:
            return {"status": "no_data", "clusters": 0, "items": 0, "source": "none"}
        ids = [e["event_id"] for e in events]
        mat = await embed_batch(events, max_concurrency=max_concurrency)
        source = "text"

    if mat.size == 0:
        return {"status": "no_vectors", "clusters": 0, "items": 0, "source": source}

    # L2 normalize for cosine-ish behavior
    if normalize:
        norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-12
        mat = (mat / norms).astype(np.float32, copy=False)

    k_final = choose_k(mat.shape[0], k=k)
    labels = try_sklearn_kmeans(mat, k_final)
    if labels is None:
        labels, _ = kmeans_numpy(mat, k_final)

    await update_nodes_with_clusters(ids, labels, batch_size=update_batch_size)

    uniques, counts = np.unique(labels, return_counts=True)
    return {
        "status": "ok",
        "items": len(ids),
        "clusters": int(len(uniques)),
        "k": int(k_final),
        "cluster_sizes": {int(u): int(c) for u, c in zip(uniques, counts)},
        "source": source,
    }


# -----------------------
# Embedding
# -----------------------


async def _embed_one(text: str) -> list[float]:
    return await get_embedding(text)


async def embed_batch(items: list[dict], max_concurrency: int = 8) -> np.ndarray:
    """
    Returns an NxD float32 matrix. Preserves order of `items`.
    Uses simple chunked gather to avoid creating tens of thousands of tasks.
    """
    vecs: list[np.ndarray] = []
    for i in range(0, len(items), max_concurrency):
        batch = items[i : i + max_concurrency]
        res = await asyncio.gather(*(_embed_one(it["text"]) for it in batch))
        vecs.extend(np.asarray(v, dtype=np.float32) for v in res)
    return np.asarray(vecs, dtype=np.float32)


# -----------------------
# K selection heuristic
# -----------------------


def choose_k(n: int, k: int | None = None) -> int:
    """
    If k not provided, pick ~sqrt(n/2), clipped to [2, 20] and <= n.
    """
    if k is not None:
        return max(1, min(k, n))  # allow k=1 if caller insists
    if n < 2:
        return 1
    est = int(max(2, min(20, np.floor(np.sqrt(n / 2)))))
    return int(min(est, n))


# -----------------------
# K-Means (NumPy first, sklearn optional)
# -----------------------


def kmeans_numpy(
    x: np.ndarray,
    k: int,
    iters: int = 50,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Simple NumPy K-Means. Returns (labels, centroids).
    Assumes x is L2-normalized for cosine-ish behavior.
    """
    rng = np.random.default_rng(seed)
    n = x.shape[0]
    k = min(k, n)
    if k <= 0:
        return np.zeros((n,), dtype=int), x[:1] if n else np.zeros(
            (0, x.shape[1] if x.ndim == 2 else 0),
        )

    # init centroids by sampling without replacement
    idx = rng.choice(n, size=k, replace=False)
    c = x[idx].copy()

    for _ in range(iters):
        # squared euclidean distances (n,k,d) -> (n,k)
        d = ((x[:, None, :] - c[None, :, :]) ** 2).sum(-1)
        y = d.argmin(axis=1)

        newc = np.empty_like(c)
        changed = False
        for i in range(k):
            sel = y == i
            if np.any(sel):
                newc[i] = x[sel].mean(axis=0)
            else:
                # empty cluster: re-seed to a random point
                ridx = rng.integers(0, n)
                newc[i] = x[ridx]
            if not np.allclose(newc[i], c[i]):
                changed = True
        c = newc
        if not changed:
            break
    return y.astype(int, copy=False), c


def try_sklearn_kmeans(x: np.ndarray, k: int) -> np.ndarray | None:
    try:
        from sklearn.cluster import KMeans  # type: ignore

        n_clusters = min(k, x.shape[0])
        try:
            km = KMeans(n_clusters=n_clusters, random_state=42, n_init="auto")
        except TypeError:
            # Older sklearn: 'auto' not supported
            km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        return km.fit_predict(x).astype(int, copy=False)
    except Exception:
        return None


# -----------------------
# Update back to Neo4j
# -----------------------


async def update_nodes_with_clusters(
    event_ids: list[str],
    labels: np.ndarray,
    *,
    batch_size: int = 1000,
) -> None:
    """
    Chunk writes to avoid gigantic UNWIND payloads.
    """
    rows = [{"event_id": e, "cluster_id": int(c)} for e, c in zip(event_ids, labels.tolist())]
    q = """
    UNWIND $rows AS row
    MATCH (n:Event {event_id: row.event_id})
    SET n.cluster_id = row.cluster_id
    """
    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        await cypher_query(q, {"rows": chunk})
