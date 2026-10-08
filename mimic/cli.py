"""Command-line interface for Mimic."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Iterator
from pathlib import Path

from mimic.application import (
    ApplicationError,
    GenerationLimits,
    GenerationRequest,
    GenerationService,
    MutationOptions,
    PolicyOptions,
    SourceOptions,
    IntelligenceOptions,
    RankingOptions,
    GenerationResult,
)
from mimic.core.candidate import Candidate, Origin
from mimic.core.sink import Sink
from mimic.domain.context import ExtractedFact, load_context
from mimic.domain.datasets import DEFAULT_MAX_LINES
from mimic.domain.models import Organization, Target
from mimic.intelligence.builtins import SERVICE_PROFILES
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
    p.add_argument("--organization", help="Organization name; no saved record or target required.")
    p.add_argument("--service", action="append", default=[], choices=[profile.id for profile in SERVICE_PROFILES],
                   help="Contextual service profile (repeatable).")
    p.add_argument("--intelligence", action=argparse.BooleanOptionalAction, default=None,
                   help="Password Intelligence (default on for generate; off for legacy invocation).")
    p.add_argument("--reference-year", type=int, help="Freeze recent-year knowledge at this year.")
    p.add_argument("--budget", type=RankingOptions.from_budget, default=RankingOptions(),
                   metavar="PRESET|N", help="Output priority: quick=100, focused=1000, balanced=10000, "
                   "large=100000, exhaustive (default), or a positive integer. Finite budgets rank "
                   "and retain K outputs according to score-v1 after scanning the whole accepted stream; they do not limit CPU work.")
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
        help="Leet-speak mode (default: partial, original + up to 2 substitutions per word).",
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
    if argv and argv[0] == "serve":
        serve_parser = argparse.ArgumentParser(prog="mimic serve")
        serve_parser.add_argument("--host", default="127.0.0.1")
        serve_parser.add_argument("--port", type=int, default=8787)
        serve_parser.add_argument("--data-dir")
        serve_args = serve_parser.parse_args(argv[1:])
        if serve_args.host not in ("127.0.0.1", "::1"):
            serve_parser.error("only loopback hosts are allowed without authentication")
        if not 1 <= serve_args.port <= 65535:
            serve_parser.error("port must be between 1 and 65535")
        try:
            import uvicorn
            from mimic.api import create_app
        except ImportError as exc:
            serve_parser.error("web dependencies unavailable; install mimic[web]")
        uvicorn.run(create_app(data_dir=serve_args.data_dir),
                    host=serve_args.host, port=serve_args.port)
        return 0
    if argv and argv[0] == "profile":
        profile_parser = argparse.ArgumentParser(prog="mimic profile")
        profile_commands = profile_parser.add_subparsers(dest="command", required=True)
        inspect_parser = profile_commands.add_parser("inspect", help="Show parsed profile/context")
        inspect_parser.add_argument("path")
        profile_args = profile_parser.parse_args(argv[1:])
        return _inspect_profile(profile_args.path)
    modern = bool(argv and argv[0] == "generate")
    if modern:
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
                  or args.team or args.pet or args.company or args.organization or args.service):
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

    # Parse profile input here; its engine mapping belongs to the shared plan.
    profile = None
    if args.profile:
        try:
            profile = load_profile_file(args.profile)
        except FileNotFoundError as exc:
            logger.error("Profile file not found: %s", exc)
            return 1
        except (ValueError, ImportError) as exc:
            logger.error("%s", exc)
            return 1
        except OSError as exc:
            logger.error("I/O error reading profile: %s", exc)
            return 2

    inline = {"data_nascimento": args.birth_date, "time_futebol": args.team,
              "pet": args.pet, "empresa": args.company}
    try:
        inline_profile = TargetProfile.from_dict(inline)
        if args.max_dataset_lines < 1:
            raise ValueError("max-dataset-lines must be >= 1")
    except (ValueError, TypeError) as exc:
        logger.error("Invalid context: %s", exc)
        return 1

    inline_facts = tuple(
        ExtractedFact(field, Candidate(value, (Origin("profile", field, value),)))
        for field in ("data_nascimento", "time_futebol", "empresa", "pet")
        if (value := getattr(inline_profile, field)) is not None
    )
    has_profile_seed = bool(profile and (
        profile.nome or profile.apelidos or profile.time_futebol or profile.empresa or profile.pet
    ))
    has_inline_seed = bool(
        inline_profile.time_futebol or inline_profile.empresa or inline_profile.pet
    )
    if not args.export_rules and not (names or has_profile_seed or has_inline_seed
                                     or args.context or args.dataset or args.candidates or args.ptbr
                                     or args.organization or args.service):
        logger.error("No names provided.")
        return 1

    # --- Export hashcat rules mode ---
    if args.export_rules:
        try:
            if profile is not None:
                numbers.extend(build_plan(profile).numbers)
            numbers.extend(build_plan(inline_profile).numbers)
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
        except ValueError as exc:
            logger.error("Invalid profile for rule export: %s", exc)
            return 1

    request = GenerationRequest(
        ranking=args.budget,
        target=Target(profile.nome or "", profile) if profile is not None else None,
        organization=Organization(args.organization) if args.organization else None,
        intelligence=IntelligenceOptions(
            enabled=modern if args.intelligence is None else args.intelligence,
            service_profiles=tuple(args.service), reference_year=args.reference_year,
        ),
        base_candidates=tuple(base_candidates),
        number_candidates=tuple(number_candidates),
        context_facts=inline_facts,
        context_path=args.context,
        sources=SourceOptions(
            dataset_paths=tuple(args.dataset),
            ready_candidate_paths=tuple(args.candidates),
            include_ptbr=args.ptbr,
        ),
        mutations=MutationOptions(
            leet_mode=args.leet, combine=args.combine, separators=args.separators,
        ),
        policy=PolicyOptions(
            min_len=args.min_len, max_len=args.max_len,
            require_upper=args.require_upper, require_lower=args.require_lower,
            require_digit=args.require_digit, require_special=args.require_special,
        ),
        limits=GenerationLimits(
            max_candidates_per_word=args.max_per_word,
            max_dataset_lines=args.max_dataset_lines,
        ),
    )
    try:
        prepared = GenerationService().prepare(request)
    except ApplicationError as exc:
        logger.error("Invalid generation configuration: %s", exc)
        return 1
    sink = Sink(output_path=args.output)

    if args.debug:
        values = (_trace_results(prepared.iter_results()) if request.ranking.enabled
                  else _trace(prepared.iter_candidates()))
    else:
        values = prepared.iter_values()

    try:
        count = sink.drain(values)
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


def _trace_results(results: Iterator[GenerationResult]) -> Iterator[str]:
    for result in results:
        if result.score is not None:
            logger.debug("rank=%d score=%d model=%s components=%s", result.rank, result.score.total,
                         result.score.version, json.dumps(result.score.to_dict()["components"], ensure_ascii=False))
        yield from _trace(iter((result.candidate,)))


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
