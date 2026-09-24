"""Cross-combination of names (first+last, initials, dotted forms, etc.)."""

from __future__ import annotations

from collections.abc import Iterator

from mimic.core.candidate import Candidate, Transformation, as_candidate
from mimic.mutators.base import StructuredMutator


class CombineMutator(StructuredMutator):
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
        all_names: list[str | Candidate],
        separators: str = "@!#_.",
    ) -> None:
        self._partners = tuple(as_candidate(n) for n in all_names)
        self.separators = list(separators)

    @property
    def all_names(self) -> list[str]:
        """Legacy lowercase textual introspection; returns a detached list.

        Configure partners through the constructor. Editing this projection
        does not alter the structured operands or their causal metadata.
        """
        return [partner.value.lower() for partner in self._partners]

    def mutate_candidate(self, candidate: Candidate) -> Iterator[Candidate]:
        w = candidate.value.lower()
        for partner in self._partners:
            other = partner.value.lower()
            if other == w:
                continue
            # Concatenations
            yield self._combine(candidate, partner, w + other, "full", "")
            yield self._combine(partner, candidate, other + w, "full", "")
            # Initial + full
            yield self._combine(candidate, partner, w[0] + other, "initial", "")
            yield self._combine(partner, candidate, other[0] + w, "initial", "")
            # Separated
            for sep in self.separators:
                yield self._combine(candidate, partner, w + sep + other, "full", sep)
                yield self._combine(partner, candidate, other + sep + w, "full", sep)

    @staticmethod
    def _combine(
        left: Candidate, right: Candidate, value: str, left_form: str, separator: str,
    ) -> Candidate:
        return left.join(right, value, Transformation("combine", (
            ("left", left.value), ("right", right.value),
            ("left_form", left_form), ("right_form", "full"),
            ("normalization", "lower"), ("separator", separator),
            ("left_steps", str(len(left.transformations))),
            ("right_steps", str(len(right.transformations))),
        )))
