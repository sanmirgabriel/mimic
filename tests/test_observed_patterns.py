"""Synthetic, authorized observations: privacy, bounded parsing and reuse."""

from dataclasses import FrozenInstanceError, asdict, replace
from concurrent.futures import ThreadPoolExecutor
import io
import json
import logging
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tracemalloc

import pytest

from mimic.application import (GenerationLimits, GenerationRequest, GenerationService,
                               MutationOptions, PolicyOptions, RankingOptions)
from mimic.application.observations import (ObservationError, ObservationLimits,
    ObservedPattern, PatternAnalysisService)
from mimic.application.errors import ApplicationError
from mimic.core.candidate import Candidate, Origin
from mimic.ranking.scoring import score_candidate


def analyze(data, **kwargs):
    if isinstance(data, str):
        data = data.encode("utf-8")
    kwargs.setdefault("min_occurrences", 1)
    return PatternAnalysisService().analyze(io.BytesIO(data), authorized=True, **kwargs)


@pytest.mark.parametrize("value,shape", [
    ("João", "WORD"), ("A", "WORD"), ("Equipeabcdefghijkl", "WORD"),
    ("ACME", "ACRONYM"), ("ÁÇ", "ACRONYM"), ("a\u0301", "WORD"),
    ("ÁC\u0301", "ACRONYM"), ("ABCDEFGHIJKLM", "WORD"),
    ("João2026", "WORD + YEAR"), ("João1900", "WORD + YEAR"),
    ("João2099", "WORD + YEAR"), ("João1899", "WORD + DIGITS"),
    ("João2100", "WORD + DIGITS"), ("João0001", "WORD + DIGITS"),
    ("João123", "WORD + DIGITS"), ("João12026", "WORD + DIGITS"),
    ("João_2026", "WORD + SEPARATOR + YEAR"),
    ("cafe\u0301!17", "WORD + SEPARATOR + DIGITS"),
    ("ACME2026", "ACRONYM + YEAR"), ("TI123", "ACRONYM + DIGITS"),
    ("ÁREA-2025", "ACRONYM + SEPARATOR + YEAR"),
    ("ACME.01", "ACRONYM + SEPARATOR + DIGITS"),
], ids=["word", "one-letter", "mixed-long", "acronym", "accented-acronym", "nfd",
        "nfd-acronym", "long-uppercase", "year", "year-min", "year-max", "pre-year",
        "post-year", "zeroes", "digits", "long-digits", "separator-year", "nfd-digits",
        "acronym-year", "acronym-digits", "acronym-separator-year", "acronym-separator-digits"])
def test_exclusive_grammar_and_ambiguity(value, shape):
    report = analyze(value)
    assert report.patterns == (ObservedPattern(shape, 1),)
    assert report.sample_size == report.matched_count == 1
    assert report.unmatched_count == 0


@pytest.mark.parametrize("value", ["123456", "2026João", "João2026!", "João__2026",
    "João$2026", "João-Equipe2026", " João2026", "João2026 ", "   ", "🔑senha",
    "\u0301nome", "senha١٢٣", "senha１２３", "senha²", "2026"],
    ids=["digits-only", "prefix", "suffix-separator", "double-separator", "unknown-separator",
         "two-words", "leading-space", "trailing-space", "spaces-only", "emoji", "leading-mark",
         "arabic-digits", "fullwidth-digits", "superscript", "year-only"])
def test_unsupported_shapes_are_reported_without_invented_patterns(value):
    report = analyze(value)
    assert report.sample_size == report.unmatched_count == 1
    assert not report.patterns
    assert report.to_dict()["unsupported_count"] == 1


@pytest.mark.parametrize("separator", list("@!#_.-"), ids=["at", "bang", "hash", "underscore", "dot", "dash"])
def test_separator_literals_are_not_retained(separator):
    report = analyze("Caju" + separator + "2026")
    assert report.patterns == (ObservedPattern("WORD + SEPARATOR + YEAR", 1),)
    assert "Caju" not in repr(report) and "2026" not in repr(report)


def test_counts_denominators_duplicates_bom_and_exact_records():
    report = analyze(b"\xef\xbb\xbfCaju_2026\r\nCaju_2026\nACME123\n\n \ninvalid\xff\nNul\x00x\n")
    assert (report.line_count, report.sample_size, report.empty_count,
            report.invalid_utf8_count, report.invalid_unicode_count, report.unmatched_count) == (7, 4, 1, 1, 1, 1)
    assert report.matched_count == 3
    assert dict((p.structure, p.count) for p in report.patterns) == {
        "WORD + SEPARATOR + YEAR": 2, "ACRONYM + DIGITS": 1}
    assert report.to_dict()["duplicate_policy"] == "count-every-observation"
    assert analyze("").line_count == 0
    assert analyze("\n").empty_count == 1
    assert analyze("\ufeff").empty_count == 1


