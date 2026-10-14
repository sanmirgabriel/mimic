"""Versioned aggregate-only import/export, suppression and local statistics."""

from dataclasses import replace
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

import pytest

from mimic.application import GenerationRequest, GenerationService
from mimic.application.observations import (MAX_ARTIFACT_BYTES, ObservationError,
    ObservationOptions, ObservationReport, PatternAnalysisService, load_report,
    load_report_file, report_bytes, save_report)
from mimic.cli import main


def sample(text="Caju_2026\n" * 5, **options):
    return PatternAnalysisService().analyze(io.BytesIO(text.encode()), authorized=True, **options)


def test_conservative_suppression_preserves_denominators_without_leaking_shapes():
    report = sample("Caju_2026\n" * 5 + "ACME123\n" * 4 + "unsupported🔑\n\n")
    data = report.to_dict()
    assert (report.sample_size, report.matched_count, report.unmatched_count, report.empty_count) == (10, 9, 1, 1)
    assert (report.suppressed_count, report.suppressed_structure_count) == (4, 1)
    assert data["distinct_structure_count"] == 2 and data["visible_structure_count"] == 1
    assert data["patterns"][0]["relative_frequency"] == {"numerator": 5, "denominator": 10}
    assert "ACRONYM" not in json.dumps(data["patterns"])
    assert sample("ACME123\n").patterns == ()
    assert sample("ACME123\n", min_occurrences=1).patterns[0].count == 1
    assert load_report(io.BytesIO(report_bytes(report))) == report


@pytest.mark.parametrize("options", [{"reference_year": 1899}, {"reference_year": 10000},
    {"reference_year": True}, {"reference_year": "2026"}, {"min_occurrences": 0},
    {"min_occurrences": True}, {"min_occurrences": 100001}],
    ids=["year-low", "year-high", "year-bool", "year-type", "minimum-zero", "minimum-bool", "minimum-high"])
def test_option_validation(options):
    with pytest.raises(ObservationError) as caught:
        ObservationOptions(**options)
    assert caught.value.code == "invalid_options"


def test_reference_year_is_explicit_and_recorded_without_reading_the_clock():
    fixed = sample("Caju2026\nCaju2027\n", min_occurrences=1)
    configured = sample("Caju2026\nCaju2027\n", reference_year=2026, min_occurrences=1)
    assert fixed.patterns[0].structure == "WORD + YEAR" and fixed.patterns[0].count == 2
    assert [(p.structure, p.count) for p in configured.patterns] == [("WORD + YEAR", 1), ("WORD + DIGITS", 1)]
    assert configured.to_dict()["year_interval"] == [1900, 2026]
    assert configured.to_dict()["options"]["reference_year"] == 2026
    assert "2027" not in report_bytes(configured).decode()


@pytest.mark.parametrize("word,structure", [("Caju", "WORD + SPECIAL"), ("TI", "ACRONYM + SPECIAL")],
                         ids=["word", "acronym-heuristic"])
def test_special_suffix_is_analyzed_but_not_applied(word, structure):
    report = sample((word + "!\n") * 5)
    assert report.patterns[0].structure == structure and not report.patterns[0].reusable
    assert report.to_dict()["patterns"][0]["reusable"] is False
    from mimic.core.candidate import Candidate
    request = GenerationRequest(base_candidates=(Candidate("Fresh!"),))
    reused = PatternAnalysisService().prepare_reuse(report, request, enabled=True)
    assert list(reused.iter_results()) == []
    assert any("analysis-only" in warning for warning in reused.warnings)


def test_deterministic_small_schema_and_all_grammar_rows_roundtrip():
    words = ["Caju", "ACME"]
    forms = ["", "!", "2026", "123", "_2026", "_123"]
    report = sample("".join(word + form + "\n" for word in words for form in forms), min_occurrences=1)
    assert len(report.patterns) == 12
    encoded = report_bytes(report)
    assert len(encoded) < MAX_ARTIFACT_BYTES
    assert load_report(io.BytesIO(encoded)) == report
    assert report_bytes(ObservationReport.from_dict(json.loads(encoded))) == encoded
    ids = [p.id for p in report.patterns]
    assert len(set(ids)) == 12 and all("Caju" not in value and "ACME" not in value for value in ids)


