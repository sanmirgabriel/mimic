"""Tests for the Generator orchestrator."""

from __future__ import annotations

import logging

from mimic.core.generator import Generator
from mimic.core.policy import PasswordPolicy
from mimic.mutators.affix import AffixMutator
from mimic.mutators.case import CaseMutator
from mimic.mutators.leet import LeetMutator


def test_generates_without_numbers() -> None:
    """Generator must produce output even when no numbers are provided."""
    gen = Generator(
        base_words=["admin"],
        stages=[CaseMutator()],
    )
    results = list(gen.generate())
    assert len(results) > 0
    assert "admin" in results
    assert "ADMIN" in results


def test_dedup_removes_duplicates() -> None:
    """Identical candidates from different stages are deduplicated."""
    gen = Generator(
        base_words=["test"],
        stages=[CaseMutator(), CaseMutator()],  # two identical stages
    )
    results = list(gen.generate())
    assert len(results) == len(set(results))


def test_policy_filters_results() -> None:
    """Only candidates matching the policy survive."""
    policy = PasswordPolicy(min_len=6)
    gen = Generator(
        base_words=["hi"],
        stages=[
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
        stages=[CaseMutator()],
    )
    it = gen.generate()
    first = next(it)
    assert isinstance(first, str)


def test_stages_compose_case_leet_affix() -> None:
    """Stages must chain: a candidate can carry case + leet + affix at once.

    This is the core guarantee of the staged pipeline: "Pedro" run through
    Case -> Leet -> Affix should be able to produce "P3dro0905@", which is
    impossible if each stage only ever sees the original base word.
    """
    gen = Generator(
        base_words=["Pedro"],
        stages=[
            CaseMutator(),
            LeetMutator(mode="partial", max_subs=2),
            AffixMutator(numbers=["0905"], separators="@"),
        ],
    )
    results = set(gen.generate())
    assert "P3dro0905@" in results


def test_deterministic_output_order() -> None:
    """Same input configuration must yield the same candidate list, in order."""
    def build() -> Generator:
        return Generator(
            base_words=["Pedro", "Maria"],
            stages=[
                CaseMutator(),
                LeetMutator(mode="partial", max_subs=2),
                AffixMutator(numbers=["0905", "2024"], separators="@_"),
            ],
        )

    first_run = list(build().generate())
    second_run = list(build().generate())
    assert first_run == second_run


def test_max_candidates_per_word_is_respected() -> None:
    """The per-stage cap bounds the candidates produced for a single word."""
    numbers = [str(n) for n in range(1000, 1100)]  # 100 numbers
    gen = Generator(
        base_words=["ace"],  # 'a' and 'e' both leet-eligible
        stages=[
            CaseMutator(),
            LeetMutator(mode="partial", max_subs=2),
            AffixMutator(numbers=numbers, separators="@!#_."),
        ],
        max_candidates_per_word=10,
    )
    results = list(gen.generate())
    # Single base word, single seed: final frontier is capped at 10.
    assert len(results) <= 10


def test_combine_seeds_flow_through_pipeline() -> None:
    """combine-derived seeds (e.g. cross-combined names) get the full pipeline too."""
    from mimic.mutators.combine import CombineMutator

    gen = Generator(
        base_words=["joao", "silva"],
        stages=[CaseMutator()],
        combine=CombineMutator(all_names=["joao", "silva"], separators=""),
    )
    results = list(gen.generate())
    assert "joaosilva" in results
    assert "JOAOSILVA" in results  # combine seed also went through CaseMutator


def test_truncation_logs_warning_with_stage_and_seed(caplog) -> None:
    """Hitting the per-stage cap mid-frontier must be logged, not silent.

    Two base words feed a high fan-out Affix stage with a tiny cap, so the
    cap is reached while expanding the first word's case-variants and the
    second word's candidates never even start this stage — exactly the
    "silent starvation" scenario flagged before adding this telemetry.
    """
    numbers = [str(n) for n in range(1000, 1100)]  # 100 numbers -> huge fan-out
    gen = Generator(
        base_words=["ace", "bob"],
        stages=[
            CaseMutator(),
            AffixMutator(numbers=numbers, separators="@!#_."),
        ],
        max_candidates_per_word=5,
    )
    with caplog.at_level(logging.WARNING, logger="mimic.core.generator"):
        list(gen.generate())

    truncation_records = [
        r for r in caplog.records if "Truncated stage=" in r.getMessage()
    ]
    assert truncation_records, "expected at least one truncation warning"

    message = truncation_records[0].getMessage()
    assert "AffixMutator" in message
    assert "cap=5" in message
    # Case produces 3 unique variants (ace/ACE/Ace) per seed; the cap hits
    # while expanding the first one, so 2 of the 3 never get processed.
    assert "2/3 input candidates" in message

    # Both base words truncate independently, each identified by its own seed.
    seeds_in_warnings = {r.getMessage() for r in truncation_records}
    assert any("seed='ace'" in m for m in seeds_in_warnings)
    assert any("seed='bob'" in m for m in seeds_in_warnings)


def test_no_truncation_warning_when_cap_not_hit(caplog) -> None:
    """A cap large enough to never bind must not emit truncation warnings."""
    gen = Generator(
        base_words=["ace"],
        stages=[CaseMutator(), AffixMutator(numbers=["2024"])],
        max_candidates_per_word=5000,
    )
    with caplog.at_level(logging.WARNING, logger="mimic.core.generator"):
        list(gen.generate())
    assert not any(
        "Truncated stage=" in r.getMessage() for r in caplog.records
    )


def test_reverse_is_independent_of_staged_pipeline() -> None:
    """reverse applies to the raw seed only, not to case/leet/affix output."""
    from mimic.mutators.reverse import ReverseMutator

    gen = Generator(
        base_words=["abc"],
        stages=[CaseMutator()],
        reverse=ReverseMutator(),
    )
    results = list(gen.generate())
    assert "cba" in results
    # A case variant reversed (e.g. "CBA") is not produced, since reverse
    # only ever sees the original seed, not staged output.
    assert "CBA" not in results