@pytest.mark.parametrize("value", ["x\x00y", "x\ry", "x\ty", "x\x7fy", "x\u0085y",
    "x\u2028y", "x\u2029y", "x\u200by", "x\u202ey", "x\ufeffy"],
    ids=["nul", "cr", "tab", "del", "c1", "line-separator", "paragraph-separator", "zero-width", "bidi", "embedded-bom"])
def test_invalid_unicode_has_aggregate_diagnostics(value):
    report = analyze(value)
    assert report.invalid_unicode_count == 1 and report.sample_size == 0
    assert not report.patterns


@pytest.mark.parametrize("data", [b"\xff", b"\xc0\xaf", b"\xed\xa0\x80", b"\xe2\x82"],
                         ids=["bad-byte", "overlong-encoding", "surrogate", "incomplete"])
def test_invalid_utf8_never_escapes_as_decode_exception(data):
    report = analyze(data + b"\nCaju123\n")
    assert report.invalid_utf8_count == 1
    assert report.patterns == (ObservedPattern("WORD + DIGITS", 1),)


@pytest.mark.parametrize("option,value", [
    ("max_bytes", 0), ("max_bytes", True), ("max_bytes", 64 * 1024 * 1024 + 1),
    ("max_lines", -1), ("max_lines", "2"), ("max_lines", 100001),
    ("max_line_bytes", 0), ("max_line_bytes", 1.0), ("max_line_bytes", 4097),
], ids=["bytes-zero", "bytes-bool", "bytes-ceiling", "lines-negative", "lines-type",
        "lines-ceiling", "record-zero", "record-float", "record-ceiling"])
def test_limits_reject_invalid_types_and_unbounded_configuration(option, value):
    with pytest.raises(ObservationError, match="documented ceilings") as caught:
        ObservationLimits(**{option: value})
    assert caught.value.code == "invalid_limits"


@pytest.mark.parametrize("label", ["", "Secret/Password2026", "../file", "a" * 65, "área", "x\n", None],
                         ids=["empty", "sensitive-path", "traversal", "length", "non-ascii", "control", "type"])
def test_invalid_source_labels_are_not_echoed(label):
    with pytest.raises(ObservationError) as caught:
        analyze("Caju123", source_label=label)
    assert caught.value.code == "invalid_source_label"
    if label and len(label) > 1:
        assert label not in str(caught.value)


def test_authorization_and_options_are_checked_before_any_read(tmp_path, monkeypatch):
    class NeverRead:
        def readline(self, size):
            raise AssertionError("source was read")
    service = PatternAnalysisService()
    for authorized in (False, None, 1, "true"):
        with pytest.raises(ObservationError) as caught:
            service.analyze(NeverRead(), authorized=authorized)
        assert caught.value.code == "authorization_required"
    def forbidden(*args, **kwargs):
        raise AssertionError("file was consulted")
    monkeypatch.setattr(os, "lstat", forbidden)
    with pytest.raises(ObservationError) as caught:
        service.analyze_file(tmp_path / "secret", authorized=False)
    assert caught.value.code == "authorization_required"
    with pytest.raises(ObservationError) as caught:
        service.analyze(NeverRead(), authorized=True, limits={})
    assert caught.value.code == "invalid_limits"


@pytest.mark.parametrize("data,limits,code,line", [
    (b"abc\n", ObservationLimits(max_bytes=3), "byte_limit", 1),
    (b"a\nb", ObservationLimits(max_lines=1), "line_limit", 2),
    (b"abcd", ObservationLimits(max_line_bytes=3), "line_too_long", 1),
    (b"abc\r\nlonger", ObservationLimits(max_line_bytes=3), "line_too_long", 2),
    ("áá".encode(), ObservationLimits(max_line_bytes=3), "line_too_long", 1),
], ids=["bytes", "lines", "record", "later-record", "utf8-bytes"])
def test_limit_failures_return_no_partial_report(data, limits, code, line):
    with pytest.raises(ObservationError) as caught:
        analyze(data, limits=limits)
    assert (caught.value.code, caught.value.line_number) == (code, line)
    assert caught.value.__context__ is None and caught.value.__cause__ is None


@pytest.mark.parametrize("data", [b"abc", b"abc\n", b"abc\r\n"], ids=["eof", "lf", "crlf"])
def test_exact_limits_accept_eof_and_line_terminators(data):
    report = analyze(data, limits=ObservationLimits(max_bytes=len(data), max_lines=1, max_line_bytes=3))
    assert report.bytes_read == len(data) and report.line_count == 1


