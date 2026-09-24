"""Causal provenance, immutable value contracts and compatibility."""

from dataclasses import FrozenInstanceError, asdict
import ast
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys

import pytest

from mimic.cli import main
from mimic.core.candidate import Candidate, Origin, Transformation
from mimic.core.generator import Generator
from mimic.core.policy import PasswordPolicy
from mimic.mutators.affix import AffixMutator
from mimic.mutators.base import Mutator
from mimic.mutators.case import CaseMutator
from mimic.mutators.combine import CombineMutator
from mimic.mutators.date import DateMutator
from mimic.mutators.leet import LeetMutator
from mimic.mutators.reverse import ReverseMutator
from mimic.profile.loader import build_plan
from mimic.profile.schema import TargetProfile


def seed(value="Pedro", field="nome"):
    return Candidate(value, (Origin("profile", field, value),))


def test_models_are_immutable_canonical_and_json_serializable():
    origin = Origin("profile", "nome", "Pedro")
    step = Transformation("example", (("z", "2"), ("a", "1")))
    canonical = Transformation("example", (("a", "1"), ("z", "2")))
    assert step == canonical
    origins, steps = [origin], [step]
    candidate = Candidate("Pedro", origins, steps)
    origins.clear()
    steps.clear()
    assert candidate == Candidate("Pedro", (origin,), (canonical,))
    assert hash(candidate) == hash(Candidate("Pedro", (origin,), (canonical,)))
    assert json.loads(json.dumps(asdict(candidate))) == {
        "value": "Pedro",
        "origins": [{"source": "profile", "field": "nome", "value": "Pedro"}],
        "transformations": [{"kind": "example", "params": [["a", "1"], ["z", "2"]]}],
    }
    for obj, attr in ((origin, "value"), (step, "kind"), (candidate, "value")):
        with pytest.raises(FrozenInstanceError):
            setattr(obj, attr, "changed")
    with pytest.raises(ValueError, match="unique"):
        Transformation("bad", (("x", "1"), ("x", "2")))


def test_simple_candidate_and_bare_api_seed_keep_origin():
    original = seed()
    stream = Generator([original], []).generate_candidates()
    assert next(stream) is original
    assert list(stream) == []
    bare = next(Generator(["Pedro"], []).generate_candidates())
    assert bare == Candidate("Pedro", (Origin("api", "seed", "Pedro"),))


def test_case_records_each_applied_mode_without_mutating_input():
    original = seed("pEdRo")
    results = list(CaseMutator().mutate_candidate(original))
    assert [c.value for c in results] == ["pEdRo", "pedro", "PEDRO", "Pedro"]
    assert [dict(c.transformations[-1].params) for c in results] == [
        {"mode": mode} for mode in ("original", "lower", "upper", "title")
    ]
    assert all(c.origins == original.origins for c in results)
    assert original.transformations == ()


@pytest.mark.parametrize("mode,expected", [
    ("partial", ["P3drO", "Pedr0", "P3dr0"]),
    ("full", ["P3dr0"]), ("none", ["PedrO"]),
])
def test_leet_records_actual_positions_case_and_replacements(mode, expected):
    original = seed("PedrO")
    results = list(LeetMutator(mode).mutate_candidate(original))
    assert [c.value for c in results] == expected
    for result in results:
        replay = list(original.value)
        for step in result.transformations:
            p = dict(step.params)
            assert step.kind == "leet"
            index = int(p["position"])
            assert replay[index] == p["from"]
            assert p["mode"] == mode
            replay[index] = p["to"]
        assert "".join(replay) == result.value
        assert result.origins == original.origins
    if mode != "none":
        assert dict(results[-1].transformations[-1].params)["from"] == "O"


def test_affix_records_all_five_layouts_and_token_origin():
    original = seed("Xy")
    token = Candidate("12", (Origin("cli", "numbers", "12"),))
    results = list(AffixMutator([token], "@").mutate_candidate(original))
    assert results[0] is original
    assert [c.value for c in results] == ["Xy", "Xy12", "12Xy", "Xy@12", "Xy12@", "@Xy12"]
    expected = [("suffix", "", "none"), ("prefix", "", "none"),
                ("suffix", "@", "between"), ("suffix", "@", "after"),
                ("suffix", "@", "before")]
    for c, (placement, separator, position) in zip(results[1:], expected):
        assert c.origins == original.origins + token.origins
        step = c.transformations[-1]
        assert step.kind == "affix"
        p = dict(step.params)
        assert (p["token"], p["placement"], p["separator"], p["separator_position"]) == (
            "12", placement, separator, position,
        )


