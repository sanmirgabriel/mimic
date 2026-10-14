"""Independent Gate 11 checks; every observation and artifact is synthetic."""

from dataclasses import asdict
import io
import json
import logging
import os
from pathlib import Path
import traceback

from fastapi.testclient import TestClient
import pytest

from mimic.api import create_app
from mimic.application import (GenerationLimits, GenerationRequest, GenerationService,
    MutationOptions, RankingOptions)
from mimic.application.observations import (ObservationError, PatternAnalysisService,
    load_report, load_report_file, report_bytes, save_report)
from mimic.cli import main
from mimic.core.candidate import Candidate, Origin


def report(text="GateSyntheticUnshared_2026\n" * 5, **options):
    return PatternAnalysisService().analyze(io.BytesIO(text.encode()), authorized=True,
                                          reference_year=2026, **options)


def request(budget=None):
    return GenerationRequest(base_candidates=(Candidate("Fresh", (Origin("manual", "name", "Fresh"),)),),
        number_candidates=(Candidate("2026", (Origin("manual", "year", "2026"),)),),
        mutations=MutationOptions("none", False, "_"), limits=GenerationLimits(100),
        ranking=RankingOptions(True, budget) if budget is not None else RankingOptions())


def test_directory_substitution_during_web_read_cannot_escape_data_root(tmp_path, monkeypatch):
    """Swap the parent at the actual selected-file open, after listing/validation."""
    root = tmp_path / "workspace"; directory = root / "patterns"; directory.mkdir(parents=True)
    outside = tmp_path / "outside-private"; outside.mkdir()
    save_report(report(source_label="inside-evidence"), directory / "review.json")
    save_report(report(source_label="outside-private-evidence"), outside / "review.json")
    original = os.open
    reads = 0
    def swap_on_selected_read(path, flags, *args, **kwargs):
        nonlocal reads
        if Path(path).name == "review.json":
            reads += 1
            if reads == 2:
                directory.rename(root / "original-patterns")
                directory.symlink_to(outside)
        return original(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, "open", swap_on_selected_read)
    with TestClient(create_app(data_dir=root)) as client:
        response = client.get("/patterns/review")
    assert reads == 2
    assert "outside-private-evidence" not in response.text
    assert response.status_code in (200, 422)
    if response.status_code == 200:
        assert "inside-evidence" in response.text


def test_web_directory_permission_failure_is_controlled_without_path_log(tmp_path, monkeypatch, caplog):
    original = os.open
    original_is_symlink = Path.is_symlink
    marker = "GateSyntheticUnshared-private-path"
    def denied(path, *args, **kwargs):
        if Path(path).name == "patterns":
            raise PermissionError(marker)
        return original(path, *args, **kwargs)
    def denied_path(path):
        if path.name == "patterns":
            raise PermissionError(marker)
        return original_is_symlink(path)
    monkeypatch.setattr(os, "open", denied)
    # Existing validation performs this path lookup before entering its handler.
    monkeypatch.setattr(Path, "is_symlink", denied_path)
    with caplog.at_level(logging.DEBUG), TestClient(create_app(data_dir=tmp_path), raise_server_exceptions=False) as client:
        page = client.get("/patterns")
    assert page.status_code == 422
    assert marker not in page.text + caplog.text


@pytest.mark.parametrize("count", [0, 1, 4, 5, 6], ids=["zero", "one", "four", "five", "six"])
def test_suppression_is_identical_across_analyze_show_web_and_reuse(count, tmp_path, capsys):
    sentinel = "GateSyntheticUnshared_2026"
    source = tmp_path / "source.txt"; source.write_bytes((sentinel + "\n").encode() * count)
    directory = tmp_path / "patterns"; directory.mkdir()
    artifact = directory / "sample.json"
    assert main(["patterns", "analyze", "--input", str(source), "--authorized", "--reference-year", "2026"]) == 0
    stdout = capsys.readouterr().out
    data = json.loads(stdout)
    assert data["sample_size"] == data["matched_count"] == count
    assert data["visible_structure_count"] == (1 if count >= 5 else 0)
    assert data["suppressed_count"] == (count if count < 5 else 0)
    assert data["patterns"] == ([] if count < 5 else [{"id": "observed-pattern.word-separator-year.v1",
        "structure": "WORD + SEPARATOR + YEAR", "occurrences": count,
        "relative_frequency": {"numerator": count, "denominator": count}, "reusable": True}])
    artifact.write_bytes(stdout.encode())
    assert main(["patterns", "show", str(artifact)]) == 0
    shown = capsys.readouterr().out
    assert shown == stdout and sentinel not in shown
    aggregate = load_report_file(artifact)
    reused = PatternAnalysisService().prepare_reuse(aggregate, request(), enabled=True)
    results = list(reused.iter_results())
    assert bool(results) is (count >= 5)
    assert sentinel not in json.dumps([asdict(value) for value in results])
    with TestClient(create_app(data_dir=tmp_path)) as client:
        page = client.get("/patterns/sample")
        assert page.status_code == 200 and sentinel not in page.text
        assert ("WORD + SEPARATOR + YEAR" in page.text) is (count >= 5)
        assert client.get("/api/jobs").json() == []
    assert not (tmp_path / "uploads").exists()


