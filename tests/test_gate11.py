"""Focused pre-commit contract audit; no Block 2 behavior changes."""

import pytest

from mimic.core.candidate import Candidate, Origin, Transformation
from mimic.core.generator import Generator
from mimic.mutators.base import Mutator, StructuredMutator
from mimic.mutators.case import CaseMutator
from mimic.mutators.combine import CombineMutator
from mimic.profile.loader import ProfilePlan, build_plan
from mimic.profile.schema import TargetProfile


def test_profile_plan_legacy_mutable_api_and_snapshot_divergence():
    # Characterization, not a desirable synchronization contract.
    names = ["Pedro"]
    plan = ProfilePlan(names, [], ["12"], {"pedro": "nome=Pedro"}, {})
    names.append("Silva")
    assert plan.base_words == ["Pedro", "Silva"]
    assert plan.base_candidates == []
    plan = build_plan(TargetProfile(nome="Pedro", data_nascimento="05/09"))
    plan.base_words.append("Silva")
    assert [c.value for c in plan.base_candidates] == ["Pedro"]
    plan.number_candidates.clear()
    assert plan.numbers == ["0509", "0905", "509", "905"]
    assert plan.number_field["0905"] == "data_nascimento=05/09"


def test_dispatch_legacy_only_records_real_call_and_propagates_exception():
    calls = []

    class Legacy(Mutator):
        def mutate(self, word):
            calls.append(word)
            yield word + "!"
            raise RuntimeError("legacy failure")

    stream = Legacy().mutate_candidate(Candidate("x"))
    result = next(stream)
    assert calls == ["x"]
    assert result.value == "x!"
    assert dict(result.transformations[0].params)["input"] == "x"
    assert dict(result.transformations[0].params)["output"] == "x!"
    with pytest.raises(RuntimeError, match="legacy failure"):
        next(stream)


def test_dispatch_structured_only_uses_explicit_structured_base():
    class WrongBase(Mutator):
        def mutate_candidate(self, candidate):
            yield candidate

    with pytest.raises(TypeError, match="abstract"):
        WrongBase()

    class Structured(StructuredMutator):
        def mutate_candidate(self, candidate):
            yield candidate.derive(candidate.value + "!", Transformation("custom"))
            raise RuntimeError("structured failure")

    stream = Structured().mutate("x")
    assert next(stream) == "x!"
    with pytest.raises(RuntimeError, match="structured failure"):
        next(stream)


def test_dispatch_both_methods_generator_selects_structured_method():
    class Both(Mutator):
        def mutate(self, word):
            yield "text"

        def mutate_candidate(self, candidate):
            yield candidate.derive("structured", Transformation("custom"))

    assert list(Both().mutate("x")) == ["text"]
    gen = Generator(["x"], [Both()])
    assert list(gen.generate()) == ["structured"]
    assert next(gen.generate_candidates()).transformations[0].kind == "custom"


@pytest.mark.parametrize("base", [Mutator, StructuredMutator])
def test_dispatch_neither_method_is_rejected_at_construction(base):
    class Neither(base):
        pass

    with pytest.raises(TypeError, match="abstract"):
        Neither()


def test_internal_mutators_share_one_text_projection():
    from mimic.mutators.affix import AffixMutator
    from mimic.mutators.date import DateMutator
    from mimic.mutators.leet import LeetMutator
    from mimic.mutators.reverse import ReverseMutator

    for cls in (AffixMutator, CaseMutator, CombineMutator, DateMutator, LeetMutator, ReverseMutator):
        assert cls.mutate is StructuredMutator.mutate
        assert "mutate_candidate" in cls.__dict__


def test_combine_text_introspection_is_detached_from_causal_operands():
    plan = build_plan(TargetProfile(nome="Pedro", apelidos=["Silva"]))
    m = CombineMutator(plan.base_candidates, "")
    assert m.all_names == ["pedro", "silva"]
    m.all_names.append("intruder")
    assert m.all_names == ["pedro", "silva"]
    with pytest.raises(AttributeError):
        m.all_names = ["intruder"]
    result = next(m.mutate_candidate(plan.base_candidates[0]))
    assert result.origins == (
        Origin("profile", "nome", "Pedro"), Origin("profile", "apelidos", "Silva"),
    )


@pytest.mark.parametrize("construct", [
    lambda: Origin("profile", "nome", []),
    lambda: Origin([], "nome", "Pedro"),
    lambda: Transformation([], ()),
    lambda: Transformation("case", (("mode", []),)),
    lambda: Candidate([], (), ()),
    lambda: Candidate("x", ({"source": "profile"},), ()),
    lambda: Candidate("x", (), (["reverse"],)),
])
def test_models_reject_hidden_mutable_payloads(construct):
    with pytest.raises(TypeError):
        construct()


@pytest.mark.parametrize("accepted", [True, False])
def test_dedup_before_policy_never_replaces_first_derivation(accepted):
    first = Candidate("Pedro", (Origin("profile", "nome", "Pedro"),))
    second = Candidate("Pedro", (Origin("profile", "apelidos", "Pedro"),))

    class RecordingPolicy:
        def __init__(self):
            self.calls = []

        def accepts(self, value):
            self.calls.append(value)
            return accepted

    policy = RecordingPolicy()
    gen = Generator([first, second], [], policy=policy)
    assert list(gen.generate_candidates()) == ([first] if accepted else [])
    assert policy.calls == ["Pedro"]
    policy.calls.clear()
    assert list(gen.generate()) == (["Pedro"] if accepted else [])
    assert policy.calls == ["Pedro"]
