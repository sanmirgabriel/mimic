"""The CLI never stores observation files as sources, packs or Jobs."""

import io
import json
import logging
import sys

import pytest

from mimic.cli import main


def test_cli_json_has_aggregate_provenance_and_no_plaintext_or_paths(tmp_path, capsys, caplog):
    source = tmp_path / "private-observations.txt"
    content = "NeverEchoSecret_2026\nACME123\nNeverEchoSecret_2026\n".encode()
    source.write_bytes(content)
    with caplog.at_level(logging.DEBUG):
        assert main(["patterns", "analyze", "--input", str(source), "--authorized", "--source-label", "synthetic", "--min-occurrences", "1"]) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["source_label"] == "synthetic" and report["sample_size"] == 3
    assert report["patterns"] == [
        {"id": "observed-pattern.word-separator-year.v1", "structure": "WORD + SEPARATOR + YEAR", "occurrences": 2,
         "relative_frequency": {"numerator": 2, "denominator": 3}, "reusable": True},
        {"id": "observed-pattern.acronym-digits.v1", "structure": "ACRONYM + DIGITS", "occurrences": 1,
         "relative_frequency": {"numerator": 1, "denominator": 3}, "reusable": True}]
    assert not captured.err and not caplog.text
    assert "NeverEcho" not in captured.out and str(source) not in captured.out
    assert source.read_bytes() == content and list(tmp_path.iterdir()) == [source]


def test_cli_authorization_required_no_implicit_stdin_read(tmp_path, capsys, monkeypatch):
    class NeverRead:
        def readline(self, size):
            raise AssertionError("unauthorized read")
    monkeypatch.setattr(sys, "stdin", NeverRead())
    assert main(["patterns", "analyze", "--input", "-"]) == 1
    captured = capsys.readouterr()
    assert "authorization_required" in captured.err and captured.out == ""
    assert main(["patterns", "analyze", "--input", str(tmp_path / "missing")]) == 1
    assert "authorization_required" in capsys.readouterr().err


def test_cli_explicit_binary_stdin_and_safe_read_failure(capsys, monkeypatch):
    class Input:
        buffer = io.BytesIO("João_2026\n".encode())
    monkeypatch.setattr(sys, "stdin", Input())
    assert main(["patterns", "analyze", "--input", "-", "--authorized"]) == 0
    assert json.loads(capsys.readouterr().out)["matched_count"] == 1
    monkeypatch.setattr(sys, "stdin", io.StringIO("NeverEchoSecret2026"))
    assert main(["patterns", "analyze", "--input", "-", "--authorized"]) == 2
    captured = capsys.readouterr()
    assert "read_failed" in captured.err and "NeverEcho" not in captured.err and not captured.out


@pytest.mark.parametrize("arguments", [
    ["--max-lines", "invalid-NeverEchoSecret"], ["--source-label", "NeverEcho/Secret"],
    ["--max-line-bytes", "0"], ["--unexpected-NeverEchoSecret"],
], ids=["integer-parse", "source-label", "invalid-limit", "unknown-option"])
def test_cli_input_errors_do_not_echo_arguments_or_partial_reports(arguments, tmp_path, capsys):
    source = tmp_path / "source"; source.write_bytes(b"NeverEchoSecret2026\n")
    try:
        code = main(["patterns", "analyze", "--input", str(source), "--authorized", *arguments])
    except SystemExit as exc:
        code = exc.code
    assert code in (1, 2)
    captured = capsys.readouterr()
    assert captured.out == "" and "NeverEcho" not in captured.err
    assert source.read_bytes() == b"NeverEchoSecret2026\n"


def test_cli_no_report_on_limit_failure_and_missing_file(tmp_path, capsys):
    source = tmp_path / "source"; source.write_bytes(b"NeverEchoSecret2026\n")
    assert main(["patterns", "analyze", "--input", str(source), "--authorized", "--max-line-bytes", "5"]) == 1
    captured = capsys.readouterr()
    assert "line_too_long" in captured.err and "NeverEcho" not in captured.err and not captured.out
    assert main(["patterns", "analyze", "--input", str(tmp_path / "NeverEchoSecret"), "--authorized"]) == 2
    captured = capsys.readouterr()
    assert "read_failed" in captured.err and "NeverEcho" not in captured.err and not captured.out


def test_cli_help_does_not_require_source_or_authorization(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["patterns", "analyze", "--help"])
    assert caught.value.code == 0
    help_text = capsys.readouterr().out
    assert "--authorized" in help_text and "--max-line-bytes" in help_text
