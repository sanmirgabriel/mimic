"""Tests for TargetProfile schema validation."""

from __future__ import annotations

import pytest

from mimic.profile.schema import TargetProfile


def test_from_dict_builds_full_profile() -> None:
    profile = TargetProfile.from_dict({
        "nome": "Pedro",
        "apelidos": ["Pedrinho", "Pepe"],
        "data_nascimento": "05/09/2000",
        "time_futebol": "Flamengo",
        "empresa": "Acme",
        "pet": "Rex",
    })
    assert profile.nome == "Pedro"
    assert profile.apelidos == ["Pedrinho", "Pepe"]
    assert profile.data_nascimento == "05/09/2000"
    assert profile.time_futebol == "Flamengo"
    assert profile.empresa == "Acme"
    assert profile.pet == "Rex"


def test_from_dict_all_fields_optional() -> None:
    profile = TargetProfile.from_dict({})
    assert profile.nome is None
    assert profile.apelidos == []
    assert profile.data_nascimento is None


def test_from_dict_partial_profile() -> None:
    profile = TargetProfile.from_dict({"time_futebol": "Flamengo"})
    assert profile.time_futebol == "Flamengo"
    assert profile.nome is None


def test_from_dict_rejects_unknown_field() -> None:
    with pytest.raises(ValueError, match="Unknown profile field"):
        TargetProfile.from_dict({"cor_favorita": "azul"})


def test_from_dict_rejects_non_list_apelidos() -> None:
    with pytest.raises(ValueError, match="apelidos"):
        TargetProfile.from_dict({"apelidos": "Pedrinho"})
