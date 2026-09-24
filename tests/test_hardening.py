"""Block 2 input validation, Unicode and causal regression coverage."""

import logging

import pytest

from mimic.cli import _parse_year_range, main
from mimic.core.candidate import Candidate, Origin, Transformation
from mimic.core.generator import Generator
from mimic.core.policy import PasswordPolicy
from mimic.mutators.base import StructuredMutator
from mimic.mutators.combine import CombineMutator
from mimic.mutators.date import DateMutator
from mimic.mutators.leet import LeetMutator
from mimic.profile.loader import build_plan, load_profile_file
from mimic.profile.schema import TargetProfile


@pytest.mark.parametrize("field", ["nome", "data_nascimento", "time_futebol", "empresa", "pet"])
@pytest.mark.parametrize("value", [123, True, [], {}])
def test_profile_scalar_types(field, value):
    with pytest.raises(ValueError, match=field):
        TargetProfile.from_dict({field: value})
    with pytest.raises(ValueError, match=field):
        TargetProfile(**{field: value})


@pytest.mark.parametrize("value", [None, "Pedro", ("Pedro",), [123], [True], [None]])
def test_apelidos_invalid_types_are_not_coerced(value):
    with pytest.raises(ValueError, match="apelidos"):
        TargetProfile.from_dict({"apelidos": value})


def test_profile_strips_only_external_whitespace_and_discards_empty_values():
    p = TargetProfile.from_dict({
        "nome": "  João  ", "apelidos": [" Pedro ", "", "  ", "Pepe"],
        "empresa": " São Paulo ", "time_futebol": " Flamengo ", "pet": "\t",
        "data_nascimento": " 05/09 ",
    })
    assert (p.nome, p.apelidos, p.empresa, p.time_futebol, p.pet, p.data_nascimento) == (
        "João", ["Pedro", "Pepe"], "São Paulo", "Flamengo", None, "05/09",
    )
    assert TargetProfile(nome="", data_nascimento=" ").nome is None
    assert build_plan(TargetProfile(nome=" ", apelidos=[" "])).base_candidates == []


@pytest.mark.parametrize("word,full", [
    ("Pedro", "P3dr0"), ("PEDRO", "P3DR0"), ("João", "J0ã0"),
    ("Árvore", "Árv0r3"), ("İa", "İ@"), ("Straße", "$7r@ß3"),
])
def test_unicode_leet_full_and_partial_keep_original_codepoint_positions(word, full):
    source = Candidate(word, (Origin("test", "word", word),))
    assert list(LeetMutator("full").mutate(word)) == [full]
    for mode in ("partial", "full"):
        for result in LeetMutator(mode).mutate_candidate(source):
            replay = list(word)
            for step in result.transformations:
                p = dict(step.params)
                i = int(p["position"])
                assert replay[i] == p["from"]
                replay[i] = p["to"]
            assert "".join(replay) == result.value
            assert result.origins == source.origins
    if word == "İa":
        c = next(LeetMutator().mutate_candidate(source))
        assert dict(c.transformations[0].params)["position"] == "1"


@pytest.mark.parametrize("word", ["İ", "á", "Á", "ç", "ß"])
def test_leet_does_not_transliterate_unmapped_characters(word):
    assert list(LeetMutator("full").mutate(word)) == [word]


@pytest.mark.parametrize("flag,value,accepted", [
    ("require_upper", "Á", True), ("require_lower", "á", True),
    ("require_lower", "ç", True), ("require_upper", "İ", True),
    ("require_digit", "1", True), ("require_digit", "١", True),
    ("require_digit", "²", True), ("require_special", "@", True),
    ("require_special", "áçÁ", False), ("require_special", " ", True),
    ("require_special", "\t", True), ("require_special", "", False),
])
def test_unicode_policy_classes(flag, value, accepted):
    assert PasswordPolicy(**{flag: True}).accepts(value) is accepted


@pytest.mark.parametrize("kwargs", [{"min_len": -1}, {"max_len": -1}, {"min_len": 12, "max_len": 8}])
def test_policy_invalid_lengths_fail_early(kwargs):
    with pytest.raises(ValueError, match="min_len|max_len"):
        PasswordPolicy(**kwargs)


def test_policy_zero_max_remains_unlimited():
    p = PasswordPolicy(min_len=8, max_len=0)
    assert p.accepts("á" * 100)
    assert not p.accepts("á" * 7)


@pytest.mark.parametrize("value", ["29/02/2023", "31/04/2020", "31/02/2000", "31/04", "01/01/0000"])
def test_invalid_calendar_dates(value):
    with pytest.raises(ValueError, match="calendar date"):
        list(DateMutator().mutate(value))


@pytest.mark.parametrize("value", ["29/02", "29/02/2024"])
def test_leap_day_validity_preserves_tokens_and_original_causality(value):
    c = Candidate(value, (Origin("profile", "data_nascimento", value),))
    tokens = list(DateMutator().mutate_candidate(c))
    expected = ["2902", "0229", "229"]
    if value.endswith("2024"):
        expected += ["2024", "24", "29022024"]
    assert [t.value for t in tokens] == expected
    assert all(t.origins == c.origins for t in tokens)
    assert all(dict(t.transformations[0].params)["input"] == value for t in tokens)
    if value == "29/02":
        assert all("2000" not in t.value for t in tokens)


@pytest.mark.parametrize("cap", [0, -1])
def test_invalid_cap_fails_at_constructor(cap):
    with pytest.raises(ValueError, match="max_candidates_per_word"):
        Generator(["x"], [], max_candidates_per_word=cap)


