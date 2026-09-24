"""Shared empty-input filtering and conservative causal input deduplication."""

from collections.abc import Iterable, Iterator

from mimic.core.candidate import Candidate, as_candidate


def nonempty_seed(value: str | Candidate) -> Candidate | None:
    """Drop empty/whitespace-only seeds; preserve nonempty values and origins.

    Profile and file inputs strip at their input boundaries. An explicitly
    supplied Candidate is never silently rewritten here.
    """
    candidate = as_candidate(value)
    return candidate if candidate.value.strip() else None


def unique_seeds(values: Iterable[str | Candidate]) -> Iterator[Candidate]:
    """Skip exact repeated derivations, not distinct causes of an equal value.

    Safe for deterministic transforms of Candidate inputs. Stateful custom
    mutators must not rely on repeated evaluation of identical seeds.
    """
    seen: set[Candidate] = set()
    for value in values:
        candidate = nonempty_seed(value)
        if candidate is not None and candidate not in seen:
            seen.add(candidate)
            yield candidate
