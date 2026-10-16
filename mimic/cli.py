"""Command-line interface for Mimic."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import logging
import sys
from collections.abc import Iterator
from pathlib import Path
import os
import tempfile
import sqlite3

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
from mimic.intelligence import catalog
from mimic import __version__
from mimic.profile.loader import build_plan, load_profile_file
from mimic.profile.schema import TargetProfile
from mimic.rules.hashcat import export_rules
from mimic.ui.banner import print_banner
from mimic.packs import PackRegistry
from mimic.packs.registry import MAX_IMPORT_BYTES

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
    p.add_argument("--organization-variants", action=argparse.BooleanOptionalAction, default=None,
                   help="Bounded organization name/component/acronym seeds (on for generate; off for legacy).")
    p.add_argument("--service", action="append", default=[], choices=[profile.id for profile in SERVICE_PROFILES],
                   help="Contextual service profile (repeatable).")
    p.add_argument("--intelligence", action=argparse.BooleanOptionalAction, default=None,
                   help="Password Intelligence (default on for generate; off for legacy invocation).")
    p.add_argument("--reference-year", type=int, help="Freeze recent-year knowledge at this year.")
    p.add_argument("--preset", choices=("corporate-br", "corporate-br-v1"),
                   help="Source defaults: organization variants, Intelligence, common numbers, recent years, PT-BR and ready weak values. Explicit switches win; no services are added.")
    p.add_argument("--selector", choices=("score-v1", "diverse-v1"), default="score-v1",
                   help="Selection independent of sources; diverse-v1 is experimental and requires a finite budget. "
                   "Budget prefixes need not nest: the first 100 of a 1000-result diverse list can differ from a 100-result run.")
    for option in ("common-numbers", "recent-years", "corporate-roles"):
        p.add_argument("--" + option, action=argparse.BooleanOptionalAction, default=None)
    p.add_argument("--budget", type=RankingOptions.from_budget, default=RankingOptions(),
                   metavar="PRESET|N", help="Output priority: quick=100, focused=1000, balanced=10000, "
                   "large=100000, exhaustive (default), or a positive integer. Finite budgets rank "
                   "and retain K outputs according to score-v1 after scanning the whole accepted stream; they do not limit CPU work.")
    p.add_argument("--context", help="Deterministic field:value context file.")
    p.add_argument("--dataset", action="append", default=[], help="Local seed corpus (repeatable).")
    p.add_argument("--candidates", action="append", default=[], help="Ready candidates file (repeatable).")
    p.add_argument('--pack', action='append', default=[], metavar='ID@VERSION', help='Local digest-pinned pack (repeatable).')
    p.add_argument('--data-dir', help='MIMIC data directory used to resolve local packs.')
    p.add_argument("--max-dataset-lines", type=int, default=DEFAULT_MAX_LINES)
    p.add_argument("--ptbr", action=argparse.BooleanOptionalAction, default=None, help="Include small built-in PT-BR seed sets.")
    p.add_argument("--include-common-passwords", action=argparse.BooleanOptionalAction, default=None,
                   help="Opt in to independent common weak passwords as ready, non-combinable candidates.")
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
    p.add_argument("--hashcat-bundle", metavar="NEW_DIRECTORY",
                   help="Export paired bases/rules/manifest from actual MIMIC output. Earlier transforms are materialized; no implicit Hashcat execution.")
    p.add_argument("--hashcat-verify", action="store_true",
                   help="Explicitly verify the bundle with local Hashcat 6.2.6 --stdout only; never hashes.")
    p.add_argument("--hashcat-allow-partial", action="store_true",
                   help="Allow declared omissions of controls/invalid Unicode/values exceeding 128 UTF-8 bytes; otherwise fail closed.")
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
    if argv and argv[0] == "frequencies":
        from mimic.frequencies.cli import command
        return command(argv[1:])
    if argv and argv[0] == "patterns":
        return _patterns_command(argv[1:])
    if argv and argv[0] in ("services", "credentials"):
        return _catalog_command(argv[0], argv[1:])
    if argv and argv[0] == 'packs':
        return _packs_command(argv[1:])
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
    if args.hashcat_bundle == "":
        parser.error("--hashcat-bundle requires a nonempty directory")
    if args.hashcat_bundle and (args.export_rules or args.output):
        parser.error("--hashcat-bundle cannot be combined with --export-rules or --output")
    if (args.hashcat_verify or args.hashcat_allow_partial) and not args.hashcat_bundle:
        parser.error("--hashcat-verify/--hashcat-allow-partial require --hashcat-bundle")
    if args.selector == "diverse-v1":
        try:
            args.budget = replace(args.budget, selector=args.selector)
        except ValueError as exc:
            parser.error(str(exc))
    if args.preset:
        if args.ptbr is None:
            args.ptbr = True
        if args.include_common_passwords is None:
            args.include_common_passwords = True
        if args.intelligence is None:
            args.intelligence = True
        if args.organization_variants is None:
            args.organization_variants = True
    args.ptbr = bool(args.ptbr)
    args.include_common_passwords = bool(args.include_common_passwords)

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
                  or args.team or args.pet or args.company or args.organization or args.service or args.pack
                  or args.include_common_passwords):
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
                                     or args.organization or args.service or args.pack or args.include_common_passwords):
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

    registry = PackRegistry(args.data_dir)
    try:
        packs = tuple(registry.reference(identity) for identity in args.pack)
        SourceOptions(packs=packs)
    except (ValueError, OSError) as exc:
        logger.error('Cannot resolve pack: %s', exc)
        return 1
    request = GenerationRequest(
        preset=args.preset,
        organization_variants=modern if args.organization_variants is None else args.organization_variants,
        ranking=args.budget,
        target=Target(profile.nome or "", profile) if profile is not None else None,
        organization=Organization(args.organization) if args.organization else None,
        intelligence=IntelligenceOptions(
            enabled=modern if args.intelligence is None else args.intelligence,
            common_numbers=True if args.common_numbers is None else args.common_numbers,
            recent_years=True if args.recent_years is None else args.recent_years,
            corporate_roles=True if args.corporate_roles is None else args.corporate_roles,
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
            include_common_passwords=args.include_common_passwords,
            packs=packs,
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
    if args.hashcat_bundle:
        from mimic.rules.bundle import BundleError, export_bundle
        try:
            manifest = export_bundle(request, args.hashcat_bundle, service=GenerationService(registry),
                                     allow_partial=args.hashcat_allow_partial, verify=args.hashcat_verify)
        except BundleError as exc:
            logger.error("Hashcat bundle incompatibility: %s", exc)
            return 3
        except ApplicationError:
            logger.error("Invalid generation request for Hashcat bundle")
            return 1
        except (ValueError, TypeError):
            logger.error("Invalid source input for Hashcat bundle")
            return 1
        except (OSError, sqlite3.Error):
            logger.error("Hashcat bundle I/O or publication failed")
            return 2
        logger.info("Hashcat bundle: %s; coverage=%s; exported=%d/%d; segments=%d; verification=%s; order/rank/provenance are not preserved",
                    manifest['mode'], manifest['equivalence']['coverage'], manifest['counts']['exported'],
                    manifest['counts']['retained'], len(manifest['segments']), manifest['equivalence']['differential']['status'])
        return 0
    try:
        prepared = GenerationService(registry).prepare(request)
    except (ApplicationError, ValueError, OSError) as exc:
        logger.error("Invalid generation configuration: %s", exc)
        return 1
    if request.preset:
        logger.info("Preset %s resolved: organization_variants=%s intelligence=%s common_numbers=%s recent_years=%s corporate_roles=%s ptbr=%s ready_common=%s services=%s",
                    request.preset, request.organization_variants, request.intelligence.enabled,
                    request.intelligence.common_numbers, request.intelligence.recent_years,
                    request.intelligence.corporate_roles, request.sources.include_ptbr,
                    request.sources.include_common_passwords, request.intelligence.service_profiles)
    # Pack executions publish a file only after every source has finished intact.
    staged_output = None
    if packs and args.output:
        try:
            descriptor, staged_output = tempfile.mkstemp(prefix='.mimic-', suffix='.part', dir=Path(args.output).absolute().parent)
            os.close(descriptor)
        except OSError as exc:
            logger.error('Cannot stage pack output: %s', exc)
            return 2
    sink = Sink(output_path=staged_output or args.output)

    if args.debug:
        values = (_trace_results(prepared.iter_results()) if request.ranking.enabled
                  else _trace(prepared.iter_candidates()))
    else:
        values = prepared.iter_values()

    try:
        count = sink.drain(values)
        if staged_output:
            os.replace(staged_output, args.output)
        logger.info("Generated %d candidates.", count)
    except (OSError, UnicodeError) as exc:
        logger.error("I/O error during output: %s", exc)
        return 2
    except ValueError as exc:
        logger.error("Invalid dataset: %s", exc)
        return 1
    finally:
        if staged_output:
            Path(staged_output).unlink(missing_ok=True)

    return 0


def _packs_command(argv):
    parser = argparse.ArgumentParser(prog='mimic packs')
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('list', 'show', 'import', 'verify'):
        child = commands.add_parser(command)
        child.add_argument('--data-dir', help='MIMIC data directory.')
        if command in ('show', 'verify'):
            child.add_argument('identity', metavar='ID@VERSION')
        if command == 'import':
            child.add_argument('path')
            child.add_argument('--id', required=True)
            child.add_argument('--version', required=True)
            child.add_argument('--kind', choices=('seed', 'ready'), required=True)
            child.add_argument('--name')
            child.add_argument('--description', default='')
            child.add_argument('--language', default='und')
            child.add_argument('--license', default='NOASSERTION')
            child.add_argument('--source-url')
            child.add_argument('--attribution')
            child.add_argument('--max-bytes', type=int, default=MAX_IMPORT_BYTES,
                               help='Import size ceiling in bytes (maximum 1 GiB).')
    args = parser.parse_args(argv)
    registry = PackRegistry(args.data_dir)
    try:
        if args.command == 'list':
            entries = registry.list()
            if not entries:
                print('No packs installed.')
            for pack in entries:
                print(f'{pack.identity}\t{pack.kind}\t{pack.language}\t{pack.license}\t{pack.name}')
            if any(pack.license == 'NOASSERTION' for pack in entries):
                print('License unverified. Check the source terms before redistribution.', file=sys.stderr)
            return 0
        if args.command == 'import':
            pack = registry.import_file(args.path, id=args.id, version=args.version, kind=args.kind,
                name=args.name, description=args.description, language=args.language, license=args.license,
                source_url=args.source_url, attribution=args.attribution, max_bytes=args.max_bytes)
            print(f'Imported {pack.identity}')
        elif args.command == 'verify':
            pack = registry.verify(args.identity)
            print(f'Verified {pack.identity} SHA-256 {pack.sha256}')
        else:
            pack = registry.get(args.identity)
            print(json.dumps(pack.to_dict(), ensure_ascii=False, indent=2))
        if pack.license == 'NOASSERTION':
            print('License unverified. Check the source terms before redistribution.', file=sys.stderr)
        return 0
    except (ValueError, OSError) as exc:
        print(f'Pack error: {exc}', file=sys.stderr)
        return 1


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
        if result.selection is not None:
            logger.debug("selection=%s family=%s family_version=%s reason=%s", result.selection.selector,
                         result.selection.family, result.selection.family_version, result.selection.reason)
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


def _catalog_command(kind: str, argv: list[str]) -> int:
    """Read-only catalog adapters; common values never become associated pairs."""
    parser = argparse.ArgumentParser(prog=f"mimic {kind}")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list")
    if kind == "services":
        listing.add_argument("--search", default="")
        showing = commands.add_parser("show")
        showing.add_argument("service")
    else:
        exporting = commands.add_parser("export")
        for subparser in (listing, exporting):
            subparser.add_argument("--service", choices=[s.id for s in catalog.SERVICES])
            subparser.add_argument("--category", choices=("documented", "common"), default="documented")
        exporting.add_argument("--format", choices=("csv",), default="csv")
        exporting.add_argument("--output", "-o", required=True)
    args = parser.parse_args(argv)
    try:
        if kind == "services":
            if args.command == "list":
                print("ID\tService\tDocumented defaults")
                for service in catalog.list_services(args.search):
                    print(f"{service.id}\t{service.display_name}\t{len(catalog.list_credentials(service.id))}")
            else:
                service = catalog.get_service(args.service)
                profile = next(p for p in SERVICE_PROFILES if p.id == service.id)
                print(f"{service.display_name} ({service.id})")
                print(service.description)
                print("Aliases: " + ", ".join(service.aliases))
                print("Contextual tokens: " + ", ".join(profile.tokens))
                print("Conventional accounts/roles (not credential pairs): " + ", ".join(profile.roles))
                print(f"Documented defaults: {len(catalog.list_credentials(service.id))}")
                print("Authentication notes: " + service.authentication_notes)
                print("Catalog version: " + service.catalog_version)
                for title, url in service.references:
                    print(f"Source: {title} — {url}")
            return 0
        if args.category == "common" and args.service:
            raise ValueError("common values are global; --service cannot be combined with --category common")
        if args.command == "export":
            content = catalog.common_csv() if args.category == "common" else catalog.credentials_csv(args.service)
            # Publish only complete data; link() atomically refuses an existing
            # destination (including symlinks), even if it appeared during writing.
            descriptor, staged = tempfile.mkstemp(prefix='.mimic-catalog-', suffix='.part',
                                                  dir=Path(args.output).absolute().parent)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as output:
                    output.write(content)
                    output.flush()
                    os.fsync(output.fileno())
                os.link(staged, args.output)
            finally:
                Path(staged).unlink()
            print(f"Exported {args.category} catalog to {args.output}")
            return 0
        if args.category == "common":
            vocabulary = catalog.common_vocabulary()
            print("Common weak values (common_value)")
            print(vocabulary.description)
            print(f"Collection: {vocabulary.id} / {vocabulary.version}")
            print("Common usernames:\n" + "\n".join(vocabulary.usernames))
            print("Common weak passwords:\n" + "\n".join(vocabulary.passwords))
            return 0
        credentials = catalog.list_credentials(args.service)
        if not credentials:
            print("No documented default credentials in this catalog for this service.")
        for credential in credentials:
            print(f"{catalog.get_service(credential.service_id).display_name}: {credential.username} / {credential.password} ({credential.type})")
            print("Source: " + credential.source_title + " — " + credential.source_url)
            print("Applicability: " + credential.applicability)
            for restriction in credential.restrictions:
                print("Restriction: " + restriction)
            if credential.version_scope:
                print("Version scope: " + credential.version_scope)
            print(f"Catalog: {credential.catalog_version}; record: {credential.record_version}")
        return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Cannot export catalog: {exc}", file=sys.stderr)
        return 2


def _patterns_command(argv: list[str]) -> int:
    """Sensitive input is read separately from generation, logging and Jobs."""
    from mimic.application.observations import (
        ObservationError, ObservationLimits, PatternAnalysisService, load_report_file, report_bytes, save_report,
    )

    class PrivateParser(argparse.ArgumentParser):
        def error(self, message):
            # argparse normally echoes invalid values, which may be sensitive.
            self.exit(2, "Invalid pattern-analysis arguments; use --help.\n")

    parser = PrivateParser(prog="mimic patterns")
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="Analyze authorized local observations; aggregate JSON only.")
    analyze.add_argument("--input", required=True, metavar="FILE", help="Local UTF-8 file, or - for explicit binary stdin.")
    analyze.add_argument("--authorized", action="store_true", help="Confirm authorization to analyze this material.")
    analyze.add_argument("--source-label", default="local-observations", help="Non-sensitive identifier; never a path or password.")
    analyze.add_argument("--max-bytes", type=int, default=64 * 1024 * 1024)
    analyze.add_argument("--max-lines", type=int, default=100_000)
    analyze.add_argument("--max-line-bytes", type=int, default=1024)
    analyze.add_argument("--reference-year", type=int, help="Recognize years from 1900 through this explicit year (default: fixed 1900-2099).")
    analyze.add_argument("--min-occurrences", type=int, default=5, help="Minimum count for publishing a structure (default: 5).")
    analyze.add_argument("--output", "-o", help="Publish aggregate JSON atomically; existing files are refused.")
    show = commands.add_parser("show", help="Validate and display an aggregate artifact; never run generation.")
    show.add_argument("artifact", metavar="FILE")
    parse_failed = False
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code != 2:
            raise
        parse_failed = True
    if parse_failed:
        # Raise after argparse's handler has exited, without its private values
        # attached as exception context. The parser printed only a fixed error.
        raise SystemExit(2)
    try:
        if args.command == "show":
            print(report_bytes(load_report_file(args.artifact)).decode("ascii"), end="")
            return 0
        limits = ObservationLimits(args.max_bytes, args.max_lines, args.max_line_bytes)
        service = PatternAnalysisService()
        options = dict(authorized=args.authorized, source_label=args.source_label, limits=limits,
                       reference_year=args.reference_year, min_occurrences=args.min_occurrences)
        if args.input == "-":
            report = service.analyze(getattr(sys.stdin, "buffer", None), **options)
        else:
            report = service.analyze_file(args.input, **options)
        if args.output:
            save_report(report, args.output)
        else:
            print(report_bytes(report).decode("ascii"), end="")
        return 0
    except ObservationError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 2 if exc.code in ("read_failed", "not_regular_file", "write_failed") else 1
    except OSError:
        print("Cannot write the aggregate observation report.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
