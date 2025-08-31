# core/utils/vector_ops/cluster.py

import hdbscan
import numpy as np


def cluster_vectors(vectors: list[list[float]], min_cluster_size: int = 2) -> list[int]:
    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size)
    labels = clusterer.fit_predict(np.array(vectors))
    return labels.tolist()
