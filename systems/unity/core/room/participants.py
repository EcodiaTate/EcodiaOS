# systems/unity/core/room/participants.py

from typing import Any


class ParticipantRegistry:
    """
    A simple, in-memory registry for available participant roles and their
    base configurations or prompting instructions.
    """

    _instance = None
    _roles: dict[str, dict[str, Any]] = {
        "Proposer": {
            "description": "Generates the initial proposal or solution.",
            "base_prompt": "Your role is to propose a clear, actionable solution to the topic.",
        },
        "SafetyCritic": {
            "description": "Evaluates proposals for safety, ethical, and security risks.",
            "base_prompt": "Your role is to critically assess the proposal for any potential safety vulnerabilities, ethical issues, or security flaws. Cite constitutional rules where applicable.",
        },
        "FactualityCritic": {
            "description": "Checks claims and evidence for factual accuracy.",
            "base_prompt": "Your role is to verify all factual claims made in the proposal. Challenge any unsupported statements and demand evidence.",
        },
        "CostCritic": {
            "description": "Analyzes the proposal for resource costs, complexity, and efficiency.",
            "base_prompt": "Your role is to evaluate the proposal's cost-effectiveness. Consider implementation complexity, computational resources, and long-term maintenance.",
        },
        "Adjudicator": {
            "description": "The final judge who weighs all arguments and makes a decision.",
            "base_prompt": "Your role is to synthesize all arguments, weigh the evidence, check for constitutional alignment, and render a final, reasoned verdict.",
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


# Singleton export
participant_registry = ParticipantRegistry()
