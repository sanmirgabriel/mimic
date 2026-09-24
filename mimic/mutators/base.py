"""Abstract base class for all mutators."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from mimic.core.candidate import Candidate, Transformation, as_candidate


class Mutator(ABC):
    """Base class that every mutator must inherit from.

    A mutator receives a single word and yields zero or more mutations of it.
    Mutators are composable: the Generator chains them in sequence so each
    mutator only needs to worry about its own transformation.
    """

    @abstractmethod
    def mutate(self, word: str) -> Iterator[str]:
        """Yield mutations derived from *word*.

        Args:
            word: The base word to transform.

        Yields:
            Mutated strings.
        """

    def mutate_candidate(self, candidate: Candidate) -> Iterator[Candidate]:
        """Compatibility for external string-only mutators: an opaque call.

        Records the actual input/output and implementation, never guesses its
        internal operations. Override this method for detailed provenance.
        """
        for value in self.mutate(candidate.value):
            yield candidate.derive(value, Transformation("legacy", (
                ("mutator", f"{type(self).__module__}.{type(self).__qualname__}"),
                ("input", candidate.value), ("output", value),
            )))


class StructuredMutator(Mutator):
    """Built-in mutators implement one structured path; strings are a view."""

    def mutate(self, word: str) -> Iterator[str]:
        for candidate in self.mutate_candidate(as_candidate(word)):
            yield candidate.value

    @abstractmethod
    def mutate_candidate(self, candidate: Candidate) -> Iterator[Candidate]:
        """Produce a value and its causal metadata together."""
