"""Case-based mutations: lower, upper, title, camelCase."""

from __future__ import annotations

from collections.abc import Iterator

from mimic.core.candidate import Candidate, Transformation
from mimic.mutators.base import StructuredMutator


class CaseMutator(StructuredMutator):
    """Yields case variations of a word.

    Produces: original, lowercase, UPPERCASE, and Titlecase forms.
    Duplicates are naturally removed downstream by the dedup layer.
    """

    def mutate_candidate(self, candidate: Candidate) -> Iterator[Candidate]:
        word = candidate.value
        for mode, value in (
            ("original", word), ("lower", word.lower()),
            ("upper", word.upper()), ("title", word.title()),
        ):
            yield candidate.derive(value, Transformation("case", (("mode", mode),)))
