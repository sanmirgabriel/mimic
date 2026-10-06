"""Bounded seed planning. All password mutations remain in the existing engine."""

from dataclasses import dataclass

from mimic.core.candidate import Candidate, Transformation, Origin
from mimic.core.seed import Seed
from mimic.intelligence.builtins import (
    COMMON_NUMBERS, CORPORATE_ROLES, KNOWLEDGE_VERSION, get_service_profile,
)
from mimic.intelligence.models import IntelligenceOptions


@dataclass(frozen=True)
class IntelligencePlan:
    seeds: tuple[Seed, ...] = ()
    numbers: tuple[Candidate, ...] = ()
    years: tuple[int, ...] = ()
    services: tuple[str, ...] = ()
    corporate_roles_active: bool = False


def recent_years(reference_year: int) -> tuple[int, ...]:
    """Current year first, then three previous years; no future years."""
    return tuple(reference_year - offset for offset in range(4))


def _knowledge(value: str, field: str) -> Candidate:
    return Candidate(value, (Origin("knowledge", field, value),))


def _template(left: Candidate, right: Candidate, template_id: str) -> Candidate:
    return left.join(right, left.value + right.value, Transformation("knowledge_template", (
        ("template", template_id), ("left", left.value), ("right", right.value),
        ("version", KNOWLEDGE_VERSION),
    )))


def plan_intelligence(
    options: IntelligenceOptions, organization_terms: tuple[Candidate, ...] = (),
    additional_terms: tuple[Candidate, ...] = (),
) -> IntelligencePlan:
    if not options.enabled:
        return IntelligencePlan()
    if options.reference_year is None:
        raise ValueError("intelligence planning requires a captured reference_year")
    numbers = [_knowledge(value, "common_number") for value in COMMON_NUMBERS] if options.common_numbers else []
    years = recent_years(options.reference_year) if options.recent_years else ()
    numbers.extend(_knowledge(str(year), "recent_year") for year in years)
    profiles = tuple(get_service_profile(value) for value in options.service_profiles)
    roles = [_knowledge(value, "role") for value in CORPORATE_ROLES] if options.corporate_roles else []
    # Profile IDs in fields retain the cause of vocabulary shared by services.
    services = [
        _knowledge(value, f"service.{profile.id}.token")
        for profile in profiles for value in profile.tokens
    ]
    service_roles = [
        _knowledge(value, f"service.{profile.id}.role")
        for profile in profiles for value in profile.roles
    ]
    # Explicit organization/company terms already enter through domain planning.
    # Only adapted supplemental terms (e.g. normalized labels) need new seeds.
    seeds = [Seed(candidate) for candidate in (*additional_terms, *roles, *services, *service_roles)]
    for terms, vocabulary, template_id in (
        (organization_terms, (*roles, *service_roles), "organization_role"),
        (organization_terms, services, "organization_service"),
    ):
        for left in terms:
            for right in vocabulary:
                seeds.append(Seed(_template(left, right, template_id)))
                seeds.append(Seed(_template(right, left, template_id + "_reverse")))
    for profile in profiles:
        for token in profile.tokens:
            left = _knowledge(token, f"service.{profile.id}.token")
            for value in profile.roles:
                right = _knowledge(value, f"service.{profile.id}.role")
                seeds.append(Seed(_template(left, right, "service_role")))
                seeds.append(Seed(_template(right, left, "service_role_reverse")))
    return IntelligencePlan(tuple(dict.fromkeys(seeds)), tuple(numbers), years,
                            tuple(profile.display_name for profile in profiles), bool(roles))
