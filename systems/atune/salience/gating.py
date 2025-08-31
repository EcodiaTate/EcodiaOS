# systems/atune/salience/gating.py


import numpy as np


class MetaAttentionGater:
    """
    A hypernetwork that generates contextual weights for the salience heads.
    """

    def __init__(self, context_dim: int, num_heads: int):
        self.layer1_weights = np.random.randn(context_dim, 32).astype(np.float32)
        self.layer1_bias = np.random.randn(32).astype(np.float32)
        self.layer2_weights = np.random.randn(32, num_heads).astype(np.float32)
        self.layer2_bias = np.random.randn(num_heads).astype(np.float32)

    def _relu(self, x: np.ndarray) -> np.ndarray:
        return np.maximum(0, x)

    def _softmax(self, x: np.ndarray, temperature: float) -> np.ndarray:
        """Softmax activation now modulated by temperature."""
        x = x / temperature
        exps = np.exp(x - np.max(x))
        return exps / np.sum(exps)

    def get_gates(self, context_vector: np.ndarray, temperature: float = 1.0) -> np.ndarray:
        """
        Performs a forward pass, now with temperature modulation to control
        the sharpness of the attention distribution.
        """
        x = np.dot(context_vector, self.layer1_weights) + self.layer1_bias
        x = self._relu(x)
        x = np.dot(x, self.layer2_weights) + self.layer2_bias
        gates = self._softmax(x, temperature=temperature)
        return gates
