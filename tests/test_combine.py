"""Tests for CombineMutator."""

from __future__ import annotations

from mimic.mutators.combine import CombineMutator


def test_basic_cross_combination() -> None:
    m = CombineMutator(all_names=["joao", "silva"], separators="._")
    results = list(m.mutate("joao"))
    # Should contain concatenations and initial forms
    assert "joaosilva" in results
    assert "silvajoao" in results
    assert "jsilva" in results
    assert "sjoao" in results


def test_separator_forms() -> None:
    m = CombineMutator(all_names=["joao", "silva"], separators=".")
    results = list(m.mutate("joao"))
    assert "joao.silva" in results
    assert "silva.joao" in results


def test_skips_self_combination() -> None:
    m = CombineMutator(all_names=["alice", "bob"], separators="")
    results = list(m.mutate("alice"))
    # Should not combine alice with itself
    assert "alicealice" not in results
    assert "alicebob" in results


def test_three_names_combines_with_others() -> None:
    m = CombineMutator(all_names=["ana", "bob", "carl"], separators="")
    results = list(m.mutate("bob"))
    assert "bobana" in results
    assert "bobcarl" in results
    assert "bobbob" not in results
