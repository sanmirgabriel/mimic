"""Leet-speak mutations with partial and full substitution modes."""

from __future__ import annotations

from collections.abc import Iterator
from itertools import combinations

from mimic.core.candidate import Candidate, Transformation
from mimic.mutators.base import StructuredMutator

LEET_MAP: dict[str, str] = {
    "a": "@",
    "e": "3",
    "i": "1",
    "o": "0",
    "s": "$",
    "t": "7",
}


class LeetMutator(StructuredMutator):
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

    def mutate_candidate(self, candidate: Candidate) -> Iterator[Candidate]:
        word = candidate.value
        if self.mode == "none":
            yield candidate
            return

        lower = word.lower()
        # Find indices where a leet substitution is possible.
        positions: list[int] = [
            i for i, ch in enumerate(lower) if ch in LEET_MAP
        ]

        if not positions:
            yield candidate
            return

        if self.mode == "full":
            # Preserve original casing of untouched letters; substitution
            # chars themselves carry no case (e.g. '@', '3').
            yield self._substitute(candidate, lower, positions)
            return

        # Partial: generate all combinations of 1..max_subs replacements.
        seen: set[str] = set()
        for count in range(1, min(self.max_subs, len(positions)) + 1):
            for combo in combinations(positions, count):
                result = self._substitute(candidate, lower, combo)
                if result.value not in seen:
                    seen.add(result.value)
                    yield result

    def _substitute(
        self, candidate: Candidate, lower: str, positions: list[int] | tuple[int, ...]
    ) -> Candidate:
        chars = list(candidate.value)
        transformations = []
        for idx in positions:
            replacement = LEET_MAP[lower[idx]]
            transformations.append(Transformation("leet", (
                ("mode", self.mode), ("from", chars[idx]),
                ("to", replacement), ("position", str(idx)),
            )))
            chars[idx] = replacement
        return Candidate(
            "".join(chars), candidate.origins,
            candidate.transformations + tuple(transformations),
        )