@pytest.mark.parametrize("cap", [1, 5000])
def test_valid_cap(cap):
    assert list(Generator(["x"], [], max_candidates_per_word=cap).generate()) == ["x"]


@pytest.mark.parametrize("value", [1.5, "2", True])
def test_noninteger_configuration_has_clear_errors(value):
    with pytest.raises(TypeError, match="integer"):
        Generator([], [], max_candidates_per_word=value)
    with pytest.raises(TypeError, match="integer"):
        PasswordPolicy(min_len=value)


def test_empty_generator_and_combine_inputs_are_filtered():
    values = ["", "   ", Candidate("\t"), "Pedro"]
    assert list(Generator(values, [], isolated_seeds=["\n"]).generate()) == ["Pedro"]
    m = CombineMutator(values + ["Silva"])
    assert m.all_names == ["pedro", "silva"]
    for empty in ("", " ", "\t"):
        assert list(m.mutate(empty)) == []
    assert "pedrosilva" in list(m.mutate("Pedro"))
    # Nonempty explicit candidates are not silently stripped/re-attributed.
    c = Candidate(" Pedro ", (Origin("test", "seed", " Pedro "),))
    assert next(Generator([c], []).generate_candidates()) is c


def test_input_dedup_keeps_distinct_causes_and_preserves_first_output():
    first = Candidate("Pedro", (Origin("profile", "nome", "Pedro"),))
    second = Candidate("Pedro", (Origin("profile", "apelidos", "Pedro"),))
    visited = []

    class Observe(StructuredMutator):
        def mutate_candidate(self, candidate):
            visited.append(candidate)
            yield candidate

    g = Generator([first, first, second, second], [Observe()], isolated_seeds=[first])
    assert list(g.generate_candidates()) == [first]
    assert visited == [first, second]
    visited.clear()
    assert list(g.generate()) == ["Pedro"]
    assert visited == [first, second]


def test_metadata_sensitive_mutator_does_not_lose_equal_value_inputs():
    a = Candidate("x", (Origin("test", "first", "x"),))
    b = Candidate("x", (Origin("test", "second", "x"),))
    c = a.derive("x", Transformation("prior"))

    class Sensitive(StructuredMutator):
        def mutate_candidate(self, candidate):
            suffix = candidate.origins[0].field + str(len(candidate.transformations))
            yield candidate.derive(candidate.value + suffix, Transformation("custom"))

    assert list(Generator([a, a, b, c], [Sensitive()]).generate()) == ["xfirst0", "xsecond0", "xfirst1"]


def test_duplicate_base_does_not_lose_combine_eligibility_or_other_partner_origins():
    a = Candidate("Pedro", (Origin("profile", "nome", "Pedro"),))
    b = Candidate("Silva", (Origin("profile", "apelidos", "Silva"),))
    c = Candidate("Silva", (Origin("cli", "names", "Silva"),))
    m = CombineMutator([a, a, b, b, c], "")
    # Different causes are not collapsed into a single lowercase value.
    assert m.all_names == ["pedro", "silva", "silva"]
    g = Generator([a, a], [], isolated_seeds=[a], combine=m)
    result = next(v for v in g.generate_candidates() if v.value == "pedrosilva")
    assert result.origins == a.origins + b.origins


@pytest.mark.parametrize("value", ["2026:2020", "0:999999999", "1:201", "abc:2026", "2026"])
def test_year_range_invalid_or_excessive(value):
    with pytest.raises(ValueError):
        _parse_year_range(value)


def test_year_range_inclusive_limit():
    assert _parse_year_range("2024:2024") == ["2024"]
    assert len(_parse_year_range("1800:1999")) == 200


@pytest.mark.parametrize("extra", [[], ["--year-range", "2020:2026"]])
def test_export_rules_without_names_never_reads_stdin(tmp_path, monkeypatch, extra):
    class ForbiddenStdin:
        def __iter__(self):
            raise AssertionError("export rules must not read stdin")

    monkeypatch.setattr("sys.stdin", ForbiddenStdin())
    path = tmp_path / "rules.rule"
    assert main(["--export-rules", str(path), "--quiet", *extra]) == 0
    rules = path.read_text(encoding="utf-8").splitlines()
    assert rules[:5] == [":", "l", "u", "c", "r"]
    assert "sa@" in rules
    if extra:
        assert "$2$0$2$0" in rules and "$2$0$2$6" in rules


@pytest.mark.parametrize("extra", [["--max-per-word", "0"], ["--min-len", "-1"],
                                  ["--min-len", "12", "--max-len", "8"],
                                  ["--year-range", "2026:2020"]])
def test_cli_validation_errors_return_one_without_output(tmp_path, extra, caplog):
    path = tmp_path / "names"
    path.write_text("Pedro\n", encoding="utf-8")
    output = tmp_path / "out"
    with caplog.at_level(logging.ERROR):
        assert main(["--names", str(path), "-o", str(output), "--quiet", *extra]) == 1
    assert not output.exists()
    assert caplog.records


def test_yaml_syntax_and_scalar_errors_are_clear(tmp_path):
    pytest.importorskip("yaml")
    path = tmp_path / "profile.yaml"
    for content in ("nome: [broken", "false", "[]", "nome: 123"):
        path.write_text(content, encoding="utf-8")
        with pytest.raises(ValueError):
            load_profile_file(str(path))
        assert main(["--profile", str(path), "--quiet"]) == 1
