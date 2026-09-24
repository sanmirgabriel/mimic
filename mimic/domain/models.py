"""Small, in-memory project, target and source model."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from mimic.profile.schema import TargetProfile


class SourceType(str, Enum):
    MANUAL = "manual"
    PROFILE_FILE = "profile_file"
    CONTEXT_FILE = "context_file"
    ORGANIZATION = "organization"
    DATASET = "dataset"
    READY_CANDIDATE = "ready_candidate"
    FUTURE_OSINT = "future_osint"
    FUTURE_LLM = "future_llm"


@dataclass(frozen=True)
class Source:
    type: SourceType
    reference: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.type, SourceType):
            raise TypeError("Source type must be a SourceType")
        if not isinstance(self.reference, str):
            raise TypeError("Source reference must be a string")


@dataclass
class Engagement:
    name: str
    description: str | None = None
    id: str | None = None


@dataclass
class Organization:
    name: str
    aliases: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    relevant_dates: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    id: str | None = None


@dataclass
class Target:
    """Individual identity; profile is the current password-engine projection."""

    name: str
    profile: TargetProfile = field(default_factory=TargetProfile)
    organization: Organization | None = None
    id: str | None = None


@dataclass(frozen=True)
class GenerationOptions:
    leet_mode: str = "partial"
    combine: bool = False
    separators: str = "@!#_."
    max_candidates_per_word: int = 5000
    min_len: int = 0
    max_len: int = 0
    require_upper: bool = False
    require_lower: bool = False
    require_digit: bool = False
    require_special: bool = False


@dataclass
class Generation:
    """A reusable request; no persistence, CLI, job or UI dependency."""

    target: Target | None = None
    organization: Organization | None = None
    sources: list[Source] = field(default_factory=list)
    options: GenerationOptions = field(default_factory=GenerationOptions)
    output_path: str | None = None
    engagement: Engagement | None = None
