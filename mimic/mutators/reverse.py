"""Reversal mutation."""

from __future__ import annotations

from collections.abc import Iterator

from mimic.core.candidate import Candidate, Transformation
from mimic.mutators.base import StructuredMutator


class ReverseMutator(StructuredMutator):
    """Yields the reversed form of a word.

    Skips yielding if the reversal is identical to the original
    (palindromes).
    """

    def mutate_candidate(self, candidate: Candidate) -> Iterator[Candidate]:
        word = candidate.value
        reversed_word = word[::-1]
        if reversed_word != word:
            yield candidate.derive(reversed_word, Transformation("reverse"))
