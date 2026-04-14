"""Prefix and suffix mutations with numbers and separators."""

from __future__ import annotations

from collections.abc import Iterator

from mimic.mutators.base import Mutator


class AffixMutator(Mutator):
    """Appends/prepends numbers and separators to a word.

    Given a word, numbers, and separators it yields combinations like::

        word + number
        number + word
        word + sep + number
        word + number + sep

    Args:
        numbers: List of numeric strings (years, pins, etc.).
        separators: Characters used between word and number.
    """

    def __init__(
        self,
        numbers: list[str] | None = None,
        separators: str = "@!#_.",
    ) -> None:
        self.numbers = numbers or []
        self.separators = list(separators)

    def mutate(self, word: str) -> Iterator[str]:
        # Always yield the bare word so it survives even with no numbers.
        yield word

        for number in self.numbers:
            yield word + number
            yield number + word

            for sep in self.separators:
                yield word + sep + number
                yield word + number + sep
                yield sep + word + number
