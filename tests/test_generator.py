"""Tests for the Generator orchestrator."""

from __future__ import annotations

from mimic.core.generator import Generator
from mimic.core.policy import PasswordPolicy
from mimic.mutators.affix import AffixMutator
from mimic.mutators.case import CaseMutator


def test_generates_without_numbers() -> None:
    """Generator must produce output even when no numbers are provided."""
    gen = Generator(
        base_words=["admin"],
        mutators=[CaseMutator()],
    )
    results = list(gen.generate())
    assert len(results) > 0
    assert "admin" in results
    assert "ADMIN" in results


def test_dedup_removes_duplicates() -> None:
    """Identical candidates from different mutators are deduplicated."""
    gen = Generator(
        base_words=["test"],
        mutators=[CaseMutator(), CaseMutator()],  # two identical mutators
    )
    results = list(gen.generate())
    assert len(results) == len(set(results))


def test_policy_filters_results() -> None:
    """Only candidates matching the policy survive."""
    policy = PasswordPolicy(min_len=6)
    gen = Generator(
        base_words=["hi"],
        mutators=[
            CaseMutator(),
            AffixMutator(numbers=["2024"]),
        ],
        policy=policy,
    )
    results = list(gen.generate())
    assert all(len(r) >= 6 for r in results)
    # "hi" alone (2 chars) must not appear
    assert "hi" not in results


def test_streaming_yields_individually() -> None:
    """generate() returns an iterator, not a list."""
    gen = Generator(
        base_words=["root"],
        mutators=[CaseMutator()],
    )
    it = gen.generate()
    first = next(it)
    assert isinstance(first, str)
