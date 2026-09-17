"""Tests for profile/loader.py: file loading, field routing, and trace explanation."""

from __future__ import annotations

from pathlib import Path

import pytest

from mimic.profile.loader import ProfilePlan, build_plan, explain_candidate, load_profile_file
from mimic.profile.schema import TargetProfile


def test_load_json_profile(tmp_path: Path) -> None:
    path = tmp_path / "profile.json"
    path.write_text(
        '{"nome": "Pedro", "time_futebol": "Flamengo", '
        '"data_nascimento": "05/09/2000"}',
        encoding="utf-8",
    )
    profile = load_profile_file(str(path))
    assert profile.nome == "Pedro"
    assert profile.time_futebol == "Flamengo"


def test_load_yaml_profile(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    path = tmp_path / "profile.yaml"
    path.write_text(
        "nome: Pedro\n"
        "apelidos:\n  - Pedrinho\n"
        "time_futebol: Flamengo\n"
        "data_nascimento: 05/09/2000\n",
        encoding="utf-8",
    )
    profile = load_profile_file(str(path))
    assert profile.nome == "Pedro"
    assert profile.apelidos == ["Pedrinho"]
    assert profile.time_futebol == "Flamengo"


def test_load_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "profile.txt"
    path.write_text("nome: Pedro", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported profile file extension"):
        load_profile_file(str(path))


def test_load_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_profile_file("/nonexistent/profile.json")


def test_build_plan_routes_nome_and_apelidos_to_base_words() -> None:
    profile = TargetProfile(nome="Pedro", apelidos=["Pedrinho"])
    plan = build_plan(profile)
    assert "Pedro" in plan.base_words
    assert "Pedrinho" in plan.base_words
    assert plan.isolated_seeds == []


def test_build_plan_routes_time_futebol_to_isolated_seeds() -> None:
    """time_futebol must never end up in base_words (which --combine cross-pairs)."""
    profile = TargetProfile(nome="Pedro", time_futebol="Flamengo")
    plan = build_plan(profile)
    assert "Flamengo" in plan.isolated_seeds
    assert "Flamengo" not in plan.base_words


def test_build_plan_routes_empresa_and_pet_to_isolated_seeds() -> None:
    profile = TargetProfile(empresa="Acme", pet="Rex")
    plan = build_plan(profile)
    assert set(plan.isolated_seeds) == {"Acme", "Rex"}


def test_build_plan_expands_data_nascimento_via_date_mutator() -> None:
    profile = TargetProfile(data_nascimento="05/09/2000")
    plan = build_plan(profile)
    assert "0905" in plan.numbers
    assert "2000" in plan.numbers
    assert plan.number_field["0905"] == "data_nascimento=05/09/2000"


def test_build_plan_empty_profile_produces_empty_plan() -> None:
    plan = build_plan(TargetProfile())
    assert plan.base_words == []
    assert plan.isolated_seeds == []
    assert plan.numbers == []


def test_explain_candidate_matches_seed_and_number() -> None:
    profile = TargetProfile(time_futebol="Flamengo", data_nascimento="05/09/2000")
    plan = build_plan(profile)
    explanation = explain_candidate("Flamengo0905@", plan)
    assert explanation is not None
    assert "time_futebol=Flamengo" in explanation
    assert "data_nascimento=05/09/2000" in explanation


def test_explain_candidate_returns_none_when_nothing_matches() -> None:
    plan = ProfilePlan(seed_field={"flamengo": "time_futebol=Flamengo"})
    assert explain_candidate("randomword123", plan) is None


def test_explain_candidate_leet_none_misses_leeted_seed() -> None:
    """Regression guard: with leet_mode='none', a leet-transformed candidate
    must NOT silently drop the seed field from the explanation -- either it
    finds the seed, or the seed's contribution must be visibly missing.

    "Fl@mengo0905" is what --leet partial (the default) actually produces
    for time_futebol=Flamengo + data_nascimento=05/09/2000. If explain_candidate
    is called without telling it leet was used, it can only match the
    literal seed text ("flamengo"), which is no longer present -- so the
    explanation is real but incomplete (date only, team silently dropped).
    """
    profile = TargetProfile(time_futebol="Flamengo", data_nascimento="05/09/2000")
    plan = build_plan(profile)
    explanation = explain_candidate("Fl@mengo0905", plan, leet_mode="none")
    assert explanation == "data_nascimento=05/09/2000"
    assert "time_futebol" not in (explanation or "")


def test_explain_candidate_leet_partial_recovers_full_attribution() -> None:
    """With leet_mode matching what generation actually used, both fields are found.

    Same candidate as above ("Fl@mengo0905"), same profile -- passing
    leet_mode="partial" (matching --leet partial, the CLI default) lets
    explain_candidate re-derive Flamengo's leet variants and find
    "fl@mengo" as a substring, recovering the team attribution that the
    leet_mode="none" call above silently lost.
    """
    profile = TargetProfile(time_futebol="Flamengo", data_nascimento="05/09/2000")
    plan = build_plan(profile)
    explanation = explain_candidate("Fl@mengo0905", plan, leet_mode="partial")
    assert explanation == "time_futebol=Flamengo + data_nascimento=05/09/2000"


def test_explain_candidate_leet_none_still_works_for_unmutated_candidates() -> None:
    """leet_mode='none' still correctly explains a candidate that never went through leet."""
    profile = TargetProfile(time_futebol="Flamengo", data_nascimento="05/09/2000")
    plan = build_plan(profile)
    explanation = explain_candidate("Flamengo0905", plan, leet_mode="none")
    assert explanation == "time_futebol=Flamengo + data_nascimento=05/09/2000"


def test_explain_candidate_returns_none_for_reversed_seed() -> None:
    """A transform outside case/leet/affix (here: ReverseMutator) is an honest
    gap -- explain_candidate must return None, not a wrong or partial guess.
    """
    profile = TargetProfile(time_futebol="Flamengo")
    plan = build_plan(profile)
    reversed_candidate = "ognemalF"  # "Flamengo" reversed
    assert explain_candidate(reversed_candidate, plan, leet_mode="partial") is None


def test_explain_candidate_prefers_longer_match() -> None:
    """A longer, more specific seed match wins over a shorter coincidental one."""
    plan = ProfilePlan(
        seed_field={
            "ana": "apelidos=Ana",
            "anabela": "nome=Anabela",
        }
    )
    explanation = explain_candidate("anabela2024", plan)
    assert explanation == "nome=Anabela"