@pytest.mark.parametrize("field,value", [("schema_version", "future"), ("extractor_version", "future"),
    ("grammar_version", "future"), ("sample_size", True), ("sample_size", 5.0),
    ("sample_size", -1), ("matched_count", 1), ("unicode_version", "NeverEchoSecret"),
    ("extraction_rules", ["NeverEchoSecret"]), ("limitations", ["NeverEchoSecret"]),
    ("passwords", ["NeverEchoSecret"]), ("valid_line_count", 99), ("distinct_structure_count", 99)],
    ids=["schema", "extractor", "grammar", "bool", "float", "negative", "matched", "unicode",
         "rules", "limits-text", "unknown-plaintext", "valid-lines", "structures"])
def test_import_rejects_unknown_versions_and_free_text_without_echo(field, value):
    data = sample().to_dict(); data[field] = value
    with pytest.raises(ObservationError) as caught:
        load_report(io.BytesIO(json.dumps(data).encode()))
    assert caught.value.code == "invalid_report"
    assert "NeverEchoSecret" not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__context__ is None and caught.value.__cause__ is None


@pytest.mark.parametrize("mutation", ["duplicate-row", "unknown-shape", "raw-id", "row-frequency", "row-reuse", "row-extra", "suppression", "row-count"],
                         ids=["duplicate", "shape", "id", "frequency", "reuse", "extra", "suppression", "count"])
def test_strict_pattern_rows_and_suppression_consistency(mutation):
    data = sample().to_dict()
    row = data["patterns"][0]
    if mutation == "duplicate-row": data["patterns"].append(row.copy())
    elif mutation == "unknown-shape": row["structure"] = "NeverEchoSecret"
    elif mutation == "raw-id": row["id"] = "NeverEchoSecret"
    elif mutation == "row-frequency": row["relative_frequency"]["denominator"] = 100
    elif mutation == "row-reuse": row["reusable"] = False
    elif mutation == "row-extra": row["example"] = "NeverEchoSecret"
    elif mutation == "suppression": data["suppressed_count"] = 10
    elif mutation == "row-count": row["occurrences"] = 4
    with pytest.raises(ObservationError):
        load_report(io.BytesIO(json.dumps(data).encode()))


@pytest.mark.parametrize("raw", [b'{"schema_version":"x","schema_version":"y"}', b'NaN', b'{}', b'\xff', b'[' * 2000,
                                 b'"NeverEchoSecret"', b'{"pattern":{"id":1,"id":2}}'],
                         ids=["duplicate-field", "nan", "empty", "utf8", "nested", "literal", "nested-duplicate"])
def test_untrusted_json_is_rejected_without_reflecting_input(raw):
    with pytest.raises(ObservationError) as caught:
        load_report(io.BytesIO(raw))
    assert caught.value.code == "invalid_report"
    assert "NeverEchoSecret" not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__context__ is None


def test_artifact_byte_limit_and_unicode_version_reuse_restriction():
    stream = io.BytesIO(b"x" * (MAX_ARTIFACT_BYTES * 2))
    with pytest.raises(ObservationError) as caught:
        load_report(stream)
    assert caught.value.code == "artifact_limit" and stream.tell() == MAX_ARTIFACT_BYTES + 1
    different = replace(sample(), unicode_version="99.0.0")
    assert load_report(io.BytesIO(report_bytes(different))) == different  # read-only inspection is possible
    with pytest.raises(ObservationError):
        PatternAnalysisService().prepare_reuse(different, GenerationRequest(), enabled=True)


def test_atomic_publication_refuses_existing_paths_and_leaves_private_complete_file(tmp_path):
    destination = tmp_path / "observed.json"
    report = sample()
    save_report(report, destination)
    assert load_report_file(destination) == report
    if os.name == "posix": assert destination.stat().st_mode & 0o777 == 0o600
    before = destination.read_bytes()
    alias = tmp_path / "alias.json"; alias.symlink_to(destination)
    for path in (destination, alias, tmp_path, tmp_path / "missing" / "x.json"):
        with pytest.raises(ObservationError) as caught:
            save_report(report, path)
        assert caught.value.code == "write_failed" and caught.value.__context__ is None
    assert destination.read_bytes() == before and not list(tmp_path.glob(".mimic-patterns-*"))