@pytest.mark.parametrize("change", ["replace", "remove", "in-place"], ids=["replaced", "removed", "modified"])
def test_loaded_report_is_a_snapshot_independent_of_mutable_artifact(change, tmp_path):
    path = tmp_path / "aggregate.json"
    save_report(report(), path)
    loaded = load_report_file(path)
    encoded = report_bytes(loaded)
    configured = request()
    baseline = list(PatternAnalysisService().prepare_reuse(loaded, configured, enabled=True).iter_results())
    prepared = PatternAnalysisService().prepare_reuse(loaded, configured, enabled=True)
    if change == "replace":
        path.unlink(); save_report(report("ACME123\n" * 5), path)
    elif change == "remove": path.unlink()
    else: path.write_bytes(b"{malformed synthetic JSON}")
    assert list(prepared.iter_results()) == baseline
    assert report_bytes(loaded) == encoded
    assert "observed" not in json.dumps(configured.to_dict())


@pytest.mark.parametrize("budget", [None, 1, 5, 20], ids=["exhaustive", "top-one", "top-five", "top-twenty"])
def test_post_topk_filter_preserves_existing_results_and_rank_gaps(budget):
    configured = request(budget)
    direct = list(GenerationService().prepare(configured).iter_results())
    expected = [value for value in direct if value.candidate.value in ("Fresh_2026", "fresh_2026")]
    reused = PatternAnalysisService().prepare_reuse(report(), configured, enabled=True)
    assert list(reused.iter_results()) == expected
    assert all(value.rank is None for value in expected) if budget is None else all(value.score.version == "score-v1" for value in expected)


def test_midstream_sensitive_read_failure_and_interrupt_close_file_without_partial_report(tmp_path, monkeypatch):
    sentinel = "GateSyntheticUnshared_2026"
    class Broken(io.BytesIO):
        reads = 0
        def readline(self, size):
            self.reads += 1
            if self.reads == 2: raise OSError(sentinel)
            return super().readline(size)
    stream = Broken((sentinel + "\n").encode() * 5)
    with pytest.raises(ObservationError) as caught:
        PatternAnalysisService().analyze(stream, authorized=True)
    assert caught.value.code == "read_failed"
    assert sentinel not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__context__ is None
    assert not stream.closed  # Caller-owned stream remains caller-owned.
    path = tmp_path / "sensitive.txt"; path.write_bytes((sentinel + "\n").encode())
    original = os.fdopen
    owned = []
    class Interrupted:
        def __init__(self, actual): self.actual = actual
        def __enter__(self): return self
        def __exit__(self, *args): return self.actual.__exit__(*args)
        def readline(self, size): raise KeyboardInterrupt()
    def interrupted(fd, mode):
        value = original(fd, mode); owned.append(value); return Interrupted(value)
    monkeypatch.setattr(os, "fdopen", interrupted)
    with pytest.raises(KeyboardInterrupt):
        PatternAnalysisService().analyze_file(path, authorized=True)
    assert owned[0].closed and list(tmp_path.iterdir()) == [path]


def test_publication_fsync_and_concurrent_destination_failure_preserve_operator_data(tmp_path, monkeypatch):
    target = tmp_path / "aggregate.json"
    def fail_sync(fd): raise OSError("GateSyntheticUnshared")
    monkeypatch.setattr(os, "fsync", fail_sync)
    with pytest.raises(ObservationError) as caught: save_report(report(), target)
    assert caught.value.code == "write_failed" and not list(tmp_path.iterdir())
    monkeypatch.undo()
    def concurrent(source, destination):
        Path(destination).write_bytes(b"operator content")
        raise FileExistsError("GateSyntheticUnshared")
    monkeypatch.setattr(os, "link", concurrent)
    with pytest.raises(ObservationError) as caught: save_report(report(), target)
    assert target.read_bytes() == b"operator content" and list(tmp_path.iterdir()) == [target]
    assert caught.value.__context__ is None


