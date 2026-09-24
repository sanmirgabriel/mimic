"""Command-line interface for Mimic."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Iterator
from itertools import chain
from pathlib import Path

from mimic.core.candidate import Candidate, Origin
from mimic.core.sink import Sink
from mimic.domain.context import load_context
from mimic.domain.datasets import DEFAULT_MAX_LINES, stream_dataset, stream_ptbr
from mimic.domain.models import Generation, GenerationOptions
from mimic.domain.planning import prepare_generation
from mimic import __version__
from mimic.profile.loader import build_plan, load_profile_file
from mimic.profile.schema import TargetProfile
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
    p.add_argument("-n", "--name", action="append", default=[], help="Target name (repeatable).")
    p.add_argument("-d", "--birth-date", help="Birth date, DD/MM or DD/MM/YYYY.")
    p.add_argument("-t", "--team", help="Target's football team.")
    p.add_argument("-p", "--pet", help="Target's pet name.")
    p.add_argument("-c", "--company", help="Target's company.")
    p.add_argument("--context", help="Deterministic field:value context file.")
    p.add_argument("--dataset", action="append", default=[], help="Local seed corpus (repeatable).")
    p.add_argument("--candidates", action="append", default=[], help="Ready candidates file (repeatable).")
    p.add_argument("--max-dataset-lines", type=int, default=DEFAULT_MAX_LINES)
    p.add_argument("--ptbr", action="store_true", help="Include small built-in PT-BR seed sets.")
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
        help="Auto-generate an inclusive ascending interval of at most 200 years, e.g. 2018:2026.",
    )
    p.add_argument(
        "--max-per-word",
        type=int,
        default=5000,
        metavar="N",
        help="Cap on candidates produced per base word by the mutation "
             "pipeline, enforced after every stage (default: 5000).",
    )
    p.add_argument(
        "--profile",
        metavar="FILE",
        help="Structured target profile (.yaml/.yml/.json). Coexists with "
             "--names: profile fields add to whatever --names/--numbers "
             "already provide.",
    )
    p.add_argument(
        "--debug",
        action="store_true",
        help="Log causal origins and transformations of each candidate. Implies verbose "
             "logging even under --quiet.",
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


_MAX_YEAR_RANGE = 200


def _parse_year_range(spec: str) -> list[str]:
    """Parse an ascending inclusive interval of at most 200 year tokens."""
    parts = spec.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid year-range format: {spec!r}  (expected START:END)")
    try:
        start, end = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise ValueError("year-range endpoints must be integers (START:END)") from exc
    if end < start:
        raise ValueError("year-range START must be <= END")
    if end - start + 1 > _MAX_YEAR_RANGE:
        raise ValueError(f"year-range must contain at most {_MAX_YEAR_RANGE} years")
    return [str(y) for y in range(start, end + 1)]


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``mimic`` CLI.

    Returns:
        Exit code: 0 success, 1 input error, 2 I/O error.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "profile":
        profile_parser = argparse.ArgumentParser(prog="mimic profile")
        profile_commands = profile_parser.add_subparsers(dest="command", required=True)
        inspect_parser = profile_commands.add_parser("inspect", help="Show parsed profile/context")
        inspect_parser.add_argument("path")
        profile_args = profile_parser.parse_args(argv[1:])
        return _inspect_profile(profile_args.path)
    if argv and argv[0] == "generate":
        argv = argv[1:]
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Show banner in interactive mode (unless suppressed).
    if not args.quiet and not args.no_banner:
        print_banner()

    # Configure logging: stderr only, suppressed by --quiet (unless --debug).
    log_level = logging.DEBUG if args.debug else (
        logging.WARNING if args.quiet else logging.INFO
    )
    logging.basicConfig(
        level=log_level,
        format="[mimic] %(message)s",
        stream=sys.stderr,
    )

    # --- Load names ---
    # Profile-only and rule export runs never wait for implicit stdin input.
    try:
        if args.names:
            names = _read_lines(args.names)
        elif not (args.profile or args.export_rules or args.name or args.context
                  or args.dataset or args.candidates or args.ptbr or args.birth_date
                  or args.team or args.pet or args.company):
            names = [
                line.strip()
                for line in sys.stdin
                if line.strip()
            ]
        else:
            names = []
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

    base_candidates = [Candidate(n, (Origin("cli", "names", n),)) for n in names]
    if args.name:
        for name in args.name:
            value = name.strip()
            if value:
                base_candidates.append(Candidate(value, (Origin("manual", "nome", value),)))
                names.append(value)
    number_candidates = [Candidate(n, (Origin("cli", "numbers", n),)) for n in numbers]
    if args.year_range:
        try:
            years = _parse_year_range(args.year_range)
            numbers.extend(years)
            number_candidates.extend(
                Candidate(year, (Origin("cli", "year_range", year),)) for year in years
            )
        except ValueError as exc:
            logger.error("%s", exc)
            return 1

    # --- Load profile (optional; merges into names/numbers, plus isolated
    # seeds that must never be cross-combined by --combine) ---
    isolated_seeds: list[str] = []
    isolated_candidates: list[Candidate] = []
    if args.profile:
        try:
            profile = load_profile_file(args.profile)
            plan = build_plan(profile)
        except FileNotFoundError as exc:
            logger.error("Profile file not found: %s", exc)
            return 1
        except (ValueError, ImportError) as exc:
            logger.error("%s", exc)
            return 1
        except OSError as exc:
            logger.error("I/O error reading profile: %s", exc)
            return 2
        names.extend(plan.base_words)
        numbers.extend(plan.numbers)
        isolated_seeds.extend(plan.isolated_seeds)
        base_candidates.extend(plan.base_candidates)
        number_candidates.extend(plan.number_candidates)
        isolated_candidates.extend(plan.isolated_candidates)

    inline = {"data_nascimento": args.birth_date, "time_futebol": args.team,
              "pet": args.pet, "empresa": args.company}
    try:
        inline_plan = build_plan(TargetProfile.from_dict(inline))
        isolated_candidates.extend(inline_plan.isolated_candidates)
        number_candidates.extend(inline_plan.number_candidates)
        numbers.extend(inline_plan.numbers)
        facts = load_context(args.context) if args.context else []
        if args.max_dataset_lines < 1:
            raise ValueError("max-dataset-lines must be >= 1")
    except FileNotFoundError as exc:
        logger.error("Context file not found: %s", exc)
        return 1
    except (ValueError, TypeError) as exc:
        logger.error("Invalid context: %s", exc)
        return 1
    except OSError as exc:
        logger.error("I/O error reading context: %s", exc)
        return 2

    if not args.export_rules and not (names or isolated_seeds or isolated_candidates
                                     or facts or args.dataset or args.candidates or args.ptbr):
        logger.error("No names provided.")
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

    try:
        options = GenerationOptions(
            leet_mode=args.leet, combine=args.combine, separators=args.separators,
            max_candidates_per_word=args.max_per_word,
            min_len=args.min_len,
            max_len=args.max_len,
            require_upper=args.require_upper,
            require_lower=args.require_lower,
            require_digit=args.require_digit,
            require_special=args.require_special,
        )

        extra = chain(
            *(stream_dataset(path, ready=True, max_lines=args.max_dataset_lines)
              for path in args.candidates),
            *(stream_dataset(path, max_lines=args.max_dataset_lines) for path in args.dataset),
            stream_ptbr() if args.ptbr else (),
        )
        generator = prepare_generation(
            Generation(options=options, output_path=args.output),
            base_candidates=base_candidates, isolated_candidates=isolated_candidates,
            number_candidates=number_candidates, context_facts=facts,
            extra_seeds=extra,
        ).generator
    except (ValueError, TypeError) as exc:
        logger.error("Invalid generation configuration: %s", exc)
        return 1
    sink = Sink(output_path=args.output)

    candidates = generator.generate()
    if args.debug:
        candidates = _trace(generator.generate_candidates())

    try:
        count = sink.drain(candidates)
        logger.info("Generated %d candidates.", count)
    except (OSError, UnicodeError) as exc:
        logger.error("I/O error during output: %s", exc)
        return 2
    except ValueError as exc:
        logger.error("Invalid dataset: %s", exc)
        return 1

    return 0


def _inspect_profile(path: str) -> int:
    try:
        if Path(path).suffix.lower() == ".txt":
            facts = load_context(path)
            data: dict[str, object] = {}
            for fact in facts:
                if fact.field == "apelidos":
                    data.setdefault("apelidos", []).append(fact.candidate.value)
                elif fact.field in data:
                    previous = data[fact.field]
                    if isinstance(previous, list):
                        previous.append(fact.candidate.value)
                    else:
                        data[fact.field] = [previous, fact.candidate.value]
                else:
                    data[fact.field] = fact.candidate.value
        else:
            from dataclasses import asdict
            data = asdict(load_profile_file(path))
    except (OSError, ValueError, ImportError) as exc:
        logger.error("Cannot inspect profile: %s", exc)
        return 1
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def _trace(candidates: Iterator[Candidate]) -> Iterator[str]:
    """Render recorded causal metadata, without matching the final string."""
    for candidate in candidates:
        origins = " + ".join(
            f"{origin.source}.{origin.field}={origin.value}" for origin in candidate.origins
        )
        steps = " -> ".join(
            f"{step.kind}({', '.join(f'{k}={v}' for k, v in step.params)})"
            for step in candidate.transformations
        )
        logger.debug("%s <- %s | %s", candidate.value, origins or "no origin supplied", steps)
        yield candidate.value


if __name__ == "__main__":
    sys.exit(main())
