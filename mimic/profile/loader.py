"""Load a TargetProfile from disk and turn it into generation inputs.

This module is the only place that knows how profile fields map onto
mutators. Profile uses core's generic candidate model and DateMutator from
``mutators/``. Core never imports profile.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from mimic.core.candidate import Candidate, Origin
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
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError("Invalid YAML profile syntax") from exc
        if data is None:
            data = {}
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
    # Causal inputs. The string lists/maps above remain legacy compatibility
    # snapshots; new consumers must pass these candidates to the engine.
    base_candidates: list[Candidate] = field(default_factory=list)
    isolated_candidates: list[Candidate] = field(default_factory=list)
    number_candidates: list[Candidate] = field(default_factory=list)


def build_plan(profile: TargetProfile) -> ProfilePlan:
    """Route each profile field to the mutator(s)/seed group it belongs in."""
    plan = ProfilePlan()

    if profile.nome:
        plan.base_words.append(profile.nome)
        plan.base_candidates.append(Candidate(
            profile.nome, (Origin("profile", "nome", profile.nome),),
        ))
        plan.seed_field[profile.nome.lower()] = f"nome={profile.nome}"

    for apelido in profile.apelidos:
        plan.base_words.append(apelido)
        plan.base_candidates.append(Candidate(
            apelido, (Origin("profile", "apelidos", apelido),),
        ))
        plan.seed_field[apelido.lower()] = f"apelidos={apelido}"

    for field_name, value in (
        ("time_futebol", profile.time_futebol),
        ("empresa", profile.empresa),
        ("pet", profile.pet),
    ):
        if value:
            plan.isolated_seeds.append(value)
            plan.isolated_candidates.append(Candidate(
                value, (Origin("profile", field_name, value),),
            ))
            plan.seed_field[value.lower()] = f"{field_name}={value}"

    if profile.data_nascimento:
        date = Candidate(profile.data_nascimento, (
            Origin("profile", "data_nascimento", profile.data_nascimento),
        ))
        plan.number_candidates.extend(DateMutator().mutate_candidate(date))
        tokens = [token.value for token in plan.number_candidates]
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
    """Deprecated heuristic compatibility API; not used by CLI generation.

    New callers should inspect Candidate.origins and Candidate.transformations.
    This helper is retained for existing string-only consumers and can return
    incomplete attributions. It does not establish causality.

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
