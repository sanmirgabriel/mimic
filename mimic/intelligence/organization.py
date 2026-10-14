"""Bounded lexical organization seeds; no password mutations or inferred words."""

from dataclasses import dataclass
import json
import unicodedata

from mimic.core.candidate import Candidate, Transformation

MAX_NAMES = 8
MAX_NAME_LENGTH = 256
MAX_COMPONENTS = 8
MAX_VARIANTS_PER_NAME = 24
VERSION = "organization-name-v1"
DELIMITERS = "-_ /\u2013\u2014"


@dataclass(frozen=True)
class OrganizationNamePlan:
    candidates: tuple[Candidate, ...] = ()
    limited_names: int = 0


def _components(value: str) -> tuple[str, ...]:
    # A single linear scan. Other punctuation is preserved by falling back to
    # the original seed, rather than silently deleting part of a brand name.
    parts: list[str] = []
    current: list[str] = []
    for character in value:
        if character.isspace() or character in DELIMITERS:
            if current:
                parts.append("".join(current))
                current.clear()
        elif unicodedata.category(character)[0] in "LNM":
            current.append(character)
        else:
            return ()
    if current:
        parts.append("".join(current))
    return tuple(parts)


def _initial_title(value: str) -> str:
    # Do not title-case the joined string or split inside CamelCase brands.
    return value[:1].upper() + value[1:].lower()


def plan_organization_names(
    terms: tuple[Candidate, ...], *, organization_name: str = "",
    organization_id: str = "",
) -> OrganizationNamePlan:
    """First eight distinct explicit names; <=24 variants each, <=256 chars.

    Originals still enter through historical planning. Names with >8 components
    get only three whole-name concatenations; >256 chars or ambiguous punctuation
    get no additional seeds. No permutations, stop words or pair products.
    """
    candidates: dict[str, Candidate] = {}
    names: set[str] = set()
    limited = 0
    for term in terms:
        if term.value in names:
            continue
        names.add(term.value)
        if len(names) > MAX_NAMES or len(term.value) > MAX_NAME_LENGTH:
            limited += 1
            continue
        parts = _components(term.value)
        # Single lexical brands already have the historical Case pipeline.
        # Replaying those forms as seeds would invent extra reverse branches.
        if len(parts) < 2:
            continue
        lower = tuple(part.lower() for part in parts)
        title = tuple(_initial_title(part) for part in parts)
        variants: list[tuple[str, str, str, str]] = []
        name_limited = len(parts) > MAX_COMPONENTS

        def add(value, rule, case, component=""):
            variants.append((value, rule, case, component))

        # Independent lexical forms preserve original case as well as the
        # requested component choices even when later Case/Leet frontiers cap.
        if len(parts) <= MAX_COMPONENTS:
            for index, part in enumerate(parts):
                choices = (("original", part), ("initial_title", title[index]))
                if len(parts) <= 4:
                    choices = (("original", part), ("lower", lower[index]), choices[1])
                for mode, value in choices:
                    add(value, "component", mode, str(index))
        add("".join(parts), "concatenate", "original")
        add("".join(lower), "concatenate", "lower")
        add("".join(title), "concatenate", "all_initial_title")
        if 2 <= len(parts) <= 4:
            for index in range(len(parts)):
                chosen = list(lower)
                chosen[index] = title[index]
                add("".join(chosen), "concatenate", "single_initial_title", str(index))
            # A bounded acronym/brand-style first component, no uppercase
            # subset enumeration. The original spelling is always retained.
            if len(parts[0]) <= 8:
                add(parts[0].upper() + "".join(title[1:]), "concatenate",
                    "first_upper_rest_initial_title")
        if 2 <= len(parts) <= MAX_COMPONENTS:
            initials = "".join(part[0] for part in parts)
            add(initials.upper(), "acronym", "upper")
            add(initials.lower(), "acronym", "lower")
        local: set[str] = {term.value}
        emitted = 0
        organization_origin = any(o.source == "organization" for o in term.origins)
        for value, rule, case, component in variants:
            if len(value) > MAX_NAME_LENGTH:
                name_limited = True
                continue
            if value in local:
                continue
            local.add(value)
            if emitted >= MAX_VARIANTS_PER_NAME:
                name_limited = True
                break
            emitted += 1
            step = Transformation("organization_name", (
                ("input", term.value), ("components", json.dumps(parts, ensure_ascii=True)),
                ("rule", rule), ("case", case), ("component", component), ("version", VERSION),
                ("organization", organization_name if organization_origin else term.value),
                ("organization_id", organization_id if organization_origin else ""),
            ))
            candidates.setdefault(value, term.derive(value, step))
        if name_limited:
            limited += 1
    return OrganizationNamePlan(tuple(candidates.values()), limited)