@pytest.mark.parametrize("trailing", [b"GateSyntheticUnshared", b"x" * 20000], ids=["trailing-data", "oversize"])
def test_short_artifact_reads_cannot_hide_invalid_or_oversized_tail(trailing):
    prefix = report_bytes(report())
    class Partial(io.BytesIO):
        def read(self, size):
            return super().read(min(size, len(prefix)))
    with pytest.raises(ObservationError) as caught:
        load_report(Partial(prefix + trailing))
    assert caught.value.code in ("invalid_report", "artifact_limit")


@pytest.mark.parametrize("size", [1, 7, 97], ids=["one-byte", "seven-bytes", "small-chunks"])
def test_valid_artifact_short_reads_have_identical_canonical_bytes(size):
    expected = report_bytes(report())
    class Partial(io.BytesIO):
        def read(self, limit): return super().read(min(size, limit))
    assert report_bytes(load_report(Partial(expected))) == expected


@pytest.mark.parametrize("shape,positive,negative", [
    ("WORD", "Olá", "TI"), ("WORD + SPECIAL", "Olá!", "Olá!!"),
    ("WORD + YEAR", "Olá2026", "Olá7777"), ("WORD + DIGITS", "Olá7777", "Olá2026"),
    ("WORD + SEPARATOR + YEAR", "Olá@2026", "Olá@@2026"),
    ("WORD + SEPARATOR + DIGITS", "Olá-7777", "Olá-2026"),
    ("ACRONYM", "TI", "Ti"), ("ACRONYM + SPECIAL", "TI!", "Ti!"),
    ("ACRONYM + YEAR", "TI2026", "Ti2026"), ("ACRONYM + DIGITS", "TI7777", "TI2026"),
    ("ACRONYM + SEPARATOR + YEAR", "TI_2026", "Ti_2026"),
    ("ACRONYM + SEPARATOR + DIGITS", "TI_7777", "TI_2026"),
], ids=["word", "word-special", "word-year", "word-digits", "word-separator-year", "word-separator-digits",
        "acronym", "acronym-special", "acronym-year", "acronym-digits", "acronym-separator-year", "acronym-separator-digits"])
def test_twelve_pattern_positive_negative_matrix_has_exclusive_classification(shape, positive, negative):
    accepted = report(positive, min_occurrences=1)
    rejected = report(negative, min_occurrences=1)
    assert [(p.structure, p.count) for p in accepted.patterns] == [(shape, 1)]
    assert all(p.structure != shape for p in rejected.patterns)
    assert accepted.matched_count == accepted.sample_size == 1
    assert rejected.matched_count + rejected.unmatched_count == 1


def test_frequency_denominator_and_all_line_partitions_are_mathematically_consistent():
    payload = "Olá2026\nOlá2026\nTI_7777\nTI_7777\nTI_7777\nunknown🔑\n\n".encode() + b"\xff\nNul\x00\n"
    result = PatternAnalysisService().analyze(io.BytesIO(payload), authorized=True,
                                            reference_year=2026, min_occurrences=1)
    assert (result.line_count, result.sample_size, result.matched_count, result.unmatched_count) == (9, 6, 5, 1)
    assert (result.empty_count, result.invalid_utf8_count, result.invalid_unicode_count) == (1, 1, 1)
    assert result.bytes_read == len(payload)
    rows = result.to_dict()["patterns"]
    assert [row["relative_frequency"] for row in rows] == [
        {"numerator": 2, "denominator": 6}, {"numerator": 3, "denominator": 6}]
    suppressed = PatternAnalysisService().analyze(io.BytesIO(payload), authorized=True, reference_year=2026)
    assert not suppressed.patterns and suppressed.suppressed_count == 5 and suppressed.suppressed_structure_count == 2


