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

from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from contextlib import ExitStack
from itertools import chain
import re

from mimic.application.errors import ApplicationError, InvalidGenerationRequest
from mimic.application.requests import GenerationLimits, GenerationRequest, PolicyOptions
from mimic.core.candidate import Candidate, Origin, Transformation
from mimic.core.seed import Seed
from mimic.domain.context import ExtractedFact, load_context
from mimic.domain.datasets import stream_dataset, stream_ptbr
from mimic.domain.models import Generation, GenerationOptions
from mimic.domain.planning import BehaviorPattern, PreparedGeneration as PlannedGeneration
from mimic.domain.planning import prepare_generation
from mimic.intelligence.builtins import KNOWLEDGE_VERSION
from mimic.intelligence.planning import IntelligencePlan, plan_intelligence
from mimic.intelligence.catalog import common_vocabulary
from mimic.ranking import GenerationResult, RankingOptions, SCORE_VERSION
from mimic.ranking.scoring import score_candidate
from mimic.ranking.topk import select_top_k
from mimic.packs import PackRegistry


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
    intelligence_enabled: bool
    common_numbers_enabled: bool
    corporate_roles_enabled: bool
    reference_year: int | None
    recent_years: tuple[int, ...]
    service_profiles: tuple[str, ...]
    knowledge_seed_count: int
    knowledge_number_count: int
    knowledge_version: str
    knowledge_template_seed_count: int
    service_derived_seed_count: int

    ranking: RankingOptions
    ranking_preset: str
    score_version: str | None
    packs: tuple = ()
    common_password_count: int = 0
    common_passwords_version: str | None = None

    def to_dict(self) -> dict:
        from dataclasses import asdict

        data = asdict(self)
        data["mutators"] = list(self.mutators)
        if not self.packs:
            del data['packs']
        if not self.common_password_count:
            del data['common_password_count']
            del data['common_passwords_version']
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
        pack_registry=None,
        pack_streams=None,
    ) -> None:
        self._request = request
        self._planned = planned
        self._warnings = warnings
        self._summary = summary
        self._started = False
        self.evaluated_count = 0
        self._ranking = request.ranking
        self._reference_year = request.intelligence.reference_year
        self._pack_registry = pack_registry
        self._pack_streams = pack_streams

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

    def _claim_candidates(self, checkpoint: Callable[[], None] | None = None) -> Iterator[Candidate]:
        """Reserve immediately and count the policy-accepted Core stream."""
        if self._started:
            raise ApplicationError("PreparedGeneration stream has already been requested")
        self._started = True

        def evaluated() -> Iterator[Candidate]:
            with ExitStack() as stack:
                if self._request.sources.packs:
                    self._pack_streams.update(stack.enter_context(self._pack_registry.open_verified(
                        self._request.sources.packs, max_lines=self._request.limits.max_dataset_lines,
                        checkpoint=checkpoint)))
                try:
                    for candidate in self._planned.generator.generate_candidates():
                        if checkpoint is not None:
                            checkpoint()
                        self.evaluated_count += 1
                        yield candidate
                finally:
                    if self._pack_streams is not None:
                        self._pack_streams.clear()

        return evaluated()

    def iter_results(self, checkpoint: Callable[[], None] | None = None) -> Iterator[GenerationResult]:
        """Claim once. Checkpoints may raise to interrupt scanning before final output.

        Ranking scans every policy-accepted candidate and retains only the budget.
        Exhaustive results stream immediately without invoking scoring or Top-K.
        """
        candidates = self._claim_candidates(checkpoint)
        if self._ranking.enabled:
            return select_top_k(candidates, self._ranking.budget,
                                lambda candidate: score_candidate(candidate, self._reference_year))
        return (GenerationResult(candidate) for candidate in candidates)

    def iter_candidates(self) -> Iterator[Candidate]:
        """Claim and project the same one-shot result stream to Core candidates."""
        if not self._ranking.enabled:
            return self._claim_candidates()
        return (result.candidate for result in self.iter_results())

    def iter_values(self) -> Iterator[str]:
        """Stream values in exhaustive encounter order or retained priority order."""
        return (candidate.value for candidate in self.iter_candidates())


