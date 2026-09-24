"""Structured target profile schema.

Deliberately a plain ``dataclass`` instead of pydantic: the profile shape
is small and flat (five scalar fields plus one list), so hand-rolled
construction validation covers it without adding a validation-engine
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

    def __post_init__(self) -> None:
        for name in ("nome", "data_nascimento", "time_futebol", "empresa", "pet"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"'{name}' must be a string or None")
            normalized = (value.strip() or None) if value is not None else None
            setattr(self, name, normalized)
        if not isinstance(self.apelidos, list) or any(
            not isinstance(value, str) for value in self.apelidos
        ):
            raise ValueError("'apelidos' must be a list of strings")
        self.apelidos = [value.strip() for value in self.apelidos if value.strip()]

    @classmethod
    def from_dict(cls, data: dict) -> "TargetProfile":
        """Build a profile from a raw dict (as parsed from YAML/JSON).

        Raises:
            ValueError: on unknown fields, invalid scalar types or malformed apelidos.
        """
        if not isinstance(data, dict):
            raise ValueError("Profile must be a mapping of field -> value")
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known, key=str)
        if unknown:
            raise ValueError(
                f"Unknown profile field(s): {unknown}. "
                f"Known fields: {sorted(known)}"
            )
        return cls(
            nome=data.get("nome"),
            apelidos=data.get("apelidos", []),
            data_nascimento=data.get("data_nascimento"),
            time_futebol=data.get("time_futebol"),
            empresa=data.get("empresa"),
            pet=data.get("pet"),
        )
