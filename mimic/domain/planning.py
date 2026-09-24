"""Reusable planning from domain context to the profile-independent engine."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import Enum

from mimic.core.candidate import Candidate, Origin
from mimic.core.generator import Generator
from mimic.core.policy import PasswordPolicy
from mimic.core.seed import Seed
from mimic.domain.context import ExtractedFact
from mimic.domain.models import Generation, Organization, SourceType
from mimic.mutators.affix import AffixMutator
from mimic.mutators.case import CaseMutator
from mimic.mutators.combine import CombineMutator
from mimic.mutators.date import DateMutator
from mimic.mutators.leet import LeetMutator
from mimic.mutators.reverse import ReverseMutator
from mimic.profile.loader import build_plan


class BehaviorPattern(str, Enum):
    TARGET_DATE = "target_date"
    TARGET_YEAR = "target_year"
    TARGET_DATE_SPECIAL = "target_date_special"
    TARGET_SPECIAL_DATE = "target_special_date"


@dataclass
class PreparedGeneration:
    generator: Generator
    patterns: tuple[BehaviorPattern, ...]


def _organization_seeds(organization: Organization) -> Iterator[Seed]:
    for field, values in (
        ("name", [organization.name]), ("alias", organization.aliases),
        ("keyword", organization.keywords), ("location", organization.locations),
        ("domain", organization.domains),
    ):
        for value in values:
            if value.strip():
                yield Seed(Candidate(value, (Origin("organization", field, value),)))


def prepare_generation(
    generation: Generation, *,
    base_candidates: Iterable[Candidate] = (),
    isolated_candidates: Iterable[Candidate] = (),
    number_candidates: Iterable[Candidate] = (),
    context_facts: Iterable[ExtractedFact] = (),
    extra_seeds: Iterable[Seed] = (),
) -> PreparedGeneration:
    """Create the same engine request for CLI and future interfaces.

    Explicit base candidates are the only default Combine partners. The
    target's name/aliases join that group; organization and corpora do not.
    """
    options = generation.options
    base = list(base_candidates)
    isolated = list(isolated_candidates)
    numbers = list(number_candidates)
    if generation.target is not None:
        plan = build_plan(generation.target.profile)
        base.extend(plan.base_candidates)
        isolated.extend(plan.isolated_candidates)
        numbers.extend(plan.number_candidates)
        if not generation.target.profile.nome and generation.target.name.strip():
            base.append(Candidate(generation.target.name, (
                Origin("target", "name", generation.target.name),
            )))
    context_isolated: list[Candidate] = []
    for fact in context_facts:
        if fact.field == "data_nascimento":
            numbers.extend(DateMutator().mutate_candidate(fact.candidate))
        elif fact.field == "nome" or fact.field == "apelidos":
            base.append(fact.candidate)
        else:
            context_isolated.append(fact.candidate)
    isolated.extend(context_isolated)

    organization = generation.organization or (
        generation.target.organization if generation.target else None
    )

    def source_seeds() -> Iterator[Seed]:
        if organization is not None:
            yield from _organization_seeds(organization)
            for date in organization.relevant_dates:
                date_candidate = Candidate(date, (Origin("organization", "relevant_date", date),))
                for token in DateMutator().mutate_candidate(date_candidate):
                    yield Seed(token)
        for seed in extra_seeds:
            if not isinstance(seed, Seed):
                raise TypeError("extra_seeds must contain Seed objects")
            if seed.combinable and any(
                origin.source in (SourceType.DATASET.value, SourceType.READY_CANDIDATE.value)
                for origin in seed.candidate.origins
            ):
                raise ValueError("Dataset and ready candidates cannot be combinable")
            yield seed

    policy = PasswordPolicy(
        min_len=options.min_len, max_len=options.max_len,
        require_upper=options.require_upper, require_lower=options.require_lower,
        require_digit=options.require_digit, require_special=options.require_special,
    )
    generator = Generator(
        base_words=base,
        isolated_seeds=isolated,
        stages=[CaseMutator(), LeetMutator(options.leet_mode),
                AffixMutator(numbers=numbers, separators=options.separators)],
        combine=CombineMutator(base, options.separators) if options.combine else None,
        reverse=ReverseMutator(), policy=policy,
        max_candidates_per_word=options.max_candidates_per_word,
        seeds=source_seeds(),
    )
    patterns = (
        (BehaviorPattern.TARGET_DATE, BehaviorPattern.TARGET_YEAR,
         BehaviorPattern.TARGET_DATE_SPECIAL, BehaviorPattern.TARGET_SPECIAL_DATE)
        if numbers and base else ()
    )
    return PreparedGeneration(generator, patterns)
