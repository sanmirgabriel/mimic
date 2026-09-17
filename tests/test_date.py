"""Tests for the DateMutator."""

from __future__ import annotations

import pytest

from mimic.mutators.date import DateMutator


def test_full_date_yields_all_formats() -> None:
    """DD/MM/AAAA yields day/month combos plus year-dependent forms."""
    results = list(DateMutator().mutate("05/09/2000"))
    assert results == [
        "0509",       # day, then month
        "0905",       # month, then day (day/month inverted)
        "509",        # day unpadded + month padded
        "905",        # month unpadded + day padded
        "2000",       # year alone
        "00",         # year, last two digits
        "05092000",   # full date, day-month-year
    ]


def test_no_year_skips_year_dependent_forms() -> None:
    """DD/MM (no year) yields only the four year-independent forms, no error."""
    results = list(DateMutator().mutate("05/09"))
    assert results == ["0509", "0905", "509", "905"]
    assert "2000" not in results


def test_day_month_inverted_pair_present() -> None:
    """Both day-first and month-first orderings are produced."""
    results = list(DateMutator().mutate("12/03/1995"))
    assert "1203" in results  # day then month
    assert "0312" in results  # month then day


def test_two_digit_year_form() -> None:
    results = list(DateMutator().mutate("01/01/1995"))
    assert "95" in results
    assert "1995" in results


def test_full_concatenated_date_form() -> None:
    results = list(DateMutator().mutate("01/01/1995"))
    assert "01011995" in results


def test_double_digit_day_and_month_no_padding_difference() -> None:
    """When day and month are both already two digits, padded/unpadded forms collapse (deduped)."""
    results = list(DateMutator().mutate("12/11"))
    # day=12, month=11: d==dd and m==mm, so dd+mm==d+mm and mm+dd==m+dd.
    assert results == ["1211", "1112"]


def test_duplicate_tokens_are_deduped() -> None:
    """A palindromic-ish date (day == month) must not repeat identical tokens."""
    results = list(DateMutator().mutate("09/09/1999"))
    assert len(results) == len(set(results))


@pytest.mark.parametrize(
    "bad_input",
    ["not-a-date", "32/01/2000", "05/13/2000", "05-09-2000", "05/09/20000"],
)
def test_invalid_date_raises(bad_input: str) -> None:
    with pytest.raises(ValueError):
        list(DateMutator().mutate(bad_input))
