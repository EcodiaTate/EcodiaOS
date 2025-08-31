from __future__ import annotations

from collections.abc import Iterable
from hashlib import blake2s
from typing import Any


def _barcode(d: dict[str, Any]) -> str:
    return blake2s(repr(sorted(d.items())).encode("utf-8")).hexdigest()


class NoveltyReservoir:
    """
    Reject near-duplicate mechanism/capability specs to force exploration
    *within a single propose run only* (no persistence → SoC-safe).
    """

    def __init__(self) -> None:
        self._seen_mech: set[str] = set()
        self._seen_caps: set[str] = set()

    def key(self, cand: dict[str, Any]) -> tuple[str, str]:
        mech = cand.get("spec", {}).get("mechanism_graph", {})
        caps = cand.get("spec", {}).get("capability_spec", {})
        return _barcode(mech), _barcode(caps)

    def accept(self, candidate: dict[str, Any]) -> bool:
        km, kc = self.key(candidate)
        if km in self._seen_mech and kc in self._seen_caps:
            return False
        self._seen_mech.add(km)
        self._seen_caps.add(kc)
        return True

    def filter_portfolio(
        self,
        candidates: Iterable[dict[str, Any]],
        k: int = 8,
    ) -> list[dict[str, Any]]:
        bag: list[dict[str, Any]] = []
        for c in candidates:
            if self.accept(c):
                bag.append(c)
            if len(bag) >= k:
                break
        return bag
