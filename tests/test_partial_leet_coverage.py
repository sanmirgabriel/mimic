"""Partial's zero-substitution cause survives composition and every adapter."""

import pytest

from mimic.application import (GenerationRequest, GenerationService,
                               IntelligenceOptions, MutationOptions, RankingOptions)
from mimic.cli import main
from mimic.core.candidate import Candidate, Origin, Transformation
from mimic.core.generator import Generator
from mimic.jobs import JobManager
from mimic.mutators.affix import AffixMutator
from mimic.mutators.case import CaseMutator
from mimic.mutators.leet import LeetMutator
from mimic.persistence import DataPaths, Database, Repository
from mimic.ranking.scoring import score_candidate


def contextual_request(ranked=False):
    return GenerationRequest(
        base_candidates=(Candidate("ACMEeditor", (
            Origin("organization", "name", "ACME"),
            Origin("knowledge", "service.wordpress.role", "editor"))),),
        number_candidates=(Candidate("2026", (Origin("knowledge", "recent_year", "2026"),)),),
        intelligence=IntelligenceOptions(enabled=False, reference_year=2026),
        mutations=MutationOptions(leet_mode="partial", separators=""),
        ranking=RankingOptions(True, 100) if ranked else RankingOptions())


def test_generator_zero_and_one_substitution_reach_affix_with_exact_provenance():
    origin = Origin("organization", "name", "ACME")
    number = Candidate("123", (Origin("knowledge", "common_number", "123"),))
    candidates = list(Generator([Candidate("ACME", (origin,))],
        [CaseMutator(), LeetMutator("partial"), AffixMutator([number], "")]
    ).generate_candidates())
    assert [c.value for c in candidates[:12]] == [
        "ACME", "ACME123", "123ACME", "@CME", "@CME123", "123@CME",
        "ACM3", "ACM3123", "123ACM3", "@CM3", "@CM3123", "123@CM3"]
    original = next(c for c in candidates if c.value == "ACME123")
    leeted = next(c for c in candidates if c.value == "@CME123")
    case = Transformation("case", (("mode", "original"),))
    assert original == Candidate("ACME123", (origin,) + number.origins, (
        case, Transformation("affix", (("input", "ACME"), ("input_steps", "1"),
            ("token", "123"), ("token_steps", "0"), ("placement", "suffix"),
            ("separator", ""), ("separator_position", "none")))))
    assert leeted == Candidate("@CME123", original.origins, (
        case, Transformation("leet", (("mode", "partial"), ("from", "A"),
            ("to", "@"), ("position", "0"))),
        Transformation("affix", (("input", "@CME"), ("input_steps", "2"),
            ("token", "123"), ("token_steps", "0"), ("placement", "suffix"),
            ("separator", ""), ("separator_position", "none")))))


def test_generator_case_convergence_keeps_first_cause():
    candidates = list(Generator([Candidate("Aa")],
        [CaseMutator(), LeetMutator("partial")]).generate_candidates())
    assert [c.value for c in candidates] == [
        "Aa", "@a", "A@", "@@", "aa", "a@", "AA", "@A"]
    both = next(c for c in candidates if c.value == "@@")
    assert dict(both.transformations[0].params) == {"mode": "original"}
    assert [dict(t.params)["from"] for t in both.transformations[1:]] == ["A", "a"]


@pytest.mark.parametrize("cap,expected", [
    (3, ["ACME", "ACME123", "123ACME"]),
    (6, ["ACME", "ACME123", "123ACME", "@CME", "@CME123", "123@CME"]),
])
def test_zero_leet_precedes_substitutions_when_affix_cap_is_hit(cap, expected, caplog):
    candidates = list(Generator(["ACME"],
        [CaseMutator(), LeetMutator("partial"), AffixMutator(["123"], "")],
        max_candidates_per_word=cap).generate_candidates())
    assert [c.value for c in candidates] == expected
    assert not any(t.kind == "leet" for c in candidates[:3] for t in c.transformations)
    assert any("Truncated stage=AffixMutator" in r.message for r in caplog.records)


@pytest.mark.parametrize("ranked", [False, True])
def test_application_partial_scores_only_actual_substitutions(ranked):
    prepared = GenerationService().prepare(contextual_request(ranked))
    results = list(prepared.iter_results())
    by_value = {r.candidate.value: r for r in results}
    values = ["ACMEeditor2026", "@CMEeditor2026", "@CM3editor2026"]
    candidates = [by_value[value].candidate for value in values]
    assert all(c.origins == candidates[0].origins for c in candidates)
    assert [sum(t.kind == "leet" for t in c.transformations) for c in candidates] == [0, 1, 2]
    assert dict(candidates[1].transformations[1].params) == {
        "mode": "partial", "from": "A", "to": "@", "position": "0"}
    scores = [score_candidate(c, 2026) for c in candidates]
    assert [s.total for s in scores] == [52, 50, 48]
    assert all(s.version == "score-v1" for s in scores)
    for count, score in enumerate(scores):
        leet = [c for c in score.components if c.code == "transformation.leet"]
        assert [c.delta for c in leet] == [-2] * count
        assert [(c.code, c.delta) for c in score.components if c.code != "transformation.leet"] == [
            (c.code, c.delta) for c in scores[0].components]
    if ranked:
        assert [by_value[v].score for v in values] == scores
        assert by_value[values[0]].rank < by_value[values[1]].rank < by_value[values[2]].rank
    else:
        assert all(r.score is None and r.rank is None for r in results)
        assert list(by_value).index(values[0]) < list(by_value).index(values[1])
    assert prepared.evaluated_count == 247
    assert len(results) == (100 if ranked else 247)


@pytest.mark.parametrize("ranked", [False, True])
def test_partial_jobs_persist_zero_leet_without_schema_change(tmp_path, ranked):
    paths = DataPaths(tmp_path)
    database = Database(paths)
    database.initialize()
    repository = Repository(database)
    manager = JobManager(repository, paths)
    manager.start()
    try:
        expected = list(GenerationService().prepare(contextual_request(ranked)).iter_results())
        submitted = manager.submit(contextual_request(ranked))
        job = manager.wait(submitted["id"], 10)
        assert job["status"] == "completed"
        assert manager.completed_output(job["id"]).read_text().splitlines() == [
            r.candidate.value for r in expected]
        row = next(r for r in repository.list_preview(job["id"])
                   if r["value"] == "ACMEeditor2026")
        result = next(r for r in expected if r.candidate.value == row["value"])
        stored = Candidate(row["value"], tuple(Origin(**o) for o in row["origins"]),
            tuple(Transformation(t["kind"], tuple(tuple(p) for p in t["params"]))
                  for t in row["transformations"]))
        assert stored == result.candidate
        assert not any(t["kind"] == "leet" for t in row["transformations"])
        assert row["score"] == (52 if ranked else None)
        assert row["score_version"] == ("score-v1" if ranked else None)
        with database.connection() as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
    finally:
        manager.stop()


@pytest.mark.parametrize("command", [[], ["generate"]])
def test_legacy_and_modern_cli_share_partial_coverage(tmp_path, command):
    path = tmp_path / "partial.txt"
    assert main([*command, "-n", "ACME", "--no-intelligence", "--leet", "partial",
                 "--year-range", "2026:2026", "--separators", "", "--quiet",
                 "--no-banner", "-o", str(path)]) == 0
    values = path.read_text().splitlines()
    assert "ACME2026" in values and "@CME2026" in values and "@CM32026" in values
    assert values.index("ACME2026") < values.index("@CME2026") < values.index("@CM32026")