def test_huge_single_line_is_read_only_in_a_bounded_chunk():
    class Recording(io.BytesIO):
        def readline(self, size):
            self.last_size = size
            return super().readline(size)
    stream = Recording(b"x" * (16 * 1024 * 1024))
    with pytest.raises(ObservationError) as caught:
        PatternAnalysisService().analyze(stream, authorized=True)
    assert caught.value.code == "line_too_long"
    assert stream.tell() == stream.last_size == 1027


def test_streaming_memory_does_not_grow_with_repeated_observations():
    class Repeated:
        remaining = 100_000
        def readline(self, size):
            assert size > 0
            if not self.remaining:
                return b""
            self.remaining -= 1
            return b"Caju2026\n"[:size]
    tracemalloc.start()
    try:
        report = PatternAnalysisService().analyze(Repeated(), authorized=True)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert report.sample_size == report.matched_count == 100_000
    assert report.patterns == (ObservedPattern("WORD + YEAR", 100_000),)
    assert peak < 2 * 1024 * 1024


def test_read_errors_have_no_foreign_exception_context_or_secret():
    class Broken:
        def readline(self, size):
            raise RuntimeError("NeverEchoSecret2026 /sensitive/source")
    for stream in (Broken(), io.StringIO("NeverEchoSecret2026"), None):
        with pytest.raises(ObservationError) as caught:
            PatternAnalysisService().analyze(stream, authorized=True)
        assert caught.value.code == "read_failed"
        assert "NeverEcho" not in repr(caught.value)
        assert caught.value.__context__ is None and caught.value.__cause__ is None


def test_local_regular_file_and_symlink_fifo_directory_rejection(tmp_path):
    service = PatternAnalysisService()
    path = tmp_path / "observations.txt"
    path.write_bytes(b"Caju2026\n")
    assert service.analyze_file(path, authorized=True, min_occurrences=1) == analyze(path.read_bytes())
    symlink = tmp_path / "symlink"; symlink.symlink_to(path)
    invalid = [tmp_path, symlink]
    if hasattr(os, "mkfifo"):
        fifo = tmp_path / "fifo"; os.mkfifo(fifo); invalid.append(fifo)
    for candidate in invalid:
        with pytest.raises(ObservationError) as caught:
            service.analyze_file(candidate, authorized=True)
        assert caught.value.code == "not_regular_file"
    with pytest.raises(ObservationError) as caught:
        service.analyze_file(tmp_path / "NeverEchoSecret2026", authorized=True)
    assert caught.value.code == "read_failed"
    assert "NeverEcho" not in str(caught.value) and caught.value.__context__ is None
    assert path.read_bytes() == b"Caju2026\n"