def test_date_causality_survives_plan_leet_and_affix():
    plan = build_plan(TargetProfile(nome="Pedro", data_nascimento="05/09"))
    assert plan.numbers == [c.value for c in plan.number_candidates]
    token = plan.number_candidates[1]
    assert token.value == "0905"
    assert token.origins == (Origin("profile", "data_nascimento", "05/09"),)
    assert dict(token.transformations[0].params)["format"] == "mmdd"
    gen = Generator(plan.base_candidates, [CaseMutator(), LeetMutator(),
                    AffixMutator(plan.number_candidates, "@")])
    result = next(c for c in gen.generate_candidates() if c.value == "P3dro0905@")
    assert result.origins == seed().origins + token.origins
    assert [t.kind for t in result.transformations] == ["case", "leet", "date", "affix"]
    p = dict(result.transformations[-1].params)
    assert (p["input_steps"], p["token_steps"]) == ("2", "1")
    assert dict(result.transformations[1].params)["position"] == "1"


def test_date_duplicate_token_keeps_first_format():
    results = list(DateMutator().mutate_candidate(seed("12/11", "data_nascimento")))
    assert [c.value for c in results] == ["1211", "1112"]
    assert [dict(c.transformations[0].params)["format"] for c in results] == ["ddmm", "mmdd"]


def test_combine_keeps_both_origins_and_exact_operand_layout():
    left, right = seed(), seed("Silva", "apelidos")
    results = list(CombineMutator([left, right], ".").mutate_candidate(left))
    assert [c.value for c in results] == [
        "pedrosilva", "silvapedro", "psilva", "spedro", "pedro.silva", "silva.pedro",
    ]
    for c in results:
        p = dict(c.transformations[-1].params)
        assert c.transformations[-1].kind == "combine"
        assert p["normalization"] == "lower"
        a = p["left"].lower()
        if p["left_form"] == "initial":
            a = a[0]
        assert a + p["separator"] + p["right"].lower() == c.value
        assert {o.field for o in c.origins} == {"nome", "apelidos"}
    assert results[0].origins == left.origins + right.origins
    assert results[1].origins == right.origins + left.origins


def test_join_keeps_operand_histories_without_claiming_alternative_derivations():
    left = next(ReverseMutator().mutate_candidate(seed("or")))
    right = next(DateMutator().mutate_candidate(seed("05/09", "date")))
    combined = next(CombineMutator([right], "").mutate_candidate(left))
    assert [s.kind for s in combined.transformations] == ["reverse", "date", "combine"]
    assert dict(combined.transformations[-1].params)["left_steps"] == "1"
    assert dict(combined.transformations[-1].params)["right_steps"] == "1"


def test_reverse_is_causal_and_still_independent():
    original = seed()
    results = list(Generator([original], [CaseMutator()], reverse=ReverseMutator()).generate_candidates())
    reverse = next(c for c in results if c.value == "ordeP")
    assert reverse.origins == original.origins
    assert reverse.transformations == (Transformation("reverse"),)
    assert "ORDEP" not in [c.value for c in results]


def test_stage_and_global_dedup_first_causal_derivation_wins():
    first, second = seed("Pedro", "nome"), seed("Pedro", "apelidos")
    results = list(Generator([first, second], [CaseMutator()]).generate_candidates())
    assert [c.value for c in results] == ["Pedro", "pedro", "PEDRO"]
    assert all(c.origins == first.origins for c in results)
    assert results[0].transformations == (Transformation("case", (("mode", "original"),)),)
    tokens = [Candidate("12", (Origin("cli", "numbers", "12"),)), seed("12", "date")]
    affixed = list(Generator([first], [AffixMutator(tokens, "")]).generate_candidates())
    assert next(c for c in affixed if c.value == "Pedro12").origins == first.origins + tokens[0].origins


def test_profile_duplicate_values_do_not_overwrite_causal_origins():
    plan = build_plan(TargetProfile(nome="Rex", pet="Rex"))
    assert plan.base_candidates[0].origins == (Origin("profile", "nome", "Rex"),)
    assert plan.isolated_candidates[0].origins == (Origin("profile", "pet", "Rex"),)
    results = list(Generator(plan.base_candidates, [], isolated_seeds=plan.isolated_candidates).generate_candidates())
    assert results == plan.base_candidates


