"""Abstract base class for all mutators."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator


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
