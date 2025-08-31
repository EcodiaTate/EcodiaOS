from __future__ import annotations

from systems.evo.schemas import Proposal
from systems.evo.spec.validators import SpecValidators


class ProposalReview:
    """
    Per-episode static review. Attaches 'open questions' to proposal.
    No persistence, no policy tuning.
    """

    def __init__(self) -> None:
        self._spec = SpecValidators()

    def review(self, p: Proposal) -> Proposal:
        questions: list[str] = []
        questions += self._spec.check_obligation_presence(
            p.obligations if hasattr(p, "obligations") else {},
        )
        questions += self._spec.check_rollback_contract(p.rollback_plan)
        # Attach without mutating core structure
        p.open_questions.extend(questions)
        return p
