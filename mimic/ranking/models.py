"""Immutable metadata above Core; scores are heuristic priority, never probability."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from types import MappingProxyType

from mimic.core.candidate import Candidate, Origin, Transformation

SCORE_VERSION = "score-v1"
BUDGET_PRESETS = MappingProxyType({"exhaustive": None, "quick": 100, "focused": 1000,
                                  "balanced": 10000, "large": 100000})


@dataclass(frozen=True)
class RankingOptions:
    enabled: bool = False
    budget: int | None = None

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise ValueError("ranking.enabled must be a boolean")
        if self.enabled:
            if type(self.budget) is not int or self.budget < 1:
                raise ValueError("enabled ranking requires a finite positive integer budget")
        elif self.budget is not None:
            raise ValueError("disabled ranking requires budget=None")

    @property
    def preset(self) -> str:
        return next((name for name, size in BUDGET_PRESETS.items() if size == self.budget), "custom")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> RankingOptions:
        return cls(**data)

    @classmethod
    def from_budget(cls, value: str) -> RankingOptions:
        budget = BUDGET_PRESETS.get(value) if value in BUDGET_PRESETS else int(value)
        return cls(enabled=budget is not None, budget=budget)


@dataclass(frozen=True)
class ScoreComponent:
    code: str
    delta: int
    description: str


@dataclass(frozen=True)
class CandidateScore:
    total: int
    components: tuple[ScoreComponent, ...]
    version: str = SCORE_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "components", tuple(self.components))

    def to_dict(self) -> dict:
        data = asdict(self)
        data["components"] = [asdict(component) for component in self.components]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> CandidateScore:
        return cls(data["total"], tuple(ScoreComponent(**c) for c in data["components"]), data["version"])


@dataclass(frozen=True)
class GenerationResult:
    candidate: Candidate
    score: CandidateScore | None = None
    rank: int | None = None
    encounter_index: int | None = None

    def to_dict(self) -> dict:
        return {"candidate": asdict(self.candidate), "score": self.score.to_dict() if self.score else None,
                "rank": self.rank, "encounter_index": self.encounter_index}

    @classmethod
    def from_dict(cls, data: dict) -> GenerationResult:
        raw = data["candidate"]
        candidate = Candidate(raw["value"], tuple(Origin(**o) for o in raw["origins"]),
                              tuple(Transformation(t["kind"], tuple(tuple(p) for p in t["params"]))
                                    for t in raw["transformations"]))
        return cls(candidate, CandidateScore.from_dict(data["score"]) if data["score"] else None,
                   data["rank"], data["encounter_index"])
