"""Reversal mutation."""

from __future__ import annotations

from collections.abc import Iterator

from mimic.mutators.base import Mutator


class ReverseMutator(Mutator):
    """Yields the reversed form of a word.

    Skips yielding if the reversal is identical to the original
    (palindromes).
    """

    def mutate(self, word: str) -> Iterator[str]:
        reversed_word = word[::-1]
        if reversed_word != word:
            yield reversed_word
