# systems/atune/focus/field.py


class SalienceFieldManager:
    """
    Manages a scalar salience field over the knowledge graph.
    """

    def __init__(self, diffusion_coeff: float = 0.1, default_leak_gamma: float = 0.05):
        self.D = diffusion_coeff
        self.default_gamma = default_leak_gamma
        self.field_values: dict[str, float] = {}

    def deposit(self, node_ids: list[str], mass: float):
        # ... (implementation unchanged)
        if mass <= 0:
            return
        mass_per_node = mass / len(node_ids) if node_ids else 0
        for node_id in node_ids:
            self.field_values[node_id] = self.field_values.get(node_id, 0.0) + mass_per_node

    def run_diffusion_step(
        self,
        adjacency_list: dict[str, list[str]],
        leak_gamma: float | None = None,
    ):
        """
        Executes one time-step of the diffusion-leak simulation, now using
        a dynamically provided leak coefficient.
        """
        gamma = leak_gamma if leak_gamma is not None else self.default_gamma

        # ... (rest of implementation is unchanged)
        if not self.field_values:
            return
        next_field_values = self.field_values.copy()
        for node_id, neighbors in adjacency_list.items():
            current_salience = self.field_values.get(node_id, 0.0)
            neighbor_salience_sum = sum(self.field_values.get(n, 0.0) for n in neighbors)
            laplacian_term = neighbor_salience_sum - (len(neighbors) * current_salience)
            leaked_value = (1 - gamma) * current_salience
            diffused_value = self.D * laplacian_term
            next_field_values[node_id] = leaked_value + diffused_value
        self.field_values = {k: v for k, v in next_field_values.items() if v > 1e-6}

    def detect_hotspots(self, threshold: float = 0.8) -> list[str]:
        # ... (implementation unchanged)
        if not self.field_values:
            return []
        max_salience = max(self.field_values.values())
        dynamic_threshold = max(threshold, max_salience * 0.75)
        return [
            node_id
            for node_id, salience in self.field_values.items()
            if salience > dynamic_threshold
        ]
