"""Tests for the ASCII banner module."""

from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import patch

from mimic.ui.banner import print_banner
from mimic.cli import main


def test_banner_silent_when_not_tty() -> None:
    """Banner produces no output when stderr is not a TTY."""
    buf = io.StringIO()
    with patch("sys.stderr", buf):
        # stderr.isatty() returns False on StringIO
        print_banner(force=False)
    assert buf.getvalue() == ""


def test_banner_writes_to_stderr_when_forced() -> None:
    """When forced, the banner writes to stderr (not stdout)."""
    stdout_buf = io.StringIO()
    with patch("sys.stdout", stdout_buf):
        print_banner(force=True)
    # stdout must remain untouched
    assert stdout_buf.getvalue() == ""


def test_no_banner_flag_suppresses_banner(tmp_path: Path) -> None:
    """--no-banner prevents the banner from appearing even in TTY mode."""
    names_file = tmp_path / "names.txt"
    names_file.write_text("admin\n", encoding="utf-8")
    output_file = tmp_path / "out.txt"

    stderr_buf = io.StringIO()
    # Make stderr look like a TTY so the banner would normally show
    stderr_buf.isatty = lambda: True  # type: ignore[assignment]

    with patch("sys.stderr", stderr_buf):
        main([
            "--names", str(names_file),
            "--output", str(output_file),
            "--no-banner",
            "--leet", "none",
        ])

    # "MIMIC" ASCII art should NOT appear in stderr
    assert "MIMIC" not in stderr_buf.getvalue()
