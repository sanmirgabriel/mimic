"""Deterministic, line-based context extraction; free text is not inferred."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from mimic.core.candidate import Candidate, Origin
from mimic.profile.schema import TargetProfile


@dataclass(frozen=True)
class ExtractedFact:
    field: str
    candidate: Candidate


class ContextExtractor(Protocol):
    def extract(self, text: str, reference: str = "") -> list[ExtractedFact]: ...


_FIELDS = {"nome", "apelidos", "data_nascimento", "time_futebol", "pet", "empresa", "cidade"}


class KeyValueContextExtractor:
    """Accepts `field: value`, comma-separated aliases, blanks and # comments."""

    def extract(self, text: str, reference: str = "") -> list[ExtractedFact]:
        facts: list[ExtractedFact] = []
        for number, raw in enumerate(text.splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                raise ValueError(f"Context line {number} must be 'field: value'")
            field, value = (part.strip() for part in line.split(":", 1))
            if field not in _FIELDS:
                raise ValueError(f"Unknown context field on line {number}: {field!r}")
            values = value.split(",") if field == "apelidos" else [value]
            for item in values:
                item = item.strip()
                if item:
                    facts.append(ExtractedFact(field, Candidate(item, (
                        Origin("context_file", f"{reference}:{field}", item),
                    ))))
        # Reuse profile validation for mapped scalar facts; date syntax is
        # checked later by DateMutator when planning numeric tokens.
        for fact in facts:
            if fact.field not in {"apelidos", "cidade"}:
                TargetProfile.from_dict({fact.field: fact.candidate.value})
        return facts


def load_context(path: str, extractor: ContextExtractor | None = None) -> list[ExtractedFact]:
    return (extractor or KeyValueContextExtractor()).extract(
        Path(path).read_text(encoding="utf-8"), path,
    )
