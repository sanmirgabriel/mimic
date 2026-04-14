"""Command-line interface for Mimic."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from mimic.core.generator import Generator
from mimic.core.policy import PasswordPolicy
from mimic.core.sink import Sink
from mimic.mutators.affix import AffixMutator
from mimic.mutators.base import Mutator
from mimic.mutators.case import CaseMutator
from mimic.mutators.combine import CombineMutator
from mimic.mutators.leet import LeetMutator
from mimic.mutators.reverse import ReverseMutator
from mimic import __version__
from mimic.rules.hashcat import export_rules
from mimic.ui.banner import print_banner

logger = logging.getLogger("mimic")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mimic",
        description="Target-aware wordlist generator for credential attacks.",
    )
    p.add_argument(
        "--names",
        metavar="FILE",
        help="File with base names/keywords, one per line. Reads stdin if omitted.",
    )
    p.add_argument(
        "--numbers",
        metavar="FILE",
        help="File with extra numbers/years, one per line.",
    )
    p.add_argument(
        "--output", "-o",
        metavar="FILE",
        help="Output file (default: stdout).",
    )
    p.add_argument(
        "--leet",
        choices=["none", "partial", "full"],
        default="partial",
        help="Leet-speak mode (default: partial, max 2 subs per word).",
    )
    p.add_argument(
        "--combine",
        action="store_true",
        help="Enable cross-combination of names.",
    )
    p.add_argument("--min-len", type=int, default=0, metavar="N")
    p.add_argument("--max-len", type=int, default=0, metavar="N")
    p.add_argument("--require-upper", action="store_true")
    p.add_argument("--require-lower", action="store_true")
    p.add_argument("--require-digit", action="store_true")
    p.add_argument("--require-special", action="store_true")
    p.add_argument(
        "--separators",
        default="@!#_.",
        help='Separator characters (default: "@!#_.").',
    )
    p.add_argument(
        "--export-rules",
        metavar="FILE",
        help="Export a hashcat .rule file instead of a wordlist.",
    )
    p.add_argument(
        "--year-range",
        metavar="START:END",
        help="Auto-generate year numbers, e.g. 2018:2026.",
    )
    p.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress progress messages on stderr.",
    )
    p.add_argument(
        "--no-banner",
        action="store_true",
        help="Suppress ASCII banner even in interactive mode.",
    )
    p.add_argument(
        "--version", "-V",
        action="version",
        version=f"mimic {__version__}",
    )
    return p


def _read_lines(path: str) -> list[str]:
    """Read non-empty stripped lines from a file."""
    return [
        line.strip()
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _parse_year_range(spec: str) -> list[str]:
    """Parse ``'START:END'`` into a list of year strings."""
    parts = spec.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid year-range format: {spec!r}  (expected START:END)")
    start, end = int(parts[0]), int(parts[1])
    return [str(y) for y in range(start, end + 1)]


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``mimic`` CLI.

    Returns:
        Exit code: 0 success, 1 input error, 2 I/O error.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Show banner in interactive mode (unless suppressed).
    if not args.quiet and not args.no_banner:
        print_banner()

    # Configure logging: stderr only, suppressed by --quiet.
    log_level = logging.WARNING if args.quiet else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="[mimic] %(message)s",
        stream=sys.stderr,
    )

    # --- Load names ---
    try:
        if args.names:
            names = _read_lines(args.names)
        else:
            names = [
                line.strip()
                for line in sys.stdin
                if line.strip()
            ]
        if not names:
            logger.error("No names provided.")
            return 1
    except FileNotFoundError as exc:
        logger.error("Names file not found: %s", exc)
        return 1
    except OSError as exc:
        logger.error("I/O error reading names: %s", exc)
        return 2

    # --- Load numbers ---
    numbers: list[str] = []
    try:
        if args.numbers:
            numbers = _read_lines(args.numbers)
    except FileNotFoundError as exc:
        logger.error("Numbers file not found: %s", exc)
        return 1
    except OSError as exc:
        logger.error("I/O error reading numbers: %s", exc)
        return 2

    if args.year_range:
        try:
            numbers.extend(_parse_year_range(args.year_range))
        except ValueError as exc:
            logger.error("%s", exc)
            return 1

    # --- Export hashcat rules mode ---
    if args.export_rules:
        try:
            count = export_rules(
                numbers=numbers,
                separators=args.separators,
                leet_mode=args.leet,
                output_path=args.export_rules,
            )
            logger.info("Exported %d hashcat rules.", count)
            return 0
        except OSError as exc:
            logger.error("I/O error writing rules: %s", exc)
            return 2

    # --- Build mutator pipeline ---
    mutators: list[Mutator] = [
        CaseMutator(),
        LeetMutator(mode=args.leet),
        ReverseMutator(),
        AffixMutator(numbers=numbers, separators=args.separators),
    ]
    if args.combine:
        mutators.append(CombineMutator(all_names=names, separators=args.separators))

    policy = PasswordPolicy(
        min_len=args.min_len,
        max_len=args.max_len,
        require_upper=args.require_upper,
        require_lower=args.require_lower,
        require_digit=args.require_digit,
        require_special=args.require_special,
    )

    generator = Generator(base_words=names, mutators=mutators, policy=policy)
    sink = Sink(output_path=args.output)

    try:
        count = sink.drain(generator.generate())
        logger.info("Generated %d candidates.", count)
    except OSError as exc:
        logger.error("I/O error during output: %s", exc)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
