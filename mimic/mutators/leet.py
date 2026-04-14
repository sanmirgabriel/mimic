"""Leet-speak mutations with partial and full substitution modes."""

from __future__ import annotations

from collections.abc import Iterator
from itertools import combinations

from mimic.mutators.base import Mutator

LEET_MAP: dict[str, str] = {
    "a": "@",
    "e": "3",
    "i": "1",
    "o": "0",
    "s": "$",
    "t": "7",
}


class LeetMutator(Mutator):
    """Applies leet-speak substitutions to a word.

    Args:
        mode: ``"none"`` (no-op), ``"partial"`` (up to *max_subs*
            simultaneous replacements), or ``"full"`` (replace every
            eligible character at once).
        max_subs: Maximum number of simultaneous substitutions in
            partial mode.  Ignored when *mode* is ``"full"`` or
            ``"none"``.
    """

    def __init__(self, mode: str = "partial", max_subs: int = 2) -> None:
        self.mode = mode
        self.max_subs = max_subs

    def mutate(self, word: str) -> Iterator[str]:
        if self.mode == "none":
            yield word
            return

        lower = word.lower()
        # Find indices where a leet substitution is possible.
        positions: list[int] = [
            i for i, ch in enumerate(lower) if ch in LEET_MAP
        ]

        if not positions:
            yield word
            return

        if self.mode == "full":
            chars = list(lower)
            for idx in positions:
                chars[idx] = LEET_MAP[chars[idx]]
            yield "".join(chars)
            return

        # Partial: generate all combinations of 1..max_subs replacements.
        seen: set[str] = set()
        for count in range(1, min(self.max_subs, len(positions)) + 1):
            for combo in combinations(positions, count):
                chars = list(lower)
                for idx in combo:
                    chars[idx] = LEET_MAP[chars[idx]]
                result = "".join(chars)
                if result not in seen:
                    seen.add(result)
                    yield result
