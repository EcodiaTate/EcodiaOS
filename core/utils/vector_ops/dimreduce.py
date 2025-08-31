# core/utils/vector_ops/dimreduce.py

import numpy as np
import umap


def reduce_vectors(vectors: list[list[float]], n_components: int = 2) -> list[list[float]]:
    reducer = umap.UMAP(n_components=n_components, random_state=42)
    embedding = reducer.fit_transform(np.array(vectors))
    return embedding.tolist()
