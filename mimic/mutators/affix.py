"""Prefix and suffix mutations with numbers and separators."""

from __future__ import annotations

from collections.abc import Iterator

from mimic.core.candidate import Candidate, Transformation, as_candidate
from mimic.mutators.base import StructuredMutator


class AffixMutator(StructuredMutator):
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
        numbers: list[str | Candidate] | None = None,
        separators: str = "@!#_.",
    ) -> None:
        self.numbers = numbers or []
        self.separators = list(separators)

    def mutate_candidate(self, candidate: Candidate) -> Iterator[Candidate]:
        word = candidate.value
        # Always yield the bare word so it survives even with no numbers.
        yield candidate

        for item in self.numbers:
            token = as_candidate(item, "numbers")
            number = token.value
            yield self._affix(candidate, token, word + number, "suffix", "", "none")
            yield self._affix(candidate, token, number + word, "prefix", "", "none")

            for sep in self.separators:
                yield self._affix(candidate, token, word + sep + number, "suffix", sep, "between")
                yield self._affix(candidate, token, word + number + sep, "suffix", sep, "after")
                yield self._affix(candidate, token, sep + word + number, "suffix", sep, "before")

    @staticmethod
    def _affix(
        candidate: Candidate, token: Candidate, value: str,
        placement: str, separator: str, separator_position: str,
    ) -> Candidate:
        return candidate.join(token, value, Transformation("affix", (
            ("input", candidate.value), ("token", token.value),
            ("placement", placement), ("separator", separator),
            ("separator_position", separator_position),
            ("input_steps", str(len(candidate.transformations))),
            ("token_steps", str(len(token.transformations))),
        )))