def test_structured_projection_policy_and_isolation():
    plan = build_plan(TargetProfile(nome="Pedro", apelidos=["Silva"], pet="Rex", data_nascimento="05/09"))
    gen = Generator(plan.base_candidates, [CaseMutator(), LeetMutator(), AffixMutator(plan.number_candidates, "@")],
                    policy=PasswordPolicy(min_len=8, require_digit=True),
                    isolated_seeds=plan.isolated_candidates,
                    combine=CombineMutator(plan.base_candidates, ""), reverse=ReverseMutator())
    candidates = list(gen.generate_candidates())
    assert candidates and all(isinstance(c, Candidate) for c in candidates)
    assert list(gen.generate()) == [c.value for c in candidates]
    assert list(gen.generate_candidates()) == candidates
    assert all(len(c.value) >= 8 for c in candidates)
    assert not any(any(o.field == "pet" for o in c.origins) and
                   any(t.kind == "combine" for t in c.transformations) for c in candidates)


def test_legacy_external_mutator_remains_usable_but_is_explicitly_opaque():
    class External(Mutator):
        def mutate(self, word):
            yield word + "!"
    gen = Generator([seed()], [External()])
    assert list(gen.generate()) == ["Pedro!"]
    c = next(gen.generate_candidates())
    assert c.origins == seed().origins
    assert c.transformations[0].kind == "legacy"
    assert dict(c.transformations[0].params)["input"] == "Pedro"
    assert dict(c.transformations[0].params)["output"] == "Pedro!"


def test_debug_uses_real_origins_not_string_matching(tmp_path, monkeypatch, caplog):
    def forbidden(*args, **kwargs):
        raise AssertionError("heuristic must not be called")
    monkeypatch.setattr("mimic.profile.loader.explain_candidate", forbidden)
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"nome": "Pedro", "apelidos": ["Silva"],
                                  "data_nascimento": "05/09"}), encoding="utf-8")
    names = tmp_path / "names.txt"
    names.write_text("unrelated0905\n", encoding="utf-8")
    output = tmp_path / "out.txt"
    with caplog.at_level(logging.DEBUG, logger="mimic"):
        assert main(["--names", str(names), "--profile", str(profile), "--debug", "--quiet",
                     "--combine", "--leet", "none", "--separators", "", "-o", str(output)]) == 0
    messages = [r.getMessage() for r in caplog.records]
    unrelated = next(m for m in messages if m.startswith("unrelated0905 <-"))
    assert "cli.names=unrelated0905" in unrelated
    assert "data_nascimento" not in unrelated
    combined = next(m for m in messages if m.startswith("pedrosilva <-"))
    assert "profile.nome=Pedro" in combined and "profile.apelidos=Silva" in combined
    assert "combine(" in combined
    reverse = next(m for m in messages if m.startswith("ordeP <-"))
    assert "profile.nome=Pedro" in reverse and "reverse()" in reverse


def test_debug_without_profile_records_cli_sources(tmp_path, caplog):
    names, numbers = tmp_path / "names.txt", tmp_path / "numbers.txt"
    names.write_text("xy\n", encoding="utf-8")
    numbers.write_text("12\n", encoding="utf-8")
    with caplog.at_level(logging.DEBUG, logger="mimic"):
        assert main(["--names", str(names), "--numbers", str(numbers), "--year-range", "2024:2024",
                     "--leet", "none", "--debug", "--quiet", "-o", str(tmp_path / "out")]) == 0
    messages = [r.getMessage() for r in caplog.records]
    assert "cli.numbers=12" in next(m for m in messages if m.startswith("xy12 <-"))
    assert "cli.year_range=2024" in next(m for m in messages if m.startswith("xy2024 <-"))


def test_provenance_deterministic_across_processes():
    code = '''
import json
from dataclasses import asdict
from mimic.profile.schema import TargetProfile
from mimic.profile.loader import build_plan
from mimic.core.generator import Generator
from mimic.mutators.combine import CombineMutator
from mimic.mutators.leet import LeetMutator
from mimic.mutators.affix import AffixMutator
p = build_plan(TargetProfile(nome="Pedro", apelidos=["Silva"], data_nascimento="05/09"))
g = Generator(p.base_candidates, [LeetMutator(), AffixMutator(p.number_candidates, "@")], combine=CombineMutator(p.base_candidates, ""))
print(json.dumps([asdict(c) for c in g.generate_candidates()], ensure_ascii=False))
'''
    outputs = [subprocess.check_output(
        [sys.executable, "-B", "-c", code], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONHASHSEED": str(n), "PYTHONDONTWRITEBYTECODE": "1"},
    ) for n in (1, 2, 42)]
    assert outputs[0] == outputs[1] == outputs[2]


