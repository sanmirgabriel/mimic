"""Block 3 domain, source capability and CLI compatibility contracts."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mimic.cli import main
from mimic.core.candidate import Candidate, Origin
from mimic.core.seed import Seed
from mimic.domain.context import KeyValueContextExtractor, load_context
from mimic.domain.datasets import stream_dataset, stream_ptbr
from mimic.domain.models import (Engagement, Generation, GenerationOptions,
                                 Organization, Source, SourceType, Target)
from mimic.domain.planning import BehaviorPattern, prepare_generation
from mimic.profile.schema import TargetProfile


def test_domain_models_and_organization_inheritance():
    org = Organization("ACME", aliases=["AcmeTech"], locations=["João Pessoa"],
                       keywords=["produto interno"])
    target = Target("Pedro", TargetProfile(nome="Pedro", time_futebol="Palmeiras",
                                            pet="Toby"), organization=org)
    generation = Generation(target=target, engagement=Engagement("External Pentest"),
                            sources=[Source(SourceType.MANUAL)],
                            options=GenerationOptions(leet_mode="none"))
    results = list(prepare_generation(generation).generator.generate_candidates())
    by_value = {c.value: c for c in results}
    assert by_value["Pedro"].origins == (Origin("profile", "nome", "Pedro"),)
    assert by_value["Palmeiras"].origins == (Origin("profile", "time_futebol", "Palmeiras"),)
    assert by_value["Toby"].origins == (Origin("profile", "pet", "Toby"),)
    assert by_value["ACME"].origins == (Origin("organization", "name", "ACME"),)
    assert by_value["AcmeTech"].origins[0].field == "alias"
    assert by_value["João Pessoa"].origins[0].field == "location"
    assert generation.target.organization is org


def test_source_type_is_explicit():
    assert {value.value for value in SourceType} >= {
        "manual", "profile_file", "context_file", "organization", "dataset",
        "ready_candidate", "future_osint", "future_llm"}
    with pytest.raises(TypeError):
        Source("arbitrary")


def test_target_name_fallback_and_combine_safety():
    org = Organization("ACME", keywords=["PrivateToken"])
    generation = Generation(target=Target("Pedro", organization=org),
                            options=GenerationOptions(combine=True, leet_mode="none"))
    plan = prepare_generation(generation, base_candidates=[Candidate("Silva", (
        Origin("manual", "name", "Silva"),))])
    values = list(plan.generator.generate_candidates())
    by_value = {c.value: c for c in values}
    assert by_value["Pedro"].origins == (Origin("target", "name", "Pedro"),)
    assert "pedrosilva" in by_value
    assert "pedroacme" not in by_value
    assert "pedroprivatetoken" not in by_value


def test_generic_source_capabilities_and_ready_bypass():
    base = Candidate("Pedro", (Origin("manual", "nome", "Pedro"),))
    corpus = Candidate("Corpus", (Origin("dataset", "corpus:1", "Corpus"),))
    ready = Candidate("Pass123!", (Origin("ready_candidate", "file:1", "Pass123!"),))
    plan = prepare_generation(
        Generation(options=GenerationOptions(combine=True, leet_mode="full")),
        base_candidates=[base], extra_seeds=[Seed(corpus), Seed(ready, mutable=False)],
    )
    result = list(plan.generator.generate_candidates())
    values = {c.value for c in result}
    assert "C0rpu$" in values
    assert "Pass123!" in values and "P@$$123!" not in values
    assert not any("corpus" in c.value.lower() and "pedro" in c.value.lower() for c in result)
    assert next(c for c in result if c.value == "Pass123!").origins == ready.origins
    with pytest.raises(ValueError):
        Seed(ready, combinable=True, mutable=False)


def test_explicitly_combinable_extra_seed_uses_only_safe_partners():
    base = Candidate("Pedro", (Origin("manual", "nome", "Pedro"),))
    extra = Candidate("Silva", (Origin("manual", "alias", "Silva"),))
    unsafe = Candidate("Corpus", (Origin("dataset", "file:1", "Corpus"),))
    generation = Generation(options=GenerationOptions(combine=True, leet_mode="none"))
    values = list(prepare_generation(generation, base_candidates=[base],
                                     extra_seeds=[Seed(extra, combinable=True),
                                                  Seed(unsafe)]).generator.generate_candidates())
    joined = next(c for c in values if c.value == "silvapedro")
    assert joined.origins == extra.origins + base.origins
    assert not any("corpus" in c.value.lower() and "pedro" in c.value.lower() for c in values)
    with pytest.raises(ValueError, match="cannot be combinable"):
        list(prepare_generation(generation, base_candidates=[base],
                                extra_seeds=[Seed(unsafe, combinable=True)]
                                ).generator.generate_candidates())


def test_ready_candidates_still_obey_policy_and_first_cause():
    a = Candidate("X7!", (Origin("ready_candidate", "a:1", "X7!"),))
    b = Candidate("X7!", (Origin("ready_candidate", "b:1", "X7!"),))
    generation = Generation(options=GenerationOptions(min_len=3, require_digit=True))
    result = list(prepare_generation(generation, extra_seeds=[Seed(a, mutable=False),
                                                               Seed(b, mutable=False)]).generator.generate_candidates())
    assert result == [a]
    filtered = Generation(options=GenerationOptions(min_len=4))
    assert list(prepare_generation(filtered, extra_seeds=[Seed(a, mutable=False)]).generator.generate()) == []


def test_context_deterministic_parser_and_provenance(tmp_path):
    path = tmp_path / "InfoPedro.txt"
    path.write_text("# comment\nnome: Pedro Henrique\napelidos: Pedro, PH\n\n"
                    "data_nascimento: 17/08/2002\ntime_futebol: Palmeiras\n"
                    "pet: Toby\nempresa: ACME\ncidade: João Pessoa\n", encoding="utf-8")
    facts = load_context(str(path))
    assert [f.field for f in facts] == ["nome", "apelidos", "apelidos", "data_nascimento",
                                       "time_futebol", "pet", "empresa", "cidade"]
    assert all(f.candidate.origins[0].source == "context_file" for f in facts)
    assert all(str(path) in f.candidate.origins[0].field for f in facts)
    plan = prepare_generation(Generation(options=GenerationOptions(leet_mode="none")),
                              context_facts=facts)
    result = list(plan.generator.generate_candidates())
    assert any(c.value == "Pedro Henrique17082002" and
               {o.source for o in c.origins} == {"context_file"} for c in result)
    assert BehaviorPattern.TARGET_DATE in plan.patterns


@pytest.mark.parametrize("text", ["unknown: value", "free text", "nome: Pedro\nother: x"])
def test_invalid_context_field_or_format(text):
    with pytest.raises(ValueError):
        KeyValueContextExtractor().extract(text)


def test_dataset_streaming_limits_and_ptbr(tmp_path):
    path = tmp_path / "corpus.txt"
    path.write_text("# header\nAlpha\n\nBeta\n", encoding="utf-8")
    stream = stream_dataset(str(path), max_lines=4)
    assert iter(stream) is stream
    first = next(stream)
    assert first.candidate.value == "Alpha"
    assert first.candidate.origins == (Origin("dataset", f"{path}:2", "Alpha"),)
    assert [seed.candidate.value for seed in stream] == ["Beta"]
    with pytest.raises(ValueError, match="exceeds"):
        list(stream_dataset(str(path), max_lines=3))
    assert [seed.candidate.value for seed in stream_dataset(str(path), max_lines=4)] == ["Alpha", "Beta"]
    assert [seed.candidate.value for seed in stream_dataset(str(path), max_lines=5)] == ["Alpha", "Beta"]
    ready = list(stream_dataset(str(path), ready=True))
    assert all(not seed.mutable and not seed.combinable for seed in ready)
    assert ready[0].candidate.origins[0].source == "ready_candidate"
    ptbr = list(stream_ptbr())
    assert {s.candidate.origins[0].field.split(":")[0] for s in ptbr} == {
        "ptbr.football_teams", "ptbr.reset_words", "ptbr.common_terms", "ptbr.cities"}
    assert all(not s.combinable for s in ptbr)


def test_multisource_first_cause_precedence(tmp_path):
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("Flamengo\n", encoding="utf-8")
    dataset = next(stream_dataset(str(corpus)))
    ready = Seed(Candidate("Flamengo", (Origin("ready_candidate", "known:1", "Flamengo"),)),
                 mutable=False)
    ptbr = next(seed for seed in stream_ptbr() if seed.candidate.value == "Flamengo")
    org = Organization("ACME", keywords=["Flamengo"])
    target = Target("Flamengo", TargetProfile(nome="Flamengo"))

    def first(target_value=None, organization=None, seeds=()):
        plan = prepare_generation(
            Generation(target=target_value, organization=organization,
                       options=GenerationOptions(leet_mode="none")), extra_seeds=seeds)
        return next(c for c in plan.generator.generate_candidates() if c.value == "Flamengo")

    assert first(target, org, [ready, dataset, ptbr]).origins[0].source == "profile"
    assert first(organization=org, seeds=[ready, dataset, ptbr]).origins[0].source == "organization"
    assert first(seeds=[ready, dataset, ptbr]).origins == ready.candidate.origins
    assert first(seeds=[dataset, ptbr]).origins == dataset.candidate.origins


def test_dataset_limit_partial_output_contract(tmp_path):
    corpus = tmp_path / "known.txt"
    corpus.write_text("Alpha\nBeta\nGamma\n", encoding="utf-8")
    output = tmp_path / "out.txt"
    assert main(["generate", "--candidates", str(corpus), "--max-dataset-lines", "2",
                 "--quiet", "--no-banner", "-o", str(output)]) == 1
    assert output.read_text(encoding="utf-8") == "Alpha\nBeta\n"


def test_context_duplicate_policy_and_invalid_field(tmp_path, capsys):
    path = tmp_path / "facts.txt"
    path.write_text("# comment\n\nnome: João Pessoa\nnome: Pedro\n"
                    "apelidos: JP, Pe\napelidos: PH\n", encoding="utf-8")
    facts = load_context(str(path))
    assert [(fact.field, fact.candidate.value) for fact in facts] == [
        ("nome", "João Pessoa"), ("nome", "Pedro"),
        ("apelidos", "JP"), ("apelidos", "Pe"), ("apelidos", "PH")]
    assert main(["profile", "inspect", str(path)]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "nome": ["João Pessoa", "Pedro"], "apelidos": ["JP", "Pe", "PH"]}
    path.write_text("campo_desconhecido: foo\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown context field"):
        load_context(str(path))


@pytest.mark.parametrize("args,expected", [
    (["--help"], "--names"), (["generate", "--help"], "--context"),
    (["profile", "--help"], "inspect"),
    (["profile", "inspect", "--help"], "path"),
    (["--version"], "mimic"),
])
def test_cli_help_routes(args, expected, capsys):
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 0
    assert expected in capsys.readouterr().out


def test_new_and_legacy_cli(tmp_path, capsys):
    output = tmp_path / "output.txt"
    assert main(["generate", "-n", "Pedro", "-d", "17/08/2002", "-t", "Palmeiras",
                 "-p", "Toby", "-o", str(output), "--leet", "none",
                 "--quiet", "--no-banner"]) == 0
    values = output.read_text(encoding="utf-8").splitlines()
    assert "Pedro" in values and "Palmeiras" in values and "Toby" in values
    assert "Pedro17082002" in values
    context = tmp_path / "context.txt"
    context.write_text("nome: João\ncidade: Recife\n", encoding="utf-8")
    assert main(["profile", "inspect", str(context)]) == 0
    assert json.loads(capsys.readouterr().out) == {"nome": "João", "cidade": "Recife"}
    assert main(["generate", "--context", str(context), "-o", str(output),
                 "--leet", "none", "--quiet"]) == 0
    assert "João" in output.read_text(encoding="utf-8").splitlines()
    names = tmp_path / "names.txt"
    names.write_text("Legacy\n", encoding="utf-8")
    assert main(["--names", str(names), "-o", str(output),
                 "--leet", "none", "--quiet"]) == 0
    assert "Legacy" in output.read_text(encoding="utf-8").splitlines()


def test_cli_dataset_and_ready(tmp_path):
    dataset = tmp_path / "dataset.txt"
    dataset.write_text("Corpus\n", encoding="utf-8")
    ready = tmp_path / "ready.txt"
    ready.write_text("Pass123!\n", encoding="utf-8")
    output = tmp_path / "out.txt"
    assert main(["generate", "--dataset", str(dataset), "--candidates", str(ready),
                 "--combine", "--leet", "full", "--quiet", "-o", str(output)]) == 0
    values = output.read_text(encoding="utf-8").splitlines()
    assert "C0rpu$" in values and "Pass123!" in values
    assert "P@$$123!" not in values


def test_core_never_imports_domain():
    root = Path(__file__).parents[1] / "mimic" / "core"
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert not any(isinstance(node, ast.ImportFrom) and node.module and
                       node.module.startswith("mimic.domain") for node in ast.walk(tree))


def test_new_source_order_is_hash_seed_independent(tmp_path):
    script = ("from mimic.domain.models import Generation,GenerationOptions; "
              "from mimic.domain.planning import prepare_generation; "
              "from mimic.core.candidate import Candidate,Origin; "
              "from mimic.core.seed import Seed; "
              "a=Candidate('Pedro',(Origin('manual','nome','Pedro'),)); "
              "b=Candidate('Corpus',(Origin('dataset','x:1','Corpus'),)); "
              "print(repr(list(prepare_generation(Generation(options=GenerationOptions("
              "leet_mode='none')),base_candidates=[a],extra_seeds=[Seed(b)]).generator.generate())))")
    outputs = []
    for seed in ("1", "777"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONDONTWRITEBYTECODE": "1"}
        outputs.append(subprocess.check_output([sys.executable,
                                                "-B", "-c", script], env=env, text=True))
    assert outputs[0] == outputs[1]