def test_suppression_does_not_promise_protection_from_complementary_totals():
    # Residual risk: eleven visible families plus one hidden family reveal the
    # remaining shape when the fixed grammar and complementary totals are known.
    from mimic.application.observations import SHAPES
    words = ("Olá", "TI")
    suffixes = ("", "!", "2026", "7777", "_2026", "_7777")
    examples = [word + suffix for word in words for suffix in suffixes]
    result = report("".join((example + "\n") * (1 if i == 0 else 5) for i, example in enumerate(examples)))
    visible = {p.structure for p in result.patterns}
    assert set(SHAPES) - visible == {"WORD"}
    assert (result.suppressed_count, result.suppressed_structure_count, result.matched_count) == (1, 1, 56)
    assert all(p.structure != "WORD" for p in result.patterns)


def test_reordering_and_terminal_newline_have_documented_metadata_semantics():
    records = ["Olá_2026", "TI7777", "unknown🔑", "Olá_2026"]
    first = report("\n".join(records), min_occurrences=1)
    reordered = report("\n".join(reversed(records)), min_occurrences=1)
    assert report_bytes(first) == report_bytes(reordered)
    terminated = report("\n".join(records) + "\n", min_occurrences=1)
    a, b = first.to_dict(), terminated.to_dict()
    assert b.pop("bytes_read") == a.pop("bytes_read") + 1
    assert a == b  # Physical-byte metadata intentionally distinguishes the files.


def test_unsupported_platform_viewer_fails_closed_without_file_reads(tmp_path, monkeypatch):
    import mimic.web.patterns as patterns
    monkeypatch.setattr(os, "supports_dir_fd", set())
    with pytest.raises(ObservationError) as caught:
        patterns.list_artifacts(tmp_path)
    assert caught.value.code == "artifact_directory" and caught.value.__context__ is None


def test_raw_sentinel_absent_from_debug_logs_provenance_reports_and_remaining_files(tmp_path, caplog, capsys):
    sentinel = "GateSyntheticUnshared_2026"
    source = tmp_path / "source.txt"; source.write_bytes((sentinel + "\n").encode() * 6)
    artifact = tmp_path / "aggregate.json"
    with caplog.at_level(logging.DEBUG):
        assert main(["patterns", "analyze", "--input", str(source), "--authorized", "--output", str(artifact)]) == 0
        assert main(["patterns", "show", str(artifact)]) == 0
        reused = PatternAnalysisService().prepare_reuse(load_report_file(artifact), request(20), enabled=True)
        results = list(reused.iter_results())
    captured = capsys.readouterr()
    public = artifact.read_text() + captured.out + captured.err + caplog.text + json.dumps([asdict(r) for r in results])
    assert sentinel not in public
    assert set(tmp_path.iterdir()) == {source, artifact}


def test_ordinary_api_job_remains_unfiltered_and_snapshot_contains_no_observed_artifact(tmp_path):
    configured = request()
    learned = report()
    filtered = list(PatternAnalysisService().prepare_reuse(learned, configured, enabled=True).iter_results())
    direct = list(GenerationService().prepare(configured).iter_results())
    assert len(filtered) < len(direct)
    expected = "".join(r.candidate.value + "\n" for r in direct).encode()
    preview = GenerationService().prepare(configured)
    assert preview.evaluated_count == 0
    assert "GateSyntheticUnshared" not in json.dumps(preview.summary().to_dict())
    with TestClient(create_app(data_dir=tmp_path)) as client:
        response = client.post("/api/jobs", json={"request": configured.to_dict()})
        assert response.status_code == 201
        identity = response.json()["id"]
        assert client.app.state.job_manager.wait(identity, 10)["status"] == "completed"
        snapshot = client.get("/api/jobs/" + identity).json()["request"]
        assert snapshot == json.loads(json.dumps(configured.to_dict()))
        assert "GateSyntheticUnshared" not in json.dumps(snapshot)
        assert client.get("/api/jobs/" + identity + "/download").content == expected
    with TestClient(create_app(data_dir=tmp_path)) as restarted:
        assert restarted.get("/api/jobs/" + identity + "/download").content == expected


def test_cli_argument_exception_has_no_sensitive_argparse_context(capsys):
    sentinel = "GateSyntheticUnshared"
    arguments = ["patterns", "analyze", "--input", "unused.txt", "--authorized", "--reference-year", sentinel]
    with pytest.raises(SystemExit) as caught:
        main(arguments)
    assert caught.value.code == 2
    captured = capsys.readouterr()
    assert sentinel not in captured.out + captured.err
    assert sentinel not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__context__ is None and caught.value.__cause__ is None
