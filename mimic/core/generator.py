"""Central generator that orchestrates mutators, policy, and dedup."""

from __future__ import annotations

import logging
from collections.abc import Iterator

from mimic.core.policy import PasswordPolicy
from mimic.mutators.base import Mutator

logger = logging.getLogger(__name__)

# Threshold: if the estimated output could exceed this, we still use a set
# for dedup but flush periodically.  For truly huge runs a bloom filter would
# be better, but we avoid external deps per the spec.
_DEDUP_WARN_THRESHOLD = 100_000


class Generator:
    """Orchestrates word generation through a pipeline of mutators.

    The generation pipeline works as follows:

    1. Each base word is fed through every mutator, collecting raw candidates.
    2. Candidates are deduplicated via an in-memory set.
    3. Each unique candidate is checked against the password policy.
    4. Accepted candidates are yielded one at a time (streaming).

    Args:
        base_words: Seed words (names, keywords, etc.).
        mutators: Ordered list of mutators to apply.
        policy: Password policy filter.  ``None`` means accept everything.
    """

    def __init__(
        self,
        base_words: list[str],
        mutators: list[Mutator],
        policy: PasswordPolicy | None = None,
    ) -> None:
        self.base_words = base_words
        self.mutators = mutators
        self.policy = policy or PasswordPolicy()

    def _raw_candidates(self) -> Iterator[str]:
        """Yield every candidate produced by running all mutators on all base words."""
        for word in self.base_words:
            for mutator in self.mutators:
                yield from mutator.mutate(word)

    def generate(self) -> Iterator[str]:
        """Yield unique, policy-compliant passwords in a streaming fashion.

        Deduplication uses an in-memory set.  A warning is logged when the
        set grows past the threshold.
        """
        seen: set[str] = set()
        warned = False
        for candidate in self._raw_candidates():
            if candidate in seen:
                continue
            seen.add(candidate)
            if not warned and len(seen) > _DEDUP_WARN_THRESHOLD:
                logger.warning(
                    "Dedup set exceeded %d entries; consider narrowing "
                    "mutator scope for lower memory usage.",
                    _DEDUP_WARN_THRESHOLD,
                )
                warned = True
            if self.policy.accepts(candidate):
                yield candidate
