"""Generic generation capabilities; independent of domain/source models."""

from dataclasses import dataclass

from mimic.core.candidate import Candidate
from mimic.mutators.base import Mutator


@dataclass(frozen=True)
class Seed:
    """A source operand; optional stages override the shared mutation pipeline."""

    candidate: Candidate
    combinable: bool = False
    mutable: bool = True
    stages: tuple[Mutator, ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, Candidate):
            raise TypeError("Seed candidate must be a Candidate")
        if type(self.combinable) is not bool or type(self.mutable) is not bool:
            raise TypeError("Seed capabilities must be booleans")
        if self.combinable and not self.mutable:
            raise ValueError("Ready candidates cannot be combinable")
        if self.stages is not None:
            stages = tuple(self.stages)
            if any(not isinstance(stage, Mutator) for stage in stages):
                raise TypeError("Seed stages must contain Mutator objects")
            if not self.mutable:
                raise ValueError("Ready candidates cannot have mutation stages")
            object.__setattr__(self, "stages", stages)
