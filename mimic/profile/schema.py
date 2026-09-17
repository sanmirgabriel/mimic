"""Structured target profile schema.

Deliberately a plain ``dataclass`` instead of pydantic: the profile shape
is small and flat (five scalar fields plus one list), so hand-rolled
validation in ``from_dict`` covers it without adding a validation-engine
dependency. It also keeps the core install dependency-free -- only
``--profile`` users pull in the (separate, optional) YAML dependency, see
``loader.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields


@dataclass
class TargetProfile:
    """A structured description of a pentest target, one field per OSINT fact.

    Every field is optional: a profile can be built up incrementally as
    OSINT reveals more about the target.
    """

    nome: str | None = None
    apelidos: list[str] = field(default_factory=list)
    data_nascimento: str | None = None  # "DD/MM" or "DD/MM/AAAA"
    time_futebol: str | None = None
    empresa: str | None = None
    pet: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "TargetProfile":
        """Build a profile from a raw dict (as parsed from YAML/JSON).

        Raises:
            ValueError: on an unknown field name or a malformed ``apelidos``.
        """
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise ValueError(
                f"Unknown profile field(s): {unknown}. "
                f"Known fields: {sorted(known)}"
            )
        apelidos = data.get("apelidos", [])
        if not isinstance(apelidos, list):
            raise ValueError("'apelidos' must be a list of strings")
        return cls(
            nome=data.get("nome"),
            apelidos=[str(a) for a in apelidos],
            data_nascimento=data.get("data_nascimento"),
            time_futebol=data.get("time_futebol"),
            empresa=data.get("empresa"),
            pet=data.get("pet"),
        )
