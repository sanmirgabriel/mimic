"""Generic generation capabilities; independent of domain/source models."""

from dataclasses import dataclass

from mimic.core.candidate import Candidate


@dataclass(frozen=True)
class Seed:
    candidate: Candidate
    combinable: bool = False
    mutable: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, Candidate):
            raise TypeError("Seed candidate must be a Candidate")
        if type(self.combinable) is not bool or type(self.mutable) is not bool:
            raise TypeError("Seed capabilities must be booleans")
        if self.combinable and not self.mutable:
            raise ValueError("Ready candidates cannot be combinable")
