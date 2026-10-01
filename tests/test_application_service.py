"""Block 4 application-service contracts: request, service, preview, boundaries."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mimic.application import generation as generation_module
from mimic.application import (
    ApplicationError,
    GenerationLimits,
    GenerationRequest,
    GenerationService,
    InvalidGenerationRequest,
    MutationOptions,
    PolicyOptions,
    SourceOptions,
)
from mimic.cli import main
import mimic.cli as cli_module
from mimic.core.candidate import Candidate, Origin, Transformation
from mimic.core.seed import Seed
from mimic.domain.context import ExtractedFact, load_context
from mimic.domain.models import Organization, Target
from mimic.domain.planning import BehaviorPattern
from mimic.profile.schema import TargetProfile


def values(prepared) -> list[str]:
    return [c.value for c in prepared.iter_candidates()]


# --- target / organization / precedence -----------------------------------


def test_target_only_in_memory_no_filesystem():
    request = GenerationRequest(
        target=Target("Pedro", TargetProfile(nome="Pedro")),
        mutations=MutationOptions(leet_mode="none"),
    )
    result = list(GenerationService().prepare(request).iter_candidates())
    by_value = {c.value: c for c in result}
    assert by_value["Pedro"].origins == (Origin("profile", "nome", "Pedro"),)


def test_organization_inheritance_through_target():
    org = Organization("ACME", aliases=["AcmeTech"], keywords=["Widget"])
    request = GenerationRequest(
        target=Target("Pedro", TargetProfile(nome="Pedro"), organization=org),
        mutations=MutationOptions(leet_mode="none"),
    )
    by_value = {c.value: c for c in GenerationService().prepare(request).iter_candidates()}
    assert by_value["ACME"].origins == (Origin("organization", "name", "ACME"),)
    assert by_value["AcmeTech"].origins[0].field == "alias"
    assert by_value["Widget"].origins[0].field == "keyword"


def test_target_name_versus_profile_nome_precedence():
    """Documented contract: profile.nome wins; Target.name only fills a gap."""
    prof = GenerationRequest(target=Target("Pedro", TargetProfile(nome="João")),
                             mutations=MutationOptions(leet_mode="none"))
    by_value = {c.value: c for c in GenerationService().prepare(prof).iter_candidates()}
    assert by_value["João"].origins == (Origin("profile", "nome", "João"),)
    assert "Pedro" not in by_value

    fallback = GenerationRequest(target=Target("Pedro", TargetProfile()),
                                 mutations=MutationOptions(leet_mode="none"))
    names = {c.value: c for c in GenerationService().prepare(fallback).iter_candidates()}
    assert names["Pedro"].origins == (Origin("target", "name", "Pedro"),)


def test_context_facts_direct_without_file():
    from mimic.domain.context import ExtractedFact
    given = (
        ExtractedFact("nome", Candidate("Ana", (Origin("web", ":nome", "Ana"),))),
        ExtractedFact("data_nascimento",
                      Candidate("17/08/2002", (Origin("web", ":data", "17/08/2002"),))),
    )
    request = GenerationRequest(context_facts=given,
                                mutations=MutationOptions(leet_mode="none"))
    prepared = GenerationService().prepare(request)
    result = values(prepared)
    assert "Ana" in result
    assert "Ana17082002" in result
    assert BehaviorPattern.TARGET_DATE in prepared.patterns


def test_context_path_and_facts_are_interchangeable(tmp_path):
    path = tmp_path / "ctx.txt"
    path.write_text("nome: Ana\ndata_nascimento: 17/08/2002\n", encoding="utf-8")
    from_path = GenerationRequest(context_path=str(path),
                                  mutations=MutationOptions(leet_mode="none"))
    from_facts = GenerationRequest(context_facts=tuple(load_context(str(path))),
                                   mutations=MutationOptions(leet_mode="none"))
    svc = GenerationService()
    assert values(svc.prepare(from_path)) == values(svc.prepare(from_facts))


def test_source_precedence_first_causal_derivation_wins(tmp_path):
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("Flamengo\n", encoding="utf-8")
    ready = tmp_path / "ready.txt"
    ready.write_text("Flamengo\n", encoding="utf-8")
    org = Organization("ACME", keywords=["Flamengo"])
    target = Target("Flamengo", TargetProfile(nome="Flamengo"), organization=org)

    def first_origin(**kwargs) -> str:
        request = GenerationRequest(mutations=MutationOptions(leet_mode="none"), **kwargs)
        prepared = GenerationService().prepare(request)
        hit = next(c for c in prepared.iter_candidates() if c.value == "Flamengo")
        return hit.origins[0].source

    full = dict(target=target,
                sources=SourceOptions(dataset_paths=(str(corpus),),
                                      ready_candidate_paths=(str(ready),), include_ptbr=True))
    assert first_origin(**full) == "profile"
    assert first_origin(organization=org,
                        sources=SourceOptions(dataset_paths=(str(corpus),),
                                              ready_candidate_paths=(str(ready),))) == "organization"
    assert first_origin(sources=SourceOptions(dataset_paths=(str(corpus),),
                                              ready_candidate_paths=(str(ready),))) == "ready_candidate"
    assert first_origin(sources=SourceOptions(dataset_paths=(str(corpus),))) == "dataset"


# --- mutation / policy / limits --------------------------------------------


def test_ptbr_toggle_via_application_only():
    request = GenerationRequest(sources=SourceOptions(include_ptbr=True),
                                mutations=MutationOptions(leet_mode="none"))
    result = values(GenerationService().prepare(request))
    assert "Flamengo" in result and "Palmeiras" in result


def test_dataset_and_ready_capabilities(tmp_path):
    dataset = tmp_path / "dataset.txt"
    dataset.write_text("Corpus\n", encoding="utf-8")
    ready = tmp_path / "ready.txt"
    ready.write_text("Pass123!\n", encoding="utf-8")
    request = GenerationRequest(
        base_candidates=(Candidate("Pedro", (Origin("manual", "nome", "Pedro"),)),),
        sources=SourceOptions(dataset_paths=(str(dataset),),
                              ready_candidate_paths=(str(ready),)),
        mutations=MutationOptions(leet_mode="full", combine=True),
    )
    result = values(GenerationService().prepare(request))
    assert "C0rpu$" in result           # dataset seed is mutated
    assert "Pass123!" in result         # ready candidate survives verbatim
    assert "P@$$123!" not in result     # ready candidate is never mutated
    assert not any("corpus" in v.lower() and "pedro" in v.lower() for v in result)


def test_leet_policy_and_limits_are_honored():
    request = GenerationRequest(
        base_candidates=(Candidate("ab", (Origin("manual", "nome", "ab"),)),),
        number_candidates=(Candidate("2024", (Origin("cli", "year", "2024"),)),),
        mutations=MutationOptions(leet_mode="none"),
        policy=PolicyOptions(min_len=5, require_digit=True),
        limits=GenerationLimits(max_candidates_per_word=3),
    )
    result = values(GenerationService().prepare(request))
    assert result
    for value in result:
        assert len(value) >= 5 and any(ch.isdigit() for ch in value)


def test_combine_only_cross_pairs_safe_partners():
    request = GenerationRequest(
        base_candidates=(
            Candidate("Pedro", (Origin("manual", "nome", "Pedro"),)),
            Candidate("Silva", (Origin("manual", "nome", "Silva"),)),
        ),
        mutations=MutationOptions(leet_mode="none", combine=True),
    )
    result = values(GenerationService().prepare(request))
    assert "pedrosilva" in result


# --- preview / warnings ----------------------------------------------------


def test_plan_summary_is_streaming_safe(tmp_path):
    dataset = tmp_path / "dataset.txt"
    dataset.write_text("A\nB\nC\nD\nE\n", encoding="utf-8")
    org = Organization("ACME", aliases=["AcmeTech"], keywords=["Widget"])
    request = GenerationRequest(
        target=Target("Pedro", TargetProfile(nome="Pedro", time_futebol="Palmeiras"),
                      organization=org),
        sources=SourceOptions(dataset_paths=(str(dataset),), include_ptbr=True),
        mutations=MutationOptions(leet_mode="partial", combine=True),
    )
    summary = GenerationService().prepare(request).summary()
    assert summary.target_seed_count == 2          # nome + time_futebol
    assert summary.organization_seed_count == 3    # name + alias + keyword
    assert summary.dataset_source_count == 1
    assert summary.dataset_line_count is None      # never read the file to count
    assert summary.ptbr_enabled is True
    assert summary.combine_enabled is True
    assert summary.mutators == ("case", "leet", "affix", "reverse", "combine")
    json.dumps(summary.to_dict(), ensure_ascii=False)  # JSON-safe


def test_summary_counts_engine_inputs_for_dates_without_reading_dataset(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("Alpha\n", encoding="utf-8")
    context = _write_context(tmp_path)

    real_open = Path.open

    def guarded_open(path, *args, **kwargs):
        if path == corpus:
            raise AssertionError("dataset must remain unopened during prepare/summary")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    request = GenerationRequest(
        target=Target("Pedro", TargetProfile(nome="Pedro", data_nascimento="17/08/2002")),
        organization=Organization("ACME", relevant_dates=["17/08/2002"]),
        context_facts=tuple(load_context(str(context))),
        sources=SourceOptions(dataset_paths=(str(corpus),)),
    )
    prepared = GenerationService().prepare(request)
    summary = prepared.summary()
    assert summary.target_seed_count == 7  # one name + six distinct date tokens
    assert summary.organization_seed_count == 7  # one name + six date tokens
    assert summary.context_fact_count == 2  # facts, not expanded tokens
    assert summary.dataset_source_count == 1
    assert summary.dataset_line_count is None
    assert prepared.warnings == ("external dataset configured",)
    assert GenerationService().prepare(GenerationRequest()).summary().dataset_line_count == 0


def test_prepared_organization_matches_summary_after_external_mutation():
    organization = Organization("ACME", keywords=["Widget"])
    prepared = GenerationService().prepare(GenerationRequest(
        organization=organization, mutations=MutationOptions(leet_mode="none")))
    assert prepared.summary().organization_seed_count == 2
    organization.keywords.append("AddedLater")
    values = list(prepared.iter_values())
    assert "Widget" in values and "AddedLater" not in values


def _write_context(tmp_path):
    path = tmp_path / "context.txt"
    path.write_text("nome: Ana\ndata_nascimento: 17/08/2002\n", encoding="utf-8")
    return path


def test_warnings_are_deterministic(tmp_path):
    dataset = tmp_path / "dataset.txt"
    dataset.write_text("A\n", encoding="utf-8")
    request = GenerationRequest(
        sources=SourceOptions(dataset_paths=(str(dataset),), include_ptbr=True),
        mutations=MutationOptions(leet_mode="none", combine=True),
    )
    prepared = GenerationService().prepare(request)
    assert prepared.warnings == (
        "combine enabled", "no target-specific seed",
        "external dataset configured", "ptbr builtins enabled",
    )


# --- error model -----------------------------------------------------------


@pytest.mark.parametrize("request_kwargs", [
    dict(mutations=MutationOptions(leet_mode="l33t")),
    dict(limits=GenerationLimits(max_candidates_per_word=0)),
    dict(limits=GenerationLimits(max_dataset_lines=0)),
    dict(policy=PolicyOptions(min_len=8, max_len=4)),
])
def test_invalid_request_raises_application_error(request_kwargs):
    request = GenerationRequest(**request_kwargs)
    with pytest.raises(InvalidGenerationRequest):
        GenerationService().prepare(request)


def test_application_error_is_not_systemexit():
    assert issubclass(ApplicationError, Exception)
    assert not issubclass(ApplicationError, SystemExit)


def test_prepared_generation_is_explicitly_one_shot():
    request = GenerationRequest(base_candidates=(Candidate(
        "Pedro", (Origin("manual", "nome", "Pedro"),)),),
        mutations=MutationOptions(leet_mode="none"))
    prepared = GenerationService().prepare(request)
    assert list(prepared.iter_candidates())
    with pytest.raises(ApplicationError, match="already been requested"):
        list(prepared.iter_candidates())
    with pytest.raises(ApplicationError, match="already been requested"):
        list(prepared.iter_values())
    second = GenerationService().prepare(request)
    assert list(second.iter_values())
    with pytest.raises(ApplicationError, match="already been requested"):
        list(second.iter_candidates())


@pytest.mark.parametrize("invalid", [
    object(), GenerationRequest(limits=GenerationLimits(max_dataset_lines="x")),
    GenerationRequest(sources="bad"),
    GenerationRequest(context_path=123),
    GenerationRequest(mutations=MutationOptions(combine="yes")),
    GenerationRequest(policy=PolicyOptions(require_digit="yes")),
])
def test_invalid_request_types_have_application_errors(invalid):
    with pytest.raises(InvalidGenerationRequest):
        GenerationService().prepare(invalid)


def test_streaming_errors_remain_typed_at_iteration(tmp_path):
    svc = GenerationService()
    missing = GenerationRequest(sources=SourceOptions(dataset_paths=(str(tmp_path / "missing"),)))
    with pytest.raises(FileNotFoundError):
        list(svc.prepare(missing).iter_candidates())
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("Alpha\nBeta\n", encoding="utf-8")
    over = GenerationRequest(sources=SourceOptions(dataset_paths=(str(corpus),)),
                             limits=GenerationLimits(max_dataset_lines=1))
    with pytest.raises(ValueError, match="exceeds"):
        list(svc.prepare(over).iter_candidates())
    corpus.write_bytes(b"\xff\n")
    with pytest.raises(UnicodeDecodeError):
        list(svc.prepare(GenerationRequest(sources=SourceOptions(
            dataset_paths=(str(corpus),)))).iter_candidates())


# --- JSON-safe request -----------------------------------------------------


def test_request_to_dict_is_json_safe_and_deterministic(tmp_path):
    request = GenerationRequest(
        target=Target("Pedro", TargetProfile(nome="João", apelidos=["PH"],
                                             data_nascimento="17/08/2002"),
                      organization=Organization("ACME", keywords=["Widget"])),
        base_candidates=(Candidate("Ana", (Origin("cli", "names", "Ana"),)),),
        number_candidates=(Candidate("2024", (Origin("cli", "year", "2024"),)),),
        context_path="ctx.txt",
        sources=SourceOptions(dataset_paths=("d.txt",), include_ptbr=True),
        mutations=MutationOptions(leet_mode="partial", combine=True),
        policy=PolicyOptions(min_len=6, require_digit=True),
    )
    first = json.dumps(request.to_dict(), ensure_ascii=False, sort_keys=False)
    second = json.dumps(request.to_dict(), ensure_ascii=False, sort_keys=False)
    assert first == second                                  # deterministic
    assert "João" in first                                  # UTF-8 preserved
    payload = json.loads(first)
    assert "argparse" not in first and "Namespace" not in first
    # No runtime objects survived: only JSON scalars/containers.
    assert isinstance(payload["base_candidates"], list)
    assert payload["sources"]["dataset_paths"] == ["d.txt"]


def test_request_from_dict_round_trips_and_validates():
    request = GenerationRequest(
        target=Target("Pedro", TargetProfile(nome="Pedro", time_futebol="Palmeiras"),
                      organization=Organization("ACME", keywords=["Widget"])),
        base_candidates=(Candidate("Ana", (Origin("cli", "names", "Ana"),)),),
        mutations=MutationOptions(leet_mode="none", combine=True),
        policy=PolicyOptions(min_len=4),
    )
    restored = GenerationRequest.from_dict(json.loads(json.dumps(request.to_dict())))
    assert restored.to_dict() == request.to_dict()
    svc = GenerationService()
    assert values(svc.prepare(restored)) == values(svc.prepare(request))
    with pytest.raises(InvalidGenerationRequest):
        GenerationRequest.from_dict({"mutations": {"leet_mode": "nope"}})
    with pytest.raises(InvalidGenerationRequest, match="dataset_paths"):
        GenerationRequest.from_dict({"sources": {"dataset_paths": "corpus.txt"}})
    with pytest.raises(InvalidGenerationRequest, match="combine"):
        GenerationRequest.from_dict({"mutations": {"combine": "false"}})
    with pytest.raises(InvalidGenerationRequest, match="min_len"):
        GenerationRequest.from_dict({"policy": {"min_len": "5"}})
    with pytest.raises(InvalidGenerationRequest, match="parameters"):
        GenerationRequest.from_dict({"base_candidates": [{
            "value": "x", "transformations": [{"kind": "manual", "params": [["x", 1]]}]
        }]})


def test_rich_json_roundtrip_preserves_causal_generation(tmp_path):
    dataset = tmp_path / "corpus.txt"
    ready = tmp_path / "ready.txt"
    dataset.write_text("São Paulo\n", encoding="utf-8")
    ready.write_text("Pass123!\n", encoding="utf-8")
    source = Candidate("João", (Origin("manual", "nome", "João"),),
                       (Transformation("reviewed", (("by", "operator"),)),))
    date = ExtractedFact("data_nascimento", Candidate(
        "17/08/2002", (Origin("context_file", "context.txt:data_nascimento", "17/08/2002"),)))
    request = GenerationRequest(
        target=Target("Pedro", TargetProfile(nome="Pedro", pet="Toby", apelidos=["PH"]),
                      organization=Organization("ACME", locations=["João Pessoa"])),
        base_candidates=(source,), context_facts=(date,),
        sources=SourceOptions(dataset_paths=(str(dataset),),
                              ready_candidate_paths=(str(ready),), include_ptbr=True),
        mutations=MutationOptions(leet_mode="partial", combine=True, separators="@"),
        policy=PolicyOptions(min_len=5, require_digit=False),
        limits=GenerationLimits(max_candidates_per_word=50, max_dataset_lines=10),
    )
    data1 = request.to_dict()
    json_payload = json.dumps(data1, ensure_ascii=False)
    restored = GenerationRequest.from_dict(json.loads(json_payload))
    assert restored.to_dict() == data1
    assert "João" in json_payload and "São" not in json_payload  # dataset is a path, not read
    assert restored.base_candidates[0] == source
    assert restored.context_facts[0] == date
    assert restored.target.profile == request.target.profile
    assert restored.target.organization == request.target.organization
    assert restored.sources.dataset_paths == (str(dataset),)
    original = list(GenerationService().prepare(request).iter_candidates())
    after = list(GenerationService().prepare(restored).iter_candidates())
    assert after == original  # values, origins, transformations, and order


# --- determinism -----------------------------------------------------------


def test_service_output_is_hash_seed_independent(tmp_path):
    script = (
        "from mimic.application import GenerationService, GenerationRequest, "
        "MutationOptions, SourceOptions; "
        "from mimic.core.candidate import Candidate, Origin; "
        "a=Candidate('Pedro',(Origin('manual','nome','Pedro'),)); "
        "r=GenerationRequest(base_candidates=(a,), "
        "sources=SourceOptions(include_ptbr=True), "
        "mutations=MutationOptions(leet_mode='none')); "
        "print(repr(list(GenerationService().prepare(r).iter_values())))"
    )
    outputs = []
    for seed in ("1", "777"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONDONTWRITEBYTECODE": "1"}
        outputs.append(subprocess.check_output([sys.executable, "-B", "-c", script],
                                               env=env, text=True))
    assert outputs[0] == outputs[1]


# --- future job compatibility ----------------------------------------------


def test_generation_is_lazy_and_cancellable_midstream(tmp_path):
    dataset = tmp_path / "dataset.txt"
    dataset.write_text("\n".join(f"word{i}" for i in range(1000)) + "\n", encoding="utf-8")
    request = GenerationRequest(sources=SourceOptions(dataset_paths=(str(dataset),)),
                               mutations=MutationOptions(leet_mode="none"))
    prepared = GenerationService().prepare(request)
    collected = []
    for candidate in prepared.iter_candidates():        # future: if job.cancel: break
        collected.append(candidate.value)
        if len(collected) >= 5:
            break
    assert len(collected) == 5


def test_prepare_does_not_consume_dataset(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("Alpha\nBeta\nGamma\nDelta\n", encoding="utf-8")
    consumed: list[str] = []
    real = generation_module.stream_dataset

    def instrumented(path, **kwargs):
        for seed in real(path, **kwargs):
            consumed.append(seed.candidate.value)
            yield seed

    monkeypatch.setattr(generation_module, "stream_dataset", instrumented)
    request = GenerationRequest(sources=SourceOptions(dataset_paths=(str(corpus),)),
                               mutations=MutationOptions(leet_mode="none"))
    prepared = GenerationService().prepare(request)
    assert consumed == []                        # prepare() did not open the file
    stream = prepared.iter_candidates()
    next(stream)
    assert consumed == ["Alpha"]                 # only the first line was pulled
    assert len(consumed) < 4                      # the whole file was not materialized


# --- CLI <-> service equivalence -------------------------------------------


def test_cli_and_direct_request_agree(tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({
        "nome": "Pedro", "apelidos": ["PH"], "data_nascimento": "17/08/2002",
        "time_futebol": "Palmeiras", "pet": "Toby",
    }), encoding="utf-8")
    dataset = tmp_path / "dataset.txt"
    dataset.write_text("Corpus\n", encoding="utf-8")
    ready = tmp_path / "ready.txt"
    ready.write_text("Pass123!\n", encoding="utf-8")
    out = tmp_path / "out.txt"

    assert main([
        "generate", "--profile", str(profile), "--dataset", str(dataset),
        "--candidates", str(ready), "--ptbr", "--leet", "partial",
        "--min-len", "6", "-o", str(out), "--quiet", "--no-banner",
    ]) == 0
    cli_values = out.read_text(encoding="utf-8").splitlines()

    request = GenerationRequest(
        target=Target("Pedro", TargetProfile(
            nome="Pedro", apelidos=["PH"], data_nascimento="17/08/2002",
            time_futebol="Palmeiras", pet="Toby")),
        sources=SourceOptions(dataset_paths=(str(dataset),),
                              ready_candidate_paths=(str(ready),), include_ptbr=True),
        mutations=MutationOptions(leet_mode="partial"),
        policy=PolicyOptions(min_len=6),
    )
    prepared = GenerationService().prepare(request)
    direct = list(prepared.iter_candidates())

    assert [c.value for c in direct] == cli_values          # same values and order
    by_value = {c.value: c for c in direct}
    assert by_value["P@lmeiras"].origins == (Origin("profile", "time_futebol", "Palmeiras"),)
    assert "leet" in {t.kind for t in by_value["P@lmeiras"].transformations}
    assert by_value["Pass123!"].origins[0].source == "ready_candidate"
    assert by_value["Pass123!"].transformations == ()       # ready candidate is unmutated


def test_cli_debug_and_normal_use_same_structured_service_stream(tmp_path, monkeypatch):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({
        "nome": "Pedro", "data_nascimento": "17/08/2002",
        "time_futebol": "Palmeiras", "pet": "Toby",
    }), encoding="utf-8")
    dataset = tmp_path / "dataset.txt"
    dataset.write_text("Corpus\n", encoding="utf-8")
    ready = tmp_path / "ready.txt"
    ready.write_text("Pass123!\n", encoding="utf-8")
    observed = []

    class RecordingService(GenerationService):
        def prepare(self, request):
            prepared = super().prepare(request)
            record = {"request": request, "candidates": [], "mode": None}
            observed.append(record)

            class Recorded:
                def iter_candidates(self):
                    record["mode"] = "candidates"
                    for candidate in prepared.iter_candidates():
                        record["candidates"].append(candidate)
                        yield candidate

                def iter_values(self):
                    record["mode"] = "values"
                    for candidate in prepared.iter_candidates():
                        record["candidates"].append(candidate)
                        yield candidate.value

            return Recorded()

    monkeypatch.setattr(cli_module, "GenerationService", RecordingService)
    output = tmp_path / "out.txt"
    args = ["generate", "--profile", str(profile), "--dataset", str(dataset),
            "--candidates", str(ready), "--ptbr", "--leet", "partial",
            "--min-len", "6", "--max-per-word", "50", "-o", str(output),
            "--quiet", "--no-banner"]
    assert main(args) == 0
    plain = output.read_bytes()
    assert observed[0]["mode"] == "values"
    direct = list(GenerationService().prepare(observed[0]["request"]).iter_candidates())
    assert observed[0]["candidates"] == direct

    assert main(args + ["--debug"]) == 0
    assert output.read_bytes() == plain
    assert observed[1]["mode"] == "candidates"
    assert observed[1]["candidates"] == direct


def test_legacy_cli_converges_on_generation_service(tmp_path, monkeypatch):
    names = tmp_path / "names.txt"
    numbers = tmp_path / "numbers.txt"
    output = tmp_path / "out.txt"
    names.write_text("Pedro\nSilva\n", encoding="utf-8")
    numbers.write_text("2024\n", encoding="utf-8")
    seen = []

    class SpyService(GenerationService):
        def prepare(self, request):
            seen.append(request)
            return super().prepare(request)

    monkeypatch.setattr(cli_module, "GenerationService", SpyService)
    assert main(["--names", str(names), "--numbers", str(numbers), "--combine",
                 "--leet", "none", "--quiet", "-o", str(output)]) == 0
    assert len(seen) == 1
    assert seen[0].mutations.combine
    assert [c.value for c in seen[0].base_candidates] == ["Pedro", "Silva"]
    assert seen[0].base_candidates[0].origins == (Origin("cli", "names", "Pedro"),)
    assert seen[0].number_candidates[0].origins == (Origin("cli", "numbers", "2024"),)
    assert "pedrosilva" in output.read_text(encoding="utf-8").splitlines()


def test_quick_cli_translates_fields_into_request_without_planning(tmp_path, monkeypatch):
    captured = []

    class SpyService(GenerationService):
        def prepare(self, request):
            captured.append(request)
            return super().prepare(request)

    monkeypatch.setattr(cli_module, "GenerationService", SpyService)
    output = tmp_path / "out.txt"
    assert main(["generate", "-n", "Pedro", "-d", "17/08/2002",
                 "-t", "Palmeiras", "-p", "Toby", "-c", "ACME",
                 "--leet", "none", "--quiet", "-o", str(output)]) == 0
    assert len(captured) == 1
    request = captured[0]
    assert request.base_candidates[0].origins == (Origin("manual", "nome", "Pedro"),)
    assert [(fact.field, fact.candidate.value) for fact in request.context_facts] == [
        ("data_nascimento", "17/08/2002"), ("time_futebol", "Palmeiras"),
        ("empresa", "ACME"), ("pet", "Toby")]
    assert all(fact.candidate.origins[0].source == "profile" for fact in request.context_facts)
    assert "Pedro17082002" in output.read_text(encoding="utf-8").splitlines()


# --- import boundaries -----------------------------------------------------


def _imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _package_files(package: str) -> list[Path]:
    root = Path(__file__).parents[1] / "mimic" / package
    return list(root.rglob("*.py"))


def test_core_does_not_import_domain_or_application():
    for path in _package_files("core"):
        for module in _imported_modules(path):
            assert not module.startswith("mimic.domain"), path
            assert not module.startswith("mimic.application"), path


def test_domain_does_not_import_application():
    for path in _package_files("domain"):
        for module in _imported_modules(path):
            assert not module.startswith("mimic.application"), path


def test_application_stays_transport_agnostic():
    forbidden = ("argparse", "fastapi", "flask", "http", "jinja2", "sqlite3", "sqlalchemy")
    for path in _package_files("application"):
        modules = _imported_modules(path)
        assert "mimic.cli" not in modules, path
        for name in forbidden:
            assert name not in modules, f"{path} imports {name}"
        assert "sys" not in modules, path
