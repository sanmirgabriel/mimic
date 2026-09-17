"""Central generator that orchestrates staged mutator composition, policy, and dedup."""

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

# Default ceiling on how many candidates a single base word may produce
# through the staged pipeline, applied after *each* stage.  This bounds
# peak memory per word instead of only truncating the final result, since
# an uncapped cartesian product across stages (case x leet x affix) can
# explode long before reaching the end of the pipeline.
_DEFAULT_MAX_CANDIDATES_PER_WORD = 5_000


class Generator:
    """Orchestrates word generation through a composed pipeline of mutators.

    Unlike a flat set of independent mutators, *stages* are applied in
    sequence: the output of stage N becomes the input of stage N+1, so a
    word can accumulate transformations (e.g. leet-speak, then an affix)
    instead of each mutator only ever seeing the original word.

    Pipeline, per base word:

    1. ``combine`` (if given) expands the base word into extra sibling
       seeds (e.g. cross-combined names). Each seed — original and
       combine-derived — is then run through the staged pipeline
       independently, so combine never multiplies against leet/affix
       output of *other* names (that would be a second, unrelated
       combinatorial explosion).
    2. Each seed is pushed through ``stages`` in order. At every stage the
       set of live candidates ("frontier") is expanded by calling
       ``stage.mutate()`` on each one, then truncated to
       ``max_candidates_per_word`` before moving to the next stage.
    3. ``reverse`` (if given) is applied directly to each seed as a cheap,
       independent branch — reversing *after* case/leet/affix has already
       run is not a realistic password pattern, so it is not composed.
    4. All produced candidates (across all seeds) are deduplicated via an
       in-memory set and checked against the password policy before being
       yielded, streaming.

    Args:
        base_words: Seed words (names, keywords, etc.).
        stages: Ordered list of mutators to compose in sequence.
        policy: Password policy filter. ``None`` means accept everything.
        combine: Optional mutator that expands a base word into extra
            sibling seeds before the staged pipeline runs.
        reverse: Optional mutator applied to each seed independently of
            ``stages``.
        max_candidates_per_word: Ceiling on live candidates per seed,
            enforced after every stage.
    """

    def __init__(
        self,
        base_words: list[str],
        stages: list[Mutator],
        policy: PasswordPolicy | None = None,
        combine: Mutator | None = None,
        reverse: Mutator | None = None,
        max_candidates_per_word: int = _DEFAULT_MAX_CANDIDATES_PER_WORD,
    ) -> None:
        self.base_words = base_words
        self.stages = stages
        self.policy = policy or PasswordPolicy()
        self.combine = combine
        self.reverse = reverse
        self.max_candidates_per_word = max_candidates_per_word

    def _seeds(self) -> Iterator[str]:
        """Yield each base word plus, when ``combine`` is set, its cross-combinations."""
        yield from self.base_words
        if self.combine is not None:
            for word in self.base_words:
                yield from self.combine.mutate(word)

    def _compose(self, seed: str) -> list[str]:
        """Run *seed* through ``stages`` in sequence, capping the frontier each step.

        When a stage's cap is hit before every candidate in the incoming
        frontier has been processed, the remaining candidates are silently
        dropped from that stage onward. That drop is logged so it's
        observable which stage/seed lost candidates and how many were
        never even attempted (the candidate mid-expansion when the cap hit
        may have had further outputs too, but those aren't counted here —
        counting them would mean generating them, defeating the point of
        the cap).
        """
        frontier: list[str] = [seed]
        for stage in self.stages:
            next_frontier: list[str] = []
            stage_seen: set[str] = set()
            candidates_processed = 0
            cap_hit = False
            for candidate in frontier:
                candidates_processed += 1
                for out in stage.mutate(candidate):
                    if out in stage_seen:
                        continue
                    stage_seen.add(out)
                    next_frontier.append(out)
                    if len(next_frontier) >= self.max_candidates_per_word:
                        cap_hit = True
                        break
                if cap_hit:
                    break
            if cap_hit:
                skipped = len(frontier) - candidates_processed
                logger.warning(
                    "Truncated stage=%s seed=%r cap=%d: %d/%d input "
                    "candidates from the previous stage were never "
                    "processed by this stage (the candidate being expanded "
                    "when the cap hit may also have had further outputs "
                    "that were never generated).",
                    type(stage).__name__,
                    seed,
                    self.max_candidates_per_word,
                    skipped,
                    len(frontier),
                )
            frontier = next_frontier
        return frontier

    def _raw_candidates(self) -> Iterator[str]:
        """Yield every candidate produced by the composed pipeline for every seed."""
        for seed in self._seeds():
            yield from self._compose(seed)
            if self.reverse is not None:
                yield from self.reverse.mutate(seed)

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
