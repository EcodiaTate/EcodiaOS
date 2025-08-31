from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any


class CounterexampleDistiller:
    """
    Shrinks failing inputs to their essence using greedy delta-debugging.
    Emits minimal repr + trace to strengthen specs and prevent regression amnesia.
    """

    def distill(
        self,
        failing_input: Any,
        test_fn: Callable[[Any], bool],
        splitter: Callable[[Any], Iterable[Any]],
        joiner: Callable[[Iterable[Any]], Any],
        *,
        max_rounds: int = 10,
    ) -> tuple[Any, dict]:
        """
        test_fn(x) -> True if failure persists on x.
        splitter breaks input into parts; joiner re-assembles.
        """
        parts = list(splitter(failing_input))
        meta: dict = {"rounds": 0, "attempts": 0}

        for r in range(max_rounds):
            meta["rounds"] = r + 1
            improved = False
            for i in range(len(parts)):
                meta["attempts"] += 1
                trial = joiner(parts[:i] + parts[i + 1 :])
                if test_fn(trial):
                    parts.pop(i)
                    improved = True
                    break
            if not improved:
                break

        return joiner(parts), meta
