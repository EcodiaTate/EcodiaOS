# file: systems/nova/playbooks/registry.py
from __future__ import annotations

from abc import ABC, abstractmethod

from systems.nova.schemas import InnovationBrief, InventionCandidate


class BasePlaybook(ABC):
    """Abstract base class for all Nova invention playbooks."""

    name: str = "base.abstract"

    @abstractmethod
    async def run(self, brief: InnovationBrief, budget_ms: int) -> list[InventionCandidate]:
        """
        Executes the playbook's invention strategy.

        Args:
            brief: The InnovationBrief detailing the problem.
            budget_ms: The compute budget allocated for this run.

        Returns:
            A list of generated InventionCandidates.
        """
        raise NotImplementedError


# Import concrete playbook implementations here
from .dreamcoder_lib import DreamCoderLibraryPlaybook
from .qdelites import QDElitesPlaybook
from .tot_mcts import ToTMCTSPlaybook

# The central, discoverable registry of all available playbooks.
# The PlaybookRunner will use this registry to find and instantiate strategies.
PLAYBOOK_REGISTRY: list[type[BasePlaybook]] = [
    QDElitesPlaybook,
    ToTMCTSPlaybook,
    DreamCoderLibraryPlaybook,
    # As new playbooks like AlphaDev or EUREKA are implemented,
    # they are simply added to this list to become available to the system.
]
