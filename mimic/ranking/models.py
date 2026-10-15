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
    selector: str | None = None
    family_version: str | None = None

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise ValueError("ranking.enabled must be a boolean")
        if self.enabled:
            if type(self.budget) is not int or self.budget < 1:
                raise ValueError("enabled ranking requires a finite positive integer budget")
        elif self.budget is not None:
            raise ValueError("disabled ranking requires budget=None")
        if self.selector is not None:
            from mimic.ranking.families import FAMILY_VERSION
            if self.selector != "diverse-v1" or not self.enabled:
                raise ValueError("diverse-v1 requires a finite ranking budget")
            if self.family_version not in (None, FAMILY_VERSION):
                raise ValueError("unsupported candidate family version")
            object.__setattr__(self, "family_version", FAMILY_VERSION)
        elif self.family_version is not None:
            raise ValueError("family_version requires a selector")

    @property
    def preset(self) -> str:
        return next((name for name, size in BUDGET_PRESETS.items() if size == self.budget), "custom")

    def to_dict(self) -> dict:
        data = asdict(self)
        if self.selector is None:
            del data["selector"]
            del data["family_version"]
        return data

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
class Selection:
    family: str
    reason: str
    family_version: str
    selector: str = "diverse-v1"

    def __post_init__(self) -> None:
        from mimic.ranking.families import FAMILIES, FAMILY_VERSION
        if (any(type(value) is not str for value in
                (self.family, self.reason, self.family_version, self.selector))
                or self.family not in FAMILIES
                or self.reason not in ("family-representative", "score-fill")
                or self.family_version != FAMILY_VERSION or self.selector != "diverse-v1"):
            raise ValueError("invalid selection metadata")

    @classmethod
    def from_dict(cls, data: dict) -> Selection:
        if (not isinstance(data, dict) or set(data) !=
                {"family", "reason", "family_version", "selector"}):
            raise ValueError("invalid selection metadata")
        return cls(**data)


@dataclass(frozen=True)
class GenerationResult:
    candidate: Candidate
    score: CandidateScore | None = None
    rank: int | None = None
    encounter_index: int | None = None
    selection: Selection | None = None

    def to_dict(self) -> dict:
        data = {"candidate": asdict(self.candidate), "score": self.score.to_dict() if self.score else None,
                "rank": self.rank, "encounter_index": self.encounter_index}
        if self.selection is not None:
            data["selection"] = asdict(self.selection)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> GenerationResult:
        raw = data["candidate"]
        candidate = Candidate(raw["value"], tuple(Origin(**o) for o in raw["origins"]),
                              tuple(Transformation(t["kind"], tuple(tuple(p) for p in t["params"]))
                                    for t in raw["transformations"]))
        return cls(candidate, CandidateScore.from_dict(data["score"]) if data["score"] else None,
                   data["rank"], data["encounter_index"],
                   Selection.from_dict(data["selection"]) if data.get("selection") is not None else None)