class GenerationService:
    """Stateless use-case object turning a request into a prepared generation."""

    def __init__(self, pack_registry=None):
        self.pack_registry = pack_registry

    def freeze_packs(self, request):
        if not request.sources.packs:
            return request
        registry = self.pack_registry or PackRegistry()
        packs = tuple(registry.resolve(pack) for pack in request.sources.packs)
        return replace(request, sources=replace(request.sources, packs=packs))

    def prepare(self, request: GenerationRequest) -> PreparedGeneration:
        """Validate and resolve *request* into a lazy :class:`PreparedGeneration`.

        Does not read datasets, generate candidates, write files or print.
        """
        if not isinstance(request, GenerationRequest):
            raise InvalidGenerationRequest("request must be a GenerationRequest")
        request.validate()
        request = self.freeze_packs(request)
        facts = self._resolve_context(request)
        terms = self._organization_terms(request, facts)
        has_context = self._has_context(request, facts)
        intelligence = request.intelligence
        if intelligence.enabled and not (has_context or intelligence.service_profiles
                or request.sources.dataset_paths or request.sources.ready_candidate_paths or request.sources.include_ptbr
                or request.sources.packs or request.sources.include_common_passwords):
            raise InvalidGenerationRequest("intelligence requires a contextual seed or service profile")
        # Service-only requests use only the selected profiles' vocabulary.
        # Configured corpora without context receive numeric primitives only.
        if not has_context:
            intelligence = replace(intelligence, corporate_roles=False)
        supplemental = tuple(term for term in terms if any(
            step.kind == "organization_domain_label" for step in term.transformations))
        knowledge = plan_intelligence(intelligence, terms, supplemental)
        options = self._build_options(request)
        generation = Generation(
            target=request.target,
            organization=request.organization,
            options=options,
        )
        pack_streams = {}
        extra = self._extra_seeds(request, knowledge, pack_streams)
        try:
            planned = prepare_generation(
                generation,
                base_candidates=request.base_candidates,
                isolated_candidates=request.isolated_candidates,
                number_candidates=request.number_candidates,
                context_facts=facts,
                extra_seeds=extra,
                extra_number_candidates=knowledge.numbers,
                defer_extra_numbers=bool((request.sources.ready_candidate_paths or request.sources.include_common_passwords or
                    any(pack.metadata.kind == 'ready' for pack in request.sources.packs)) and knowledge.numbers),
            )
            summary = self._summary(request, facts, planned, knowledge)
        except (ValueError, TypeError) as exc:
            raise InvalidGenerationRequest(str(exc)) from exc
        warnings = self._warnings(request, facts)
        if request.intelligence.enabled and not (planned.target_seed_count or planned.organization_seed_count or facts):
            warnings += ("intelligence enabled without target/organization context",)
        return PreparedGeneration(request, planned, warnings, summary,
                                  self.pack_registry or (PackRegistry() if request.sources.packs else None), pack_streams)

    # -- resolution helpers -------------------------------------------------

    def _has_context(self, request: GenerationRequest, facts: list[ExtractedFact]) -> bool:
        if any(candidate.value.strip() for candidate in (*request.base_candidates, *request.isolated_candidates)) or any(
                fact.candidate.value.strip() for fact in facts):
            return True
        target = request.target
        if target and (target.name.strip() or any((target.profile.nome, target.profile.apelidos,
                target.profile.empresa, target.profile.pet, target.profile.time_futebol, target.profile.data_nascimento))):
            return True
        org = request.organization or (target.organization if target else None)
        return bool(org and any(value.strip() for value in (
            org.name, *org.aliases, *org.locations, *org.keywords, *org.relevant_dates, *org.domains)))

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

    def _organization_terms(self, request: GenerationRequest, facts: list[ExtractedFact]) -> tuple[Candidate, ...]:
        """Adapt explicit company facts; DNS hostnames contribute only their first label.

        No public suffix guessing, URL parsing, subdomain search or NLP. Raw
        organization domains remain explicit inputs in domain planning.
        """
        terms: list[Candidate] = []
        if request.target and request.target.profile.empresa:
            value = request.target.profile.empresa
            terms.append(Candidate(value, (Origin("profile", "empresa", value),)))
        terms.extend(fact.candidate for fact in facts if fact.field == "empresa")
        org = request.organization or (request.target.organization if request.target else None)
        if org:
            for field, values in (("name", (org.name,)), ("alias", org.aliases)):
                terms.extend(Candidate(value, (Origin("organization", field, value),))
                             for value in values if value.strip())
            for value in org.domains:
                hostname = value.lower().removesuffix(".")
                label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
                if re.fullmatch(label + r"(?:\." + label + r")+", hostname):
                    candidate = Candidate(value, (Origin("organization", "domain", value),))
                    terms.append(candidate.derive(hostname.split(".")[0], Transformation(
                        "organization_domain_label", (("input", value), ("rule", "first_dns_label")))))
        first: dict[str, Candidate] = {}
        for term in terms:
            first.setdefault(term.value, term)
        return tuple(first.values())

    def _extra_seeds(self, request: GenerationRequest, knowledge: IntelligencePlan, pack_streams=None) -> Iterator[Seed]:
        """Build the lazy source chain in causal-precedence order.

        Ready candidates precede knowledge, external datasets and PT-BR.
        Corpora remain generators: no file is opened here.
        """
        limit = request.limits.max_dataset_lines
        def packs(kind):
            for reference in request.sources.packs:
                if reference.metadata.kind == kind:
                    yield from PackRegistry.seeds(*pack_streams[reference.identity])
        def common_passwords():
            if request.sources.include_common_passwords:
                for value in common_vocabulary(request.sources.common_passwords_version).passwords:
                    yield Seed(Candidate(value, (Origin("knowledge", "common_password", value),)),
                               mutable=False, combinable=False)
        return chain(
            *(
                stream_dataset(path, ready=True, max_lines=limit)
                for path in request.sources.ready_candidate_paths
            ),
            packs('ready'),
            common_passwords(),
            knowledge.seeds,
            *(
                stream_dataset(path, max_lines=limit)
                for path in request.sources.dataset_paths
            ),
            packs('seed'),
            stream_ptbr() if request.sources.include_ptbr else (),
        )

    # -- preview helpers ----------------------------------------------------

    def _summary(
        self, request: GenerationRequest, facts: list[ExtractedFact],
        planned: PlannedGeneration, knowledge: IntelligencePlan,
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
            dataset_source_count=len(request.sources.dataset_paths) + sum(p.metadata.kind == 'seed' for p in request.sources.packs),
            ready_candidate_source_count=len(request.sources.ready_candidate_paths) + sum(p.metadata.kind == 'ready' for p in request.sources.packs),
            dataset_line_count=(None if request.sources.dataset_paths or request.sources.packs else 0),
            mutators=tuple(mutators),
            combine_enabled=request.mutations.combine,
            leet_mode=request.mutations.leet_mode,
            policy=request.policy,
            limits=request.limits,
            intelligence_enabled=request.intelligence.enabled,
            common_numbers_enabled=request.intelligence.enabled and request.intelligence.common_numbers,
            corporate_roles_enabled=knowledge.corporate_roles_active,
            reference_year=request.intelligence.reference_year,
            recent_years=knowledge.years,
            service_profiles=knowledge.services,
            knowledge_seed_count=len(knowledge.seeds),
            knowledge_number_count=len(knowledge.numbers),
            knowledge_version=KNOWLEDGE_VERSION,
            knowledge_template_seed_count=sum(any(step.kind == "knowledge_template" for step in seed.candidate.transformations)
                                            for seed in knowledge.seeds),
            ranking=request.ranking,
            ranking_preset=request.ranking.preset,
            score_version=SCORE_VERSION if request.ranking.enabled else None,
            service_derived_seed_count=sum(any(origin.source == "knowledge" and origin.field.startswith("service.")
                                          for origin in seed.candidate.origins) for seed in knowledge.seeds),
            packs=tuple(p.metadata for p in request.sources.packs),
            common_password_count=(len(common_vocabulary(request.sources.common_passwords_version).passwords)
                                   if request.sources.include_common_passwords else 0),
            common_passwords_version=request.sources.common_passwords_version,
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
