"""Tests for the LeetMutator."""

from __future__ import annotations

import pytest

from mimic.mutators.leet import LeetMutator


@pytest.fixture
def partial_mutator() -> LeetMutator:
    return LeetMutator(mode="partial", max_subs=2)


@pytest.fixture
def full_mutator() -> LeetMutator:
    return LeetMutator(mode="full")


def test_partial_single_eligible(partial_mutator: LeetMutator) -> None:
    """Word with one eligible char yields exactly one partial mutation."""
    results = list(partial_mutator.mutate("bob"))
    # 'o' -> '0', only one position => one combination
    assert "b0b" in results
    assert len(results) == 1


def test_partial_two_eligible(partial_mutator: LeetMutator) -> None:
    """Word with two eligible chars yields C(2,1)+C(2,2) = 3 mutations."""
    results = list(partial_mutator.mutate("ace"))
    # a->@, e->3, positions: 0 and 2
    # C(2,1)=2 single subs + C(2,2)=1 double sub = 3
    assert len(results) == 3
    assert "@ce" in results
    assert "ac3" in results
    assert "@c3" in results


def test_partial_respects_max_subs() -> None:
    """max_subs=1 limits to single-char replacements only."""
    m = LeetMutator(mode="partial", max_subs=1)
    results = list(m.mutate("ace"))
    assert len(results) == 2  # only C(2,1)=2
    assert "@c3" not in results


def test_full_replaces_all(full_mutator: LeetMutator) -> None:
    """Full mode replaces every eligible character at once."""
    results = list(full_mutator.mutate("east"))
    assert results == ["3@$7"]


def test_none_mode_is_identity() -> None:
    """Mode 'none' yields the original word unchanged."""
    m = LeetMutator(mode="none")
    assert list(m.mutate("hello")) == ["hello"]


def test_no_eligible_chars(partial_mutator: LeetMutator) -> None:
    """Word with no leet-eligible chars yields original."""
    results = list(partial_mutator.mutate("hymn"))
    assert results == ["hymn"]
