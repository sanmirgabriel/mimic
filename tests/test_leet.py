"""Tests for the LeetMutator."""

from __future__ import annotations

import pytest

from mimic.core.candidate import Candidate, Origin, Transformation
from mimic.mutators.leet import LeetMutator


@pytest.fixture
def partial_mutator() -> LeetMutator:
    return LeetMutator(mode="partial", max_subs=2)


@pytest.fixture
def full_mutator() -> LeetMutator:
    return LeetMutator(mode="full")


def test_partial_single_eligible(partial_mutator: LeetMutator) -> None:
    """Word with one eligible char yields original, then one mutation."""
    results = list(partial_mutator.mutate("bob"))
    assert results == ["bob", "b0b"]


def test_partial_two_eligible(partial_mutator: LeetMutator) -> None:
    """Original precedes C(2,1)+C(2,2) = 3 mutations."""
    results = list(partial_mutator.mutate("ace"))
    assert results == ["ace", "@ce", "ac3", "@c3"]


def test_partial_respects_max_subs() -> None:
    """max_subs=1 yields original and every single-char replacement."""
    m = LeetMutator(mode="partial", max_subs=1)
    results = list(m.mutate("ace"))
    assert results == ["ace", "@ce", "ac3"]


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


def test_partial_preserves_original_casing(partial_mutator: LeetMutator) -> None:
    """Untouched letters keep their original case; only leet-able ones change."""
    results = list(partial_mutator.mutate("Pedro"))
    # 'e' (idx1) and 'o' (idx4) are eligible; 'P', 'd', 'r' must stay as-is.
    assert "P3dro" in results
    assert "Pedr0" in results
    assert "P3dr0" in results
    assert "p3dro" not in results  # would mean case got dropped


def test_full_preserves_original_casing() -> None:
    """Full mode also keeps case on characters it doesn't substitute."""
    m = LeetMutator(mode="full")
    results = list(m.mutate("PEDRO"))
    assert results == ["P3DR0"]


def test_partial_preserves_identity_and_exact_causal_history() -> None:
    previous = Transformation("case", (("mode", "lower"),))
    original = Candidate("ace", (Origin("profile", "nome", "Ace"),), (previous,))
    a = Transformation("leet", (("mode", "partial"), ("from", "a"),
                                ("to", "@"), ("position", "0")))
    e = Transformation("leet", (("mode", "partial"), ("from", "e"),
                                ("to", "3"), ("position", "2")))
    results = list(LeetMutator("partial", 2).mutate_candidate(original))
    assert results[0] is original
    assert results == [original,
        Candidate("@ce", original.origins, (previous, a)),
        Candidate("ac3", original.origins, (previous, e)),
        Candidate("@c3", original.origins, (previous, a, e))]


def test_partial_repeated_occurrences_keep_original_offsets() -> None:
    original = Candidate("pass", (Origin("test", "word", "pass"),))
    results = list(LeetMutator("partial", 2).mutate_candidate(original))
    assert [c.value for c in results] == [
        "pass", "p@ss", "pa$s", "pas$", "p@$s", "p@s$", "pa$$"]
    assert [tuple(dict(t.params)["position"] for t in c.transformations)
            for c in results] == [(), ("1",), ("2",), ("3",),
                                  ("1", "2"), ("1", "3"), ("2", "3")]
    assert all(c.origins == original.origins for c in results)


@pytest.mark.parametrize("word,expected", [
    ("Aa", ["Aa", "@a", "A@", "@@"]),
    ("aa", ["aa", "@a", "a@", "@@"]),
    ("İaE", ["İaE", "İ@E", "İa3", "İ@3"]),
    ("áa", ["áa", "á@"]),
    ("a\u0301a", ["a\u0301a", "@\u0301a", "a\u0301@", "@\u0301@"]),
])
def test_partial_case_unicode_and_repetition_are_unique_and_ordered(word, expected):
    results = list(LeetMutator("partial").mutate(word))
    assert results == expected
    assert len(results) == len(set(results))


@pytest.mark.parametrize("mode", ["none", "partial", "full"])
@pytest.mark.parametrize("word", ["hymn", "İ", "áçß", ""])
def test_no_eligible_characters_preserve_candidate_exactly_once(mode, word):
    original = Candidate(word, (Origin("test", "word", word),),
                         (Transformation("case", (("mode", "original"),)),))
    results = list(LeetMutator(mode).mutate_candidate(original))
    assert results == [original]
    assert results[0] is original


def test_partial_max_subs_above_eligible_count() -> None:
    assert list(LeetMutator("partial", 10).mutate("bob")) == ["bob", "b0b"]


@pytest.mark.parametrize("max_subs", [0, -1, -10])
def test_partial_nonpositive_max_subs_preserves_original(max_subs):
    # These integers were already accepted; no new constructor validation.
    original = Candidate("ace")
    results = list(LeetMutator("partial", max_subs).mutate_candidate(original))
    assert results == [original]
    assert results[0] is original


@pytest.mark.parametrize("max_subs", [None, "2", 1.5])
def test_partial_retains_existing_noninteger_errors(max_subs):
    mutator = LeetMutator("partial", max_subs)
    with pytest.raises(TypeError):
        list(mutator.mutate("ace"))


@pytest.mark.parametrize("max_subs,expected", [
    (False, ["ace"]), (True, ["ace", "@ce", "ac3"]),
    (10.0, ["ace", "@ce", "ac3", "@c3"]),
])
def test_partial_retains_existing_permissive_max_subs(max_subs, expected):
    # min() clamps 10.0 to the integer eligible count; bool remains int-like.
    assert list(LeetMutator("partial", max_subs).mutate("ace")) == expected
