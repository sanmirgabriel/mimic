"""Case-based mutations: lower, upper, title, camelCase."""

from __future__ import annotations

from collections.abc import Iterator

from mimic.mutators.base import Mutator


class CaseMutator(Mutator):
    """Yields case variations of a word.

    Produces: original, lowercase, UPPERCASE, and Titlecase forms.
    Duplicates are naturally removed downstream by the dedup layer.
    """

    def mutate(self, word: str) -> Iterator[str]:
        yield word
        yield word.lower()
        yield word.upper()
        yield word.title()
