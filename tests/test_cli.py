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
