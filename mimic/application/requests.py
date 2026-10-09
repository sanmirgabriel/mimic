"""Transport-independent description of one generation.

A :class:`GenerationRequest` captures everything the CLI, a future API, a
future Web UI or a future job needs to describe a generation, without
carrying any runtime object (no ``argparse.Namespace``, no open file handle,
no stream, no HTTP request). File paths are held as configuration and read
lazily during execution, never materialized here.

Domain objects (:class:`~mimic.domain.models.Target`,
:class:`~mimic.domain.models.Organization`) are accepted directly. Free,
pre-attributed seeds coming from adapter-specific inputs (a CLI ``--names``
file, a ``-n`` flag) are carried as :class:`~mimic.core.candidate.Candidate`
tuples: only the adapter knows their true source, so the adapter attributes
them and the application never invents a ``"cli"`` origin of its own.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import date

from mimic.application.errors import InvalidGenerationRequest
from mimic.core.candidate import Candidate, Origin, Transformation
from mimic.domain.context import ExtractedFact
from mimic.domain.models import Organization, Target
from mimic.profile.schema import TargetProfile
from mimic.intelligence import IntelligenceOptions
from mimic.ranking import RankingOptions
from mimic.intelligence.builtins import get_service_profile
from mimic.packs.models import PackReference, PackError

LEET_MODES = ("none", "partial", "full")


@dataclass(frozen=True)
class MutationOptions:
    """How base seeds are expanded into candidates."""

    leet_mode: str = "partial"
    combine: bool = False
    separators: str = "@!#_."

    @classmethod
    def from_dict(cls, data: dict) -> "MutationOptions":
        return cls(
            leet_mode=data.get("leet_mode", "partial"),
            combine=data.get("combine", False),
            separators=data.get("separators", "@!#_."),
        )


@dataclass(frozen=True)
class PolicyOptions:
    """Password policy constraints applied after dedup."""

    min_len: int = 0
    max_len: int = 0
    require_upper: bool = False
    require_lower: bool = False
    require_digit: bool = False
    require_special: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "PolicyOptions":
        return cls(
            min_len=data.get("min_len", 0),
            max_len=data.get("max_len", 0),
            require_upper=data.get("require_upper", False),
            require_lower=data.get("require_lower", False),
            require_digit=data.get("require_digit", False),
            require_special=data.get("require_special", False),
        )


@dataclass(frozen=True)
class GenerationLimits:
    """Bounds on expansion cost; ranking budgets independently limit retained outputs."""

    max_candidates_per_word: int = 5000
    max_dataset_lines: int = 100_000

    @classmethod
    def from_dict(cls, data: dict) -> "GenerationLimits":
        return cls(
            max_candidates_per_word=data.get("max_candidates_per_word", 5000),
            max_dataset_lines=data.get("max_dataset_lines", 100_000),
        )


@dataclass(frozen=True)
class SourceOptions:
    """Streaming corpora and built-ins, held as configuration only.

    Paths are never read at construction or planning time; they are streamed
    incrementally during execution. Order mirrors causal precedence:
    ready candidates, then external datasets, then PT-BR built-ins.
    """

    dataset_paths: tuple[str, ...] = ()
    ready_candidate_paths: tuple[str, ...] = ()
    include_ptbr: bool = False
    packs: tuple[PackReference, ...] = ()

    def __post_init__(self) -> None:
        for name, paths in (("dataset_paths", self.dataset_paths),
                            ("ready_candidate_paths", self.ready_candidate_paths)):
            if not isinstance(paths, (list, tuple)) or any(
                not isinstance(path, str) for path in paths
            ):
                raise TypeError(f"{name} must be a sequence of strings")
        object.__setattr__(self, "dataset_paths", tuple(self.dataset_paths))
        object.__setattr__(self, "ready_candidate_paths", tuple(self.ready_candidate_paths))
        if (not isinstance(self.packs, (tuple, list)) or len(self.packs) > 64 or
                any(not isinstance(pack, PackReference) for pack in self.packs)):
            raise PackError('snapshot', "packs must contain at most 64 digest-pinned PackReference objects")
        if len({pack.identity for pack in self.packs}) != len(self.packs):
            raise PackError('snapshot', "duplicate pack selections")
        object.__setattr__(self, "packs", tuple(self.packs))

    def to_dict(self):
        data = asdict(self)
        if not self.packs:
            del data['packs']  # Preserve the JSON contract of requests without packs.
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "SourceOptions":
        return cls(
            dataset_paths=data.get("dataset_paths", ()),
            ready_candidate_paths=data.get("ready_candidate_paths", ()),
            include_ptbr=data.get("include_ptbr", False),
            packs=tuple(PackReference.from_dict(p) for p in data.get('packs', ())),
        )


def _origin_from_dict(data: dict) -> Origin:
    return Origin(data["source"], data["field"], data["value"])


def _transformation_from_dict(data: dict) -> Transformation:
    params = tuple((k, v) for k, v in data.get("params", ()))
    return Transformation(data["kind"], params)


def _candidate_from_dict(data: dict) -> Candidate:
    return Candidate(
        data["value"],
        tuple(_origin_from_dict(o) for o in data.get("origins", ())),
        tuple(_transformation_from_dict(t) for t in data.get("transformations", ())),
    )


def _fact_from_dict(data: dict) -> ExtractedFact:
    return ExtractedFact(data["field"], _candidate_from_dict(data["candidate"]))


def _profile_to_dict(profile: TargetProfile) -> dict:
    return asdict(profile)


def _target_to_dict(target: Target | None) -> dict | None:
    if target is None:
        return None
    return {
        "name": target.name,
        "profile": _profile_to_dict(target.profile),
        "organization": asdict(target.organization) if target.organization else None,
        "id": target.id,
    }


def _target_from_dict(data: dict | None) -> Target | None:
    if data is None:
        return None
    profile = TargetProfile.from_dict(data.get("profile") or {})
    org = data.get("organization")
    return Target(
        name=data.get("name", ""),
        profile=profile,
        organization=Organization(**org) if org else None,
        id=data.get("id"),
    )


@dataclass
class GenerationRequest:
    """A complete, serializable description of one generation.

    Attributes:
        target: Domain target; its profile is resolved by planning.
        organization: Organization seeds; falls back to ``target.organization``.
        base_candidates: Combinable, pre-attributed free seeds (e.g. CLI names).
        isolated_candidates: Non-combinable pre-attributed free seeds.
        number_candidates: Numeric tokens for affixing (e.g. CLI numbers/years).
        context_facts: Already-parsed structured facts (Web/API path).
        context_path: A deterministic ``field: value`` context file (CLI path).
        sources: Streaming corpora / PT-BR configuration.
        mutations: Mutation pipeline configuration.
        policy: Password policy configuration.
        limits: Generation cost bounds.
        intelligence: Bounded knowledge inputs; enabled requests capture a reference year.
        ranking: Opt-in priority and retained output budget; exhaustive by default.
    """

    target: Target | None = None
    organization: Organization | None = None
    base_candidates: tuple[Candidate, ...] = ()
    isolated_candidates: tuple[Candidate, ...] = ()
    number_candidates: tuple[Candidate, ...] = ()
    context_facts: tuple[ExtractedFact, ...] = ()
    context_path: str | None = None
    sources: SourceOptions = field(default_factory=SourceOptions)
    mutations: MutationOptions = field(default_factory=MutationOptions)
    policy: PolicyOptions = field(default_factory=PolicyOptions)
    limits: GenerationLimits = field(default_factory=GenerationLimits)
    intelligence: IntelligenceOptions = field(default_factory=lambda: IntelligenceOptions(enabled=False))
    ranking: RankingOptions = field(default_factory=RankingOptions)

    def __post_init__(self) -> None:
        self.base_candidates = tuple(self.base_candidates)
        self.isolated_candidates = tuple(self.isolated_candidates)
        self.number_candidates = tuple(self.number_candidates)
        self.context_facts = tuple(self.context_facts)
        if (isinstance(self.intelligence, IntelligenceOptions)
                and self.intelligence.enabled and self.intelligence.reference_year is None):
            self.intelligence = replace(self.intelligence, reference_year=date.today().year)

    def validate(self) -> None:
        """Raise :class:`InvalidGenerationRequest` on malformed configuration."""
        if self.target is not None and not isinstance(self.target, Target):
            raise InvalidGenerationRequest("target must be a Target or None")
        if self.organization is not None and not isinstance(self.organization, Organization):
            raise InvalidGenerationRequest("organization must be an Organization or None")
        for name, value, expected in (
            ("sources", self.sources, SourceOptions),
            ("mutations", self.mutations, MutationOptions),
            ("policy", self.policy, PolicyOptions),
            ("limits", self.limits, GenerationLimits),
            ("intelligence", self.intelligence, IntelligenceOptions),
            ("ranking", self.ranking, RankingOptions),
        ):
            if not isinstance(value, expected):
                raise InvalidGenerationRequest(f"{name} must be a {expected.__name__}")
        for name in ("enabled", "common_numbers", "recent_years", "corporate_roles"):
            if type(getattr(self.intelligence, name)) is not bool:
                raise InvalidGenerationRequest(f"intelligence.{name} must be a boolean")
        year = self.intelligence.reference_year
        if year is not None and (type(year) is not int or not 4 <= year <= 9999):
            raise InvalidGenerationRequest("reference_year must be an integer between 4 and 9999")
        if self.intelligence.enabled and year is None:
            raise InvalidGenerationRequest("enabled intelligence requires reference_year")
        for service_id in self.intelligence.service_profiles:
            try:
                get_service_profile(service_id)
            except ValueError as exc:
                raise InvalidGenerationRequest(str(exc)) from exc
        for name, group in (
            ("base_candidates", self.base_candidates),
            ("isolated_candidates", self.isolated_candidates),
            ("number_candidates", self.number_candidates),
        ):
            if any(not isinstance(item, Candidate) for item in group):
                raise InvalidGenerationRequest(f"{name} must contain Candidate objects")
        if any(not isinstance(fact, ExtractedFact) for fact in self.context_facts):
            raise InvalidGenerationRequest("context_facts must contain ExtractedFact objects")
        if self.context_path is not None and not isinstance(self.context_path, str):
            raise InvalidGenerationRequest("context_path must be a string or None")
        for name, paths in (("dataset_paths", self.sources.dataset_paths),
                            ("ready_candidate_paths", self.sources.ready_candidate_paths)):
            if any(not isinstance(path, str) for path in paths):
                raise InvalidGenerationRequest(f"{name} must contain strings")
        if self.mutations.leet_mode not in LEET_MODES:
            raise InvalidGenerationRequest(
                f"leet_mode must be one of {LEET_MODES}, got {self.mutations.leet_mode!r}"
            )
        if not isinstance(self.mutations.separators, str):
            raise InvalidGenerationRequest("separators must be a string")
        if type(self.mutations.combine) is not bool or type(self.sources.include_ptbr) is not bool:
            raise InvalidGenerationRequest("combine and include_ptbr must be booleans")
        for name, value in (("max_candidates_per_word", self.limits.max_candidates_per_word),
                            ("max_dataset_lines", self.limits.max_dataset_lines),
                            ("min_len", self.policy.min_len), ("max_len", self.policy.max_len)):
            if type(value) is not int:
                raise InvalidGenerationRequest(f"{name} must be an integer")
        for name in ("require_upper", "require_lower", "require_digit", "require_special"):
            if type(getattr(self.policy, name)) is not bool:
                raise InvalidGenerationRequest(f"{name} must be a boolean")
        if self.limits.max_candidates_per_word < 1:
            raise InvalidGenerationRequest("max_candidates_per_word must be >= 1")
        if self.limits.max_dataset_lines < 1:
            raise InvalidGenerationRequest("max_dataset_lines must be >= 1")
        if self.policy.min_len < 0 or self.policy.max_len < 0:
            raise InvalidGenerationRequest("policy lengths must be >= 0")
        if self.policy.max_len and self.policy.min_len > self.policy.max_len:
            raise InvalidGenerationRequest("min_len must be <= max_len when max_len is set")

    def to_dict(self) -> dict:
        """Return a deterministic, JSON-safe mapping.

        Contains only strings, numbers, booleans, ``None`` and nested
        lists/dicts thereof: no ``argparse.Namespace``, no generators, no open
        file handles, no un-serialized ``Path``. Key order is stable.
        """
        return {
            "target": _target_to_dict(self.target),
            "organization": asdict(self.organization) if self.organization else None,
            "base_candidates": [asdict(c) for c in self.base_candidates],
            "isolated_candidates": [asdict(c) for c in self.isolated_candidates],
            "number_candidates": [asdict(c) for c in self.number_candidates],
            "context_facts": [
                {"field": f.field, "candidate": asdict(f.candidate)}
                for f in self.context_facts
            ],
            "context_path": self.context_path,
            "sources": self.sources.to_dict(),
            "mutations": asdict(self.mutations),
            "policy": asdict(self.policy),
            "limits": asdict(self.limits),
            "intelligence": self.intelligence.to_dict(),
            "ranking": self.ranking.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GenerationRequest":
        """Rebuild a request from :meth:`to_dict` output, with validation."""
        if not isinstance(data, dict):
            raise InvalidGenerationRequest("request payload must be a mapping")
        try:
            request = cls(
                target=_target_from_dict(data.get("target")),
                organization=(
                    Organization(**data["organization"])
                    if data.get("organization") else None
                ),
                base_candidates=tuple(
                    _candidate_from_dict(c) for c in data.get("base_candidates", ())
                ),
                isolated_candidates=tuple(
                    _candidate_from_dict(c) for c in data.get("isolated_candidates", ())
                ),
                number_candidates=tuple(
                    _candidate_from_dict(c) for c in data.get("number_candidates", ())
                ),
                context_facts=tuple(
                    _fact_from_dict(f) for f in data.get("context_facts", ())
                ),
                context_path=data.get("context_path"),
                sources=SourceOptions.from_dict(data.get("sources", {})),
                mutations=MutationOptions.from_dict(data.get("mutations", {})),
                policy=PolicyOptions.from_dict(data.get("policy", {})),
                limits=GenerationLimits.from_dict(data.get("limits", {})),
                intelligence=IntelligenceOptions.from_dict(data.get("intelligence", {"enabled": False})),
                ranking=RankingOptions.from_dict(data.get("ranking", {})),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidGenerationRequest(f"malformed request payload: {exc}") from exc
        request.validate()
        return request
