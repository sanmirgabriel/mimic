"""Immutable, profile-independent values describing one causal derivation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Origin:
    source: str
    field: str
    value: str

    def __post_init__(self) -> None:
        if any(not isinstance(v, str) for v in (self.source, self.field, self.value)):
            raise TypeError("Origin fields must be strings")


@dataclass(frozen=True)
class Transformation:
    kind: str
    params: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str):
            raise TypeError("Transformation kind must be a string")
        # Canonical key order; immutable even when constructed from a list.
        params = tuple((key, value) for key, value in self.params)
        if any(not isinstance(k, str) or not isinstance(v, str) for k, v in params):
            raise TypeError("Transformation parameters must be string pairs")
        if len({key for key, _ in params}) != len(params):
            raise ValueError("Transformation parameter keys must be unique")
        object.__setattr__(self, "params", tuple(sorted(params)))


@dataclass(frozen=True)
class Candidate:
    value: str
    origins: tuple[Origin, ...] = ()
    transformations: tuple[Transformation, ...] = ()

    def __post_init__(self) -> None:
        origins, transformations = tuple(self.origins), tuple(self.transformations)
        if not isinstance(self.value, str):
            raise TypeError("Candidate value must be a string")
        if any(not isinstance(origin, Origin) for origin in origins):
            raise TypeError("Candidate origins must contain Origin objects")
        if any(not isinstance(step, Transformation) for step in transformations):
            raise TypeError("Candidate transformations must contain Transformation objects")
        object.__setattr__(self, "origins", origins)
        object.__setattr__(self, "transformations", transformations)

    def derive(self, value: str, transformation: Transformation) -> Candidate:
        return Candidate(value, self.origins, self.transformations + (transformation,))

    def join(
        self, other: Candidate, value: str, transformation: Transformation
    ) -> Candidate:
        """Combine actual operands, retaining ordered origins and both histories.

        Histories are left operand, right operand, then the joining operation.
        They are not alternative derivations of the resulting value.
        """
        origins = tuple(dict.fromkeys(self.origins + other.origins))
        return Candidate(
            value, origins,
            self.transformations + other.transformations + (transformation,),
        )


def as_candidate(value: str | Candidate, field: str = "seed") -> Candidate:
    """Adapt a bare API value without inventing profile/CLI attribution."""
    if isinstance(value, Candidate):
        return value
    return Candidate(value, (Origin("api", field, value),))
