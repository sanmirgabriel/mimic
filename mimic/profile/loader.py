"""Load a TargetProfile from disk and turn it into generation inputs.

This module is the only place that knows how profile fields map onto
mutators. ``core/`` never imports from here -- ``profile/`` depends on
``core/`` (for ``DateMutator``), never the other way around.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from mimic.mutators.date import DateMutator
from mimic.mutators.leet import LeetMutator
from mimic.profile.schema import TargetProfile


def load_profile_file(path: str) -> TargetProfile:
    """Read a ``.yaml``/``.yml``/``.json`` profile file into a ``TargetProfile``.

    Raises:
        ImportError: a ``.yaml``/``.yml`` file was given but PyYAML isn't
            installed (it's an optional dependency -- see the ``profile``
            extra in ``pyproject.toml``).
        ValueError: unsupported extension, malformed top-level structure,
            or a field the schema doesn't recognize.
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")

    if p.suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as exc:
            raise ImportError(
                "Reading a YAML profile requires PyYAML. Install it with "
                '`pip install -e ".[profile]"`, or use a .json profile instead.'
            ) from exc
        data = yaml.safe_load(text) or {}
    elif p.suffix == ".json":
        data = json.loads(text) if text.strip() else {}
    else:
        raise ValueError(
            f"Unsupported profile file extension: {p.suffix!r} "
            "(use .yaml, .yml, or .json)"
        )

    if not isinstance(data, dict):
        raise ValueError(
            "Profile file must contain a mapping of field -> value at the top level"
        )
    return TargetProfile.from_dict(data)


@dataclass
class ProfilePlan:
    """Concrete generation inputs derived from a ``TargetProfile``, plus
    origin metadata used for debug-mode traceability.

    Args:
        base_words: Combinable seeds (``nome`` + ``apelidos``) -- these are
            the ones ``--combine`` is allowed to cross-pair.
        isolated_seeds: Seeds that go through the full mutation pipeline
            but must never be cross-combined with unrelated fields (e.g.
            ``time_futebol``, ``empresa``, ``pet``).
        numbers: Digit tokens for ``AffixMutator``, currently only
            ``data_nascimento`` expanded via ``DateMutator``.
        seed_field: Lowercased seed text -> human-readable ``field=value``
            label, for reverse-attribution in debug mode.
        number_field: Number token -> human-readable ``field=value`` label,
            for reverse-attribution in debug mode.
    """

    base_words: list[str] = field(default_factory=list)
    isolated_seeds: list[str] = field(default_factory=list)
    numbers: list[str] = field(default_factory=list)
    seed_field: dict[str, str] = field(default_factory=dict)
    number_field: dict[str, str] = field(default_factory=dict)


def build_plan(profile: TargetProfile) -> ProfilePlan:
    """Route each profile field to the mutator(s)/seed group it belongs in."""
    plan = ProfilePlan()

    if profile.nome:
        plan.base_words.append(profile.nome)
        plan.seed_field[profile.nome.lower()] = f"nome={profile.nome}"

    for apelido in profile.apelidos:
        plan.base_words.append(apelido)
        plan.seed_field[apelido.lower()] = f"apelidos={apelido}"

    for field_name, value in (
        ("time_futebol", profile.time_futebol),
        ("empresa", profile.empresa),
        ("pet", profile.pet),
    ):
        if value:
            plan.isolated_seeds.append(value)
            plan.seed_field[value.lower()] = f"{field_name}={value}"

    if profile.data_nascimento:
        tokens = list(DateMutator().mutate(profile.data_nascimento))
        plan.numbers.extend(tokens)
        label = f"data_nascimento={profile.data_nascimento}"
        for token in tokens:
            plan.number_field[token] = label

    return plan


def explain_candidate(
    candidate: str,
    plan: ProfilePlan,
    leet_mode: str = "none",
    max_subs: int = 2,
) -> str | None:
    """Best-effort reverse-attribution: which profile field(s) likely produced *candidate*.

    This is a heuristic, substring-based lookup -- it does not track exact
    provenance through the mutation pipeline (that would require threading
    metadata through every mutator, coupling ``core/`` to profile concepts).
    It looks for known seed/number fragments inside the final candidate and
    reports the fields they came from. Longer matches are preferred over
    shorter ones to reduce false positives from short, coincidental
    substrings (e.g. a two-letter pet name matching inside an unrelated
    word).

    A literal substring match alone misses candidates that went through
    ``LeetMutator`` (e.g. seed "Flamengo" -> candidate fragment "Fl@mengo"):
    the seed text is no longer a substring of the candidate at all. When
    *leet_mode* is not ``"none"``, this also re-derives the same leet
    variants of each known seed that ``LeetMutator(mode=leet_mode,
    max_subs=max_subs)`` would have produced during generation, and checks
    those too. Because the pipeline composes stages in a fixed order (case
    -> leet -> affix), a seed's leet-transformed form always survives as one
    contiguous substring of the final candidate -- so this isn't a fuzzy
    guess, it's an exact replay of that stage.

    It intentionally does *not* try to cover every mutator (e.g. a
    reversed seed, or a seed that went through ``combine`` and *then*
    leet): those remain real gaps. Returns ``None`` in that case rather
    than a partial, silently-incomplete attribution -- callers should
    surface that ``None`` explicitly (e.g. "untraceable"), never treat a
    missing match as "nothing to report".
    """
    lowered = candidate.lower()
    matched_labels: list[str] = []

    for seed, label in sorted(plan.seed_field.items(), key=lambda kv: -len(kv[0])):
        if not seed:
            continue
        if seed in lowered:
            matched_labels.append(label)
            break
        if leet_mode != "none" and any(
            variant in lowered
            for variant in LeetMutator(mode=leet_mode, max_subs=max_subs).mutate(seed)
        ):
            matched_labels.append(label)
            break

    for token, label in sorted(plan.number_field.items(), key=lambda kv: -len(kv[0])):
        if token and token in candidate:
            matched_labels.append(label)
            break

    if not matched_labels:
        return None
    return " + ".join(matched_labels)
