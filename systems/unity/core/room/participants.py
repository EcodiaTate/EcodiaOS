from typing import Any


class ParticipantRegistry:
    """
    A simple, in-memory registry for available participant roles and their
    base configurations, including metadata for dynamic selection.
    """

    _instance = None
    _roles: dict[str, dict[str, Any]] = {
        "Proposer": {
            "description": "Generates the initial proposal or solution.",
            "base_prompt": "Your role is to propose a clear, actionable solution to the topic.",
            "type": "proposer",
        },
        "SafetyCritic": {
            "description": "Evaluates proposals for safety, ethical, and security risks.",
            "base_prompt": "Your role is to critically assess the proposal for any potential safety vulnerabilities, ethical issues, or security flaws.",
            "type": "critic",
            # --- ADDITION: Metadata for intelligent selection ---
            "specialties": ["risk_review", "policy_review", "high_urgency"],
        },
        "FactualityCritic": {
            "description": "Checks claims and evidence for factual accuracy.",
            "base_prompt": "Your role is to verify all factual claims made in the proposal. Challenge any unsupported statements and demand evidence.",
            "type": "critic",
            "specialties": ["policy_review", "design_review", "data_analysis"],
        },
        "CostCritic": {
            "description": "Analyzes the proposal for resource costs, complexity, and efficiency.",
            "base_prompt": "Your role is to evaluate the proposal's cost-effectiveness. Consider implementation complexity, computational resources, and long-term maintenance.",
            "type": "critic",
            "specialties": ["design_review", "high_dissonance", "efficiency_optimization"],
        },
        # --- ADDITION: New, specialized agent ---
        "EthicalCritic": {
            "description": "Evaluates proposals for ethical alignment, fairness, and potential for unintended harm.",
            "base_prompt": "Your role is to analyze the proposal from an ethical standpoint, considering fairness, accountability, transparency, and potential societal impact.",
            "type": "critic",
            "specialties": ["risk_review", "policy_review", "user_impact"],
        },
        "Adjudicator": {
            "description": "The final judge who weighs all arguments and makes a decision.",
            "base_prompt": "Your role is to synthesize all arguments, weigh the evidence, and render a final, reasoned verdict.",
            "type": "synthesizer",
        },
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_role_info(self, role_name: str) -> dict[str, Any]:
        """Returns the configuration for a given role."""
        return self._roles.get(role_name, {"description": "Unknown role.", "base_prompt": ""})

    def list_roles(self) -> list[str]:
        """Returns a list of all available role names."""
        return list(self._roles.keys())

    # --- ADDITION: New helper method for the "casting director" ---
    def get_critics_with_metadata(self) -> list[dict[str, Any]]:
        """Returns a list of all available critics with their selection metadata."""
        critics = []
        for name, data in self._roles.items():
            if data.get("type") == "critic":
                critics.append(
                    {
                        "name": name,
                        "description": data.get("description"),
                        "specialties": data.get("specialties", []),
                    }
                )
        return critics


# Singleton export
participant_registry = ParticipantRegistry()
