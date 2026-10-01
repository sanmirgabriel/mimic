"""The reusable generation use case.

:class:`GenerationService` is the single entry point every adapter shares:
the CLI today, a future API, Web UI or job tomorrow. It owns source
precedence, mutator/policy assembly and Generator construction (via
``domain.planning``); adapters only translate their input into a
:class:`~mimic.application.requests.GenerationRequest` and consume the
resulting candidate stream. The service writes nothing and prints nothing.

``prepare`` is side-effect light: it validates, resolves context, assembles a
lazy plan and computes a warnings/summary preview, but it does not open
dataset files, generate candidates or start work. Execution happens only when
:meth:`PreparedGeneration.iter_candidates` is iterated.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from itertools import chain

from mimic.application.errors import ApplicationError, InvalidGenerationRequest
from mimic.application.requests import GenerationLimits, GenerationRequest, PolicyOptions
from mimic.core.candidate import Candidate
from mimic.core.seed import Seed
from mimic.domain.context import ExtractedFact, load_context
from mimic.domain.datasets import stream_dataset, stream_ptbr
from mimic.domain.models import Generation, GenerationOptions
from mimic.domain.planning import BehaviorPattern, PreparedGeneration as PlannedGeneration
from mimic.domain.planning import prepare_generation


@dataclass(frozen=True)
class GenerationPlanSummary:
    """A cheap, streaming-safe preview of a resolved generation.

    ``target_seed_count`` counts target engine inputs, including every token
    expanded from a profile date, but excludes context facts (reported
    separately). ``organization_seed_count`` counts organization engine
    inputs after date expansion. Counts are before output dedup or mutation.
    ``context_fact_count`` counts parsed facts, including each alias. Streaming corpora expose
    their *source* count (number of files), never a line count: those files
    are not read to build this summary, so their sizes are reported as
    ``None`` (unknown). With no dataset files, the line count is ``0``.
    """

    target_seed_count: int
    organization_seed_count: int
    context_fact_count: int
    ptbr_enabled: bool
    dataset_source_count: int
    ready_candidate_source_count: int
    dataset_line_count: int | None
    mutators: tuple[str, ...]
    combine_enabled: bool
    leet_mode: str
    policy: PolicyOptions
    limits: GenerationLimits

    def to_dict(self) -> dict:
        from dataclasses import asdict

        data = asdict(self)
        data["mutators"] = list(self.mutators)
        return data


class PreparedGeneration:
    """A validated, resolved generation ready to stream, plus its preview.

    Candidate production is lazy and single-pass: iterating
    :meth:`iter_candidates` (or :meth:`iter_values`) consumes the underlying
    stream, including its one-shot streaming sources. Iterate once.
    """

    def __init__(
        self,
        request: GenerationRequest,
        planned: PlannedGeneration,
        warnings: tuple[str, ...],
        summary: GenerationPlanSummary,
    ) -> None:
        self._request = request
        self._planned = planned
        self._warnings = warnings
        self._summary = summary
        self._started = False

    @property
    def request(self) -> GenerationRequest:
        return self._request

    @property
    def warnings(self) -> tuple[str, ...]:
        return self._warnings

    @property
    def patterns(self) -> tuple[BehaviorPattern, ...]:
        return self._planned.patterns

    def summary(self) -> GenerationPlanSummary:
        return self._summary

    def iter_candidates(self) -> Iterator[Candidate]:
        """Claim and stream this one-shot plan; a second claim is an error."""
        if self._started:
            raise ApplicationError("PreparedGeneration stream has already been requested")
        self._started = True
        return self._planned.generator.generate_candidates()

    def iter_values(self) -> Iterator[str]:
        """Stream candidate values, in the same order as :meth:`iter_candidates`."""
        return (candidate.value for candidate in self.iter_candidates())


class GenerationService:
    """Stateless use-case object turning a request into a prepared generation."""

    def prepare(self, request: GenerationRequest) -> PreparedGeneration:
        """Validate and resolve *request* into a lazy :class:`PreparedGeneration`.

        Does not read datasets, generate candidates, write files or print.
        """
        if not isinstance(request, GenerationRequest):
            raise InvalidGenerationRequest("request must be a GenerationRequest")
        request.validate()
        facts = self._resolve_context(request)
        options = self._build_options(request)
        generation = Generation(
            target=request.target,
            organization=request.organization,
            options=options,
        )
        extra = self._extra_seeds(request)
        try:
            planned = prepare_generation(
                generation,
                base_candidates=request.base_candidates,
                isolated_candidates=request.isolated_candidates,
                number_candidates=request.number_candidates,
                context_facts=facts,
                extra_seeds=extra,
            )
            summary = self._summary(request, facts, planned)
        except (ValueError, TypeError) as exc:
            raise InvalidGenerationRequest(str(exc)) from exc
        warnings = self._warnings(request, facts)
        return PreparedGeneration(request, planned, warnings, summary)

    # -- resolution helpers -------------------------------------------------

    def _resolve_context(self, request: GenerationRequest) -> list[ExtractedFact]:
        facts = list(request.context_facts)
        if request.context_path:
            try:
                facts.extend(load_context(request.context_path))
            except (OSError, ValueError, TypeError) as exc:
                raise InvalidGenerationRequest(f"invalid context source: {exc}") from exc
        return facts

    def _build_options(self, request: GenerationRequest) -> GenerationOptions:
        m, p, limits = request.mutations, request.policy, request.limits
        return GenerationOptions(
            leet_mode=m.leet_mode,
            combine=m.combine,
            separators=m.separators,
            max_candidates_per_word=limits.max_candidates_per_word,
            min_len=p.min_len,
            max_len=p.max_len,
            require_upper=p.require_upper,
            require_lower=p.require_lower,
            require_digit=p.require_digit,
            require_special=p.require_special,
        )

    def _extra_seeds(self, request: GenerationRequest) -> Iterator[Seed]:
        """Build the lazy source chain in causal-precedence order.

        Ready candidates precede external datasets, which precede PT-BR
        built-ins. Every element is a generator: no file is opened here.
        """
        limit = request.limits.max_dataset_lines
        return chain(
            *(
                stream_dataset(path, ready=True, max_lines=limit)
                for path in request.sources.ready_candidate_paths
            ),
            *(
                stream_dataset(path, max_lines=limit)
                for path in request.sources.dataset_paths
            ),
            stream_ptbr() if request.sources.include_ptbr else (),
        )

    # -- preview helpers ----------------------------------------------------

    def _summary(
        self, request: GenerationRequest, facts: list[ExtractedFact],
        planned: PlannedGeneration,
    ) -> GenerationPlanSummary:
        mutators = ["case"]
        if request.mutations.leet_mode != "none":
            mutators.append("leet")
        mutators.extend(("affix", "reverse"))
        if request.mutations.combine:
            mutators.append("combine")
        return GenerationPlanSummary(
            target_seed_count=planned.target_seed_count,
            organization_seed_count=planned.organization_seed_count,
            context_fact_count=len(facts),
            ptbr_enabled=request.sources.include_ptbr,
            dataset_source_count=len(request.sources.dataset_paths),
            ready_candidate_source_count=len(request.sources.ready_candidate_paths),
            dataset_line_count=(None if request.sources.dataset_paths else 0),
            mutators=tuple(mutators),
            combine_enabled=request.mutations.combine,
            leet_mode=request.mutations.leet_mode,
            policy=request.policy,
            limits=request.limits,
        )

    def _warnings(
        self, request: GenerationRequest, facts: list[ExtractedFact]
    ) -> tuple[str, ...]:
        warnings: list[str] = []
        if request.mutations.combine:
            warnings.append("combine enabled")
        target = request.target
        has_target_seed = bool(
            request.base_candidates
            or request.isolated_candidates
            or (target is not None and (
                target.profile.nome
                or target.profile.apelidos
                or target.profile.time_futebol
                or target.profile.empresa
                or target.profile.pet
                or target.name.strip()
            ))
            or any(fact.field in {"nome", "apelidos"} for fact in facts)
        )
        if not has_target_seed:
            warnings.append("no target-specific seed")
        if request.sources.dataset_paths:
            warnings.append("external dataset configured")
        if request.sources.ready_candidate_paths:
            warnings.append("ready candidates bypass mutation")
        if request.sources.include_ptbr:
            warnings.append("ptbr builtins enabled")
        return tuple(warnings)
