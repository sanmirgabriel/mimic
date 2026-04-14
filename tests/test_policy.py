"""Tests for PasswordPolicy."""

from __future__ import annotations

import pytest

from mimic.core.policy import PasswordPolicy


@pytest.fixture
def strict_policy() -> PasswordPolicy:
    return PasswordPolicy(
        min_len=8,
        max_len=20,
        require_upper=True,
        require_lower=True,
        require_digit=True,
        require_special=True,
    )


def test_accepts_valid(strict_policy: PasswordPolicy) -> None:
    assert strict_policy.accepts("Hello@123")


def test_rejects_too_short(strict_policy: PasswordPolicy) -> None:
    assert not strict_policy.accepts("Hi@1")


def test_rejects_too_long(strict_policy: PasswordPolicy) -> None:
    assert not strict_policy.accepts("A" * 21 + "@1a")


def test_rejects_missing_upper(strict_policy: PasswordPolicy) -> None:
    assert not strict_policy.accepts("hello@123")


def test_rejects_missing_lower(strict_policy: PasswordPolicy) -> None:
    assert not strict_policy.accepts("HELLO@123")


def test_rejects_missing_digit(strict_policy: PasswordPolicy) -> None:
    assert not strict_policy.accepts("Hello@abc")


def test_rejects_missing_special(strict_policy: PasswordPolicy) -> None:
    assert not strict_policy.accepts("Hello1234")


def test_permissive_policy_accepts_anything() -> None:
    p = PasswordPolicy()
    assert p.accepts("")
    assert p.accepts("x")
    assert p.accepts("AnyTh1ng!")
