"""Cross-combination of names (first+last, initials, dotted forms, etc.)."""

from __future__ import annotations

from collections.abc import Iterator

from mimic.mutators.base import Mutator


class CombineMutator(Mutator):
    """Produces cross-combinations of a name with all other names.

    For each pair ``(a, b)`` it yields forms commonly seen in usernames
    and passwords::

        ab, ba, a.b, a_b, a-b, a<initial>b, <initial>a+b, ...

    Args:
        all_names: The full list of base names used for cross-pairing.
        separators: Characters placed between combined names.
    """

    def __init__(
        self,
        all_names: list[str],
        separators: str = "@!#_.",
    ) -> None:
        self.all_names = [n.lower() for n in all_names]
        self.separators = list(separators)

    def mutate(self, word: str) -> Iterator[str]:
        w = word.lower()
        for other in self.all_names:
            if other == w:
                continue
            # Concatenations
            yield w + other
            yield other + w
            # Initial + full
            yield w[0] + other
            yield other[0] + w
            # Separated
            for sep in self.separators:
                yield w + sep + other
                yield other + sep + w