@pytest.mark.parametrize("failure", ["write", "publish", "cancel"], ids=["disk-write", "atomic-link", "interrupt"])
def test_export_failures_and_cancellation_cleanup_without_raw_exception(tmp_path, monkeypatch, failure):
    original = os.fdopen
    class Broken:
        def __init__(self, stream): self.stream = stream
        def __enter__(self): return self
        def __exit__(self, *args): return self.stream.__exit__(*args)
        def write(self, payload):
            self.stream.write(payload[:20])
            if failure == "cancel": raise KeyboardInterrupt()
            raise OSError("NeverEchoSecret")
    if failure in ("write", "cancel"):
        monkeypatch.setattr(os, "fdopen", lambda fd, mode: Broken(original(fd, mode)))
    else:
        def fail(*args): raise OSError("NeverEchoSecret")
        monkeypatch.setattr(os, "link", fail)
    with pytest.raises(KeyboardInterrupt if failure == "cancel" else ObservationError) as caught:
        save_report(sample(), tmp_path / "report.json")
    assert not list(tmp_path.iterdir())
    assert "NeverEchoSecret" not in "".join(traceback.format_exception(caught.value))


def test_cli_analyze_publish_show_and_no_automatic_generation(tmp_path, capsys, monkeypatch):
    source = tmp_path / "source.txt"; source.write_bytes(b"NeverEchoSecret_2026\n" * 5)
    destination = tmp_path / "report.json"
    def forbidden(*args, **kwargs): raise AssertionError("generation was started")
    monkeypatch.setattr(GenerationService, "prepare", forbidden)
    assert main(["patterns", "analyze", "--input", str(source), "--authorized", "--reference-year", "2026", "--output", str(destination)]) == 0
    assert capsys.readouterr().out == ""
    assert main(["patterns", "show", str(destination)]) == 0
    captured = capsys.readouterr()
    assert captured.out.encode() == destination.read_bytes() and not captured.err
    assert "NeverEchoSecret" not in captured.out
    before = source.read_bytes()
    assert main(["patterns", "analyze", "--input", str(source), "--authorized", "--output", str(source)]) == 2
    assert source.read_bytes() == before and not list(tmp_path.glob(".mimic-patterns-*"))


def test_cli_invalid_artifact_no_echo_or_partial_output(tmp_path, capsys):
    source = tmp_path / "untrusted.json"; source.write_bytes(b'{"plaintext":"NeverEchoSecret"}')
    assert main(["patterns", "show", str(source)]) == 1
    captured = capsys.readouterr()
    assert "NeverEcho" not in captured.err and "invalid_report" in captured.err and not captured.out
    assert source.read_bytes() == b'{"plaintext":"NeverEchoSecret"}'


def test_binary_input_buffer_chunk_sizes_do_not_change_artifact():
    content = ("\ufeffJoão_2026\r\ncafe\u0301!17\nACME123\n" * 5).encode()
    # The repeated BOM away from the first line is an invalid record, consistently.
    class Chunked(io.RawIOBase):
        def __init__(self, size): self.inner = io.BytesIO(content); self.size = size
        def readable(self): return True
        def readinto(self, target):
            piece = self.inner.read(min(len(target), self.size)); target[:len(piece)] = piece; return len(piece)
    outputs = []
    for size in (1, 7, 64, 8192):
        with io.BufferedReader(Chunked(size)) as stream:
            outputs.append(report_bytes(PatternAnalysisService().analyze(stream, authorized=True, reference_year=2026)))
    assert len(set(outputs)) == 1


def test_artifact_hashseed_full_bytes_equivalence():
    script = '''
import io,sys
from mimic.application.observations import PatternAnalysisService,report_bytes
text=('João_2026\\n'*5+'ACME123\\n'*6+'Nome!\\n'*5)
report=PatternAnalysisService().analyze(io.BytesIO(text.encode()),authorized=True,reference_year=2026)
sys.stdout.buffer.write(report_bytes(report))
'''
    values = [subprocess.check_output([sys.executable, "-B", "-c", script], env={**os.environ, "PYTHONHASHSEED": seed})
              for seed in ("1", "42", "777")]
    assert values[0] == values[1] == values[2]
