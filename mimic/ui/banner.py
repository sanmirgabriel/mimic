"""ASCII banner for interactive terminal sessions."""

from __future__ import annotations

import sys

from mimic import __version__


def print_banner(force: bool = False) -> None:
    """Print the Mimic ASCII banner to stderr.

    The banner is only shown when stderr is a TTY (interactive terminal)
    or when *force* is ``True``.  It never writes to stdout so it cannot
    pollute piped wordlist output.

    Args:
        force: Print even when stderr is not a TTY.
    """
    if not force and not sys.stderr.isatty():
        return

    try:
        from pyfiglet import figlet_format
        from rich.console import Console
    except ImportError:
        # pyfiglet/rich not installed — skip silently.
        return

    console = Console(stderr=True)
    ascii_art = figlet_format("MIMIC", font="slant")
    console.print(ascii_art, style="cyan", end="")
    console.print(f"  mimic the target's mind", style="dim")
    console.print(f"  v{__version__}", style="dim")
    console.print()