def test_core_has_no_profile_dependency():
    core = Path(__file__).resolve().parents[1] / "mimic" / "core"
    for path in core.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("mimic.profile")
                assert all(alias.name != "TargetProfile" for alias in node.names)
            elif isinstance(node, ast.Import):
                assert all(not alias.name.startswith("mimic.profile") for alias in node.names)


def test_structured_stream_does_not_process_later_seeds_early():
    visited = []

    class Observe(Mutator):
        def mutate(self, word):
            visited.append(word)
            yield word

    stream = Generator([seed("one"), seed("two")], [Observe()]).generate_candidates()
    assert visited == []
    assert next(stream).value == "one"
    assert visited == ["one"]
    assert next(stream).value == "two"
    assert visited == ["one", "two"]


def test_cli_debug_preserves_exact_stdout(tmp_path, capsys, caplog):
    profile = tmp_path / "profile.json"
    profile.write_text('{"nome":"Pedro","data_nascimento":"05/09"}', encoding="utf-8")
    args = ["--profile", str(profile), "--quiet", "--separators", "@"]
    assert main(args) == 0
    plain = capsys.readouterr().out
    with caplog.at_level(logging.DEBUG, logger="mimic"):
        assert main(args + ["--debug"]) == 0
    assert capsys.readouterr().out == plain
    assert "P3dro0905@\n" in plain


# Captured from HEAD 6044df7 before any implementation change.
@pytest.mark.parametrize("mode,cap,combine,count,digest", [
    ('none', 3, False, 10, 'd486531daf30565f323450e61c20dc3c6ca6b3a9e856607f57e46f7858ccb93d'),
    ('none', 3, True, 42, '19c81d2d46c70dd5cf2713e0b9489688feb34b221661b757e9719c0320e9497a'),
    ('none', 5000, False, 152, '2d2b3768aa855c7b28ce4ca4d059a13213a7232a11fa1bcffce8801fcae24c76'),
    ('none', 5000, True, 568, '565f1fd151b1a6723734d741c59666bcbfa3369f3334a99b3d6858d06b653cc5'),
    ('partial', 3, False, 10, 'd867fcc3c19edb8027e69e327c2419773cb893e0dd48e0dada3dda1e4b10a1ae'),
    ('partial', 3, True, 42, '78fbf60c153563b423fbf892449f6d2c4b362ca73d6787cc0a71c8e7542512d9'),
    ('partial', 5000, False, 458, '2e9a857d99bc937911bcc1ac3166452941061fbbda9489f1ab9c396aa7013bd6'),
    ('partial', 5000, True, 5532, '473c5400c76adac170fbf98ca2d2289a58172ec5124ec49a128d5032b81b7e77'),
    ('full', 3, False, 10, '2d3fc9025e907a64f42509b3b22ac0e70e97dee36a28bad0f069bb14532f9c3c'),
    ('full', 3, True, 42, 'a27bb54c282d166c8b1ef9a9a56064813260ed9d21edae091bcabf967f038087'),
    ('full', 5000, False, 135, '7b813eaf5f99497cc350b94b22ee489c41c1f314cf32432468a7cb73b5298db6'),
    ('full', 5000, True, 517, 'a89bd1e6883ce81ac824f6bc8b9f31de48e6b2dd1963906517faa5df69e6cd89'),
])
def test_legacy_output_matches_prechange_snapshot(mode, cap, combine, count, digest):
    names = ["Pedro", "Silva", "Pedro"]
    gen = Generator(
        names, [CaseMutator(), LeetMutator(mode), AffixMutator(["0905", "12"], "@_")],
        policy=PasswordPolicy(min_len=4),
        combine=CombineMutator(names, "@_") if combine else None,
        reverse=ReverseMutator(), isolated_seeds=["Rex"], max_candidates_per_word=cap,
    )
    values = list(gen.generate())
    assert len(values) == count
    assert hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest() == digest