def test_analysis_cannot_log_write_connect_or_modify_job_request(tmp_path, monkeypatch, caplog):
    original = GenerationRequest().to_dict()
    def forbidden(*args, **kwargs):
        raise AssertionError("side effect attempted")
    monkeypatch.setattr(Path, "write_text", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(GenerationService, "prepare", forbidden)
    with caplog.at_level(logging.DEBUG):
        report = analyze("NeverEchoSecret2026\nOtherSecret!9876\n")
    public = json.dumps(report.to_dict()) + repr(report) + caplog.text
    for secret in ("NeverEchoSecret", "OtherSecret", "9876", "2026"):
        assert secret not in public
    assert GenerationRequest().to_dict() == original
    assert not list(tmp_path.iterdir())


def test_report_immutability_deterministic_order_and_concurrent_service():
    values = "ACME123\nCaju_2026\nÁREA\nJoão\nEquipe123\n"
    expected = analyze(values)
    assert analyze("\n".join(reversed(values.strip().splitlines())) + "\n") == expected
    with ThreadPoolExecutor(4) as executor:
        reports = list(executor.map(lambda _: analyze(values), range(8)))
    assert all(report == expected for report in reports)
    with pytest.raises(FrozenInstanceError):
        expected.sample_size = 0
    rendered = expected.to_dict(); rendered["patterns"][0]["occurrences"] = 999
    assert expected.patterns[0].count == 1


def test_report_hashseed_equivalence():
    script = '''
import io,json
from mimic.application.observations import PatternAnalysisService
data='João_2026\\nACME123\\ncafe\\u0301!17\\nJoão_2026\\nunsupported🔑\\n'
report=PatternAnalysisService().analyze(io.BytesIO(data.encode()),authorized=True,source_label='synthetic',min_occurrences=1)
print(json.dumps(report.to_dict(),sort_keys=True,ensure_ascii=True))
'''
    outputs = [subprocess.check_output([sys.executable, "-B", "-c", script],
        env={**os.environ, "PYTHONHASHSEED": seed}) for seed in ("1", "42", "777")]
    assert outputs[0] == outputs[1] == outputs[2]


def request(ranking=None, policy=None):
    return GenerationRequest(
        base_candidates=(Candidate("Equipe", (Origin("manual", "name", "Equipe"),)),),
        number_candidates=(Candidate("2025", (Origin("manual", "year", "2025"),)),),
        mutations=MutationOptions("none", False, "_"),
        limits=GenerationLimits(100), ranking=ranking or RankingOptions(),
        policy=policy or PolicyOptions(),
    )


def test_reuse_is_opt_in_delegates_once_and_preserves_real_provenance_and_score():
    report = analyze("NeverReuseObservedLiteral_2026\nUnsupported🔑\n")
    configured = request(RankingOptions(True, 20))
    before = configured.to_dict()
    service = PatternAnalysisService()
    with pytest.raises(ObservationError) as caught:
        service.prepare_reuse(report, configured)
    assert caught.value.code == "reuse_disabled"
    calls = []
    class Spy(GenerationService):
        def prepare(self, value):
            calls.append(value)
            return super().prepare(value)
    reused = service.prepare_reuse(report, configured, enabled=True, generation_service=Spy())
    results = list(reused.iter_results())
    assert calls == [configured] and configured.to_dict() == before
    assert [r.candidate.value for r in results] == ["Equipe_2025", "equipe_2025"]
    # Uppercase spelling is classified separately as ACRONYM and filtered out.
    baseline = list(GenerationService().prepare(configured).iter_results())
    assert results == [r for r in baseline if r.candidate.value in ("Equipe_2025", "equipe_2025")]
    assert all(r.score == score_candidate(r.candidate, None) and r.score.version == "score-v1" for r in results)
    assert all(o.source == "manual" for r in results for o in r.candidate.origins)
    assert "NeverReuseObservedLiteral" not in json.dumps([asdict(r) for r in results])
    assert report.unmatched_count == 1 and any("unsupported" in w for w in reused.warnings)
    with pytest.raises(ApplicationError):
        list(reused.iter_results())


def test_reuse_respects_policy_caps_and_original_rank_positions():
    report = analyze("Caju_2026\n")
    configured = request(RankingOptions(True, 1))
    reused = PatternAnalysisService().prepare_reuse(report, configured, enabled=True)
    assert list(reused.iter_results()) == []  # Top-1 is not of the learned shape.
    assert any("below the budget" in w for w in reused.warnings)
    policy_filtered = PatternAnalysisService().prepare_reuse(report, request(policy=PolicyOptions(max_len=3)), enabled=True)
    assert list(policy_filtered.iter_results()) == []
    capped = PatternAnalysisService().prepare_reuse(report, replace(request(), limits=GenerationLimits(1)), enabled=True)
    assert list(capped.iter_results()) == []
    unsupported = PatternAnalysisService().prepare_reuse(analyze("🔑OnlyUnsupported"), request(), enabled=True)
    assert list(unsupported.iter_results()) == []


@pytest.mark.parametrize("change", [
    {"grammar_version": "future"}, {"sample_size": -1}, {"sample_size": 999},
    {"patterns": (ObservedPattern("invented", 1),)},
    {"patterns": (ObservedPattern("WORD", 0),)},
    {"patterns": (ObservedPattern("WORD + YEAR", 1), ObservedPattern("WORD + YEAR", 1))},
    {"patterns": []}, {"line_count": True},
], ids=["version", "negative", "inconsistent", "unknown-shape", "zero", "duplicate", "mutable", "bool"])
def test_reuse_rejects_forged_or_inconsistent_aggregate_reports(change):
    with pytest.raises(ObservationError) as caught:
        PatternAnalysisService().prepare_reuse(replace(analyze("Caju2026"), **change), request(), enabled=True)
    assert caught.value.code == "invalid_report"


def test_independent_synthetic_holdout_structure_coverage():
    training = analyze("Caju_2026\nACME123\nEquipe2025\n")
    holdout = analyze("João_2024\nÁREA17\nEmpresa2023\nTeam!2022\nTI99\nNome2021\nUnsupported🔑\n123456\n")
    learned = {p.structure for p in training.patterns}
    covered = sum(p.count for p in holdout.patterns if p.structure in learned)
    assert (holdout.sample_size, holdout.matched_count, covered) == (8, 6, 6)
    # Structural coverage only: no recovery/success or population-frequency claim.
