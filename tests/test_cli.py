"""End-to-end tests for the CLI entry point."""

from __future__ import annotations

from pathlib import Path

from mimic.cli import main


def test_cli_with_names_file(tmp_path: Path) -> None:
    """CLI reads a names file and writes output to a file."""
    names_file = tmp_path / "names.txt"
    names_file.write_text("admin\nroot\n", encoding="utf-8")
    output_file = tmp_path / "out.txt"

    exit_code = main([
        "--names", str(names_file),
        "--output", str(output_file),
        "--leet", "none",
        "--quiet",
    ])

    assert exit_code == 0
    lines = output_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) > 0
    assert "admin" in lines
    assert "ROOT" in lines


def test_cli_with_numbers_and_years(tmp_path: Path) -> None:
    """CLI combines names with numbers and year-range."""
    names_file = tmp_path / "names.txt"
    names_file.write_text("joao\n", encoding="utf-8")
    output_file = tmp_path / "out.txt"

    exit_code = main([
        "--names", str(names_file),
        "--output", str(output_file),
        "--leet", "none",
        "--year-range", "2024:2025",
        "--quiet",
    ])

    assert exit_code == 0
    lines = output_file.read_text(encoding="utf-8").splitlines()
    assert "joao2024" in lines
    assert "joao2025" in lines


def test_cli_export_rules(tmp_path: Path) -> None:
    """--export-rules writes a hashcat .rule file."""
    names_file = tmp_path / "names.txt"
    names_file.write_text("x\n", encoding="utf-8")
    rules_file = tmp_path / "out.rule"

    exit_code = main([
        "--names", str(names_file),
        "--export-rules", str(rules_file),
        "--year-range", "2024:2024",
        "--quiet",
    ])

    assert exit_code == 0
    content = rules_file.read_text(encoding="utf-8")
    # Must contain hashcat rule syntax
    assert "l" in content.splitlines()  # lowercase rule
    assert "u" in content.splitlines()  # uppercase rule


def test_cli_missing_names_file() -> None:
    """CLI returns exit code 1 for missing names file."""
    exit_code = main(["--names", "/nonexistent/path.txt", "--quiet"])
    assert exit_code == 1


def test_cli_with_profile_only(tmp_path: Path) -> None:
    """--profile alone (no --names) supplies both a name and a date-derived number."""
    profile_file = tmp_path / "profile.json"
    profile_file.write_text(
        '{"time_futebol": "Flamengo", "data_nascimento": "05/09/2000"}',
        encoding="utf-8",
    )
    output_file = tmp_path / "out.txt"

    exit_code = main([
        "--profile", str(profile_file),
        "--output", str(output_file),
        "--leet", "none",
        "--separators", "@",
        "--quiet",
    ])

    assert exit_code == 0
    lines = output_file.read_text(encoding="utf-8").splitlines()
    assert "Flamengo@0905" in lines


def test_cli_profile_coexists_with_names(tmp_path: Path) -> None:
    """--profile and --names can be combined; both contribute seeds."""
    names_file = tmp_path / "names.txt"
    names_file.write_text("joao\n", encoding="utf-8")
    profile_file = tmp_path / "profile.json"
    profile_file.write_text('{"time_futebol": "Flamengo"}', encoding="utf-8")
    output_file = tmp_path / "out.txt"

    exit_code = main([
        "--names", str(names_file),
        "--profile", str(profile_file),
        "--output", str(output_file),
        "--leet", "none",
        "--quiet",
    ])

    assert exit_code == 0
    lines = output_file.read_text(encoding="utf-8").splitlines()
    assert "joao" in lines
    assert "Flamengo" in lines


def test_cli_debug_logs_field_provenance_leet_none(tmp_path: Path, caplog) -> None:
    """--debug with --profile logs which field(s) produced a matching candidate (--leet none)."""
    import logging

    profile_file = tmp_path / "profile.json"
    profile_file.write_text(
        '{"time_futebol": "Flamengo", "data_nascimento": "05/09/2000"}',
        encoding="utf-8",
    )
    output_file = tmp_path / "out.txt"

    with caplog.at_level(logging.DEBUG, logger="mimic"):
        exit_code = main([
            "--profile", str(profile_file),
            "--output", str(output_file),
            "--leet", "none",
            "--separators", "@",
            "--debug",
        ])

    assert exit_code == 0
    trace_lines = [
        r.getMessage() for r in caplog.records if "Flamengo@0905" in r.getMessage()
    ]
    assert trace_lines
    assert "time_futebol=Flamengo" in trace_lines[0]
    assert "data_nascimento=05/09/2000" in trace_lines[0]


def test_cli_debug_logs_field_provenance_leet_partial(tmp_path: Path, caplog) -> None:
    """Same profile, but with --leet partial (the actual CLI default).

    Regression test for the traceability gap: the seed "Flamengo" itself
    gets leet-substituted (e.g. "Fl@mengo"), so a literal-only match would
    silently lose the time_futebol attribution and report only the date.
    """
    import logging

    profile_file = tmp_path / "profile.json"
    profile_file.write_text(
        '{"time_futebol": "Flamengo", "data_nascimento": "05/09/2000"}',
        encoding="utf-8",
    )
    output_file = tmp_path / "out.txt"

    with caplog.at_level(logging.DEBUG, logger="mimic"):
        exit_code = main([
            "--profile", str(profile_file),
            "--output", str(output_file),
            "--leet", "partial",
            "--separators", "@",
            "--debug",
        ])

    assert exit_code == 0
    trace_lines = [
        r.getMessage() for r in caplog.records if "Fl@mengo0905" in r.getMessage()
    ]
    assert trace_lines, "expected a trace line for the leet-substituted candidate"
    assert "time_futebol=Flamengo" in trace_lines[0]
    assert "data_nascimento=05/09/2000" in trace_lines[0]


def test_cli_debug_traces_reversed_candidate(tmp_path: Path, caplog) -> None:
    """Reverse now has causal provenance, without reverse string matching."""
    import logging

    profile_file = tmp_path / "profile.json"
    profile_file.write_text('{"time_futebol": "Flamengo"}', encoding="utf-8")
    output_file = tmp_path / "out.txt"

    with caplog.at_level(logging.DEBUG, logger="mimic"):
        exit_code = main([
            "--profile", str(profile_file),
            "--output", str(output_file),
            "--leet", "none",
            "--debug",
        ])

    assert exit_code == 0
    reversed_trace = [
        r.getMessage() for r in caplog.records if r.getMessage().startswith("ognemalF")
    ]
    assert reversed_trace, "expected a trace line for the reversed candidate"
    assert "profile.time_futebol=Flamengo" in reversed_trace[0]
    assert "reverse()" in reversed_trace[0]
    assert "não rastreável" not in reversed_trace[0]


def test_cli_policy_filters(tmp_path: Path) -> None:
    """CLI respects --min-len and --require-digit flags."""
    names_file = tmp_path / "names.txt"
    names_file.write_text("ab\n", encoding="utf-8")
    output_file = tmp_path / "out.txt"

    exit_code = main([
        "--names", str(names_file),
        "--output", str(output_file),
        "--leet", "none",
        "--min-len", "5",
        "--require-digit",
        "--year-range", "2024:2024",
        "--quiet",
    ])

    assert exit_code == 0
    lines = output_file.read_text(encoding="utf-8").splitlines()
    for line in lines:
        assert len(line) >= 5
        assert any(c.isdigit() for c in line)
