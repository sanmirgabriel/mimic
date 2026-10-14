"""Offline frequency commands. Fixed errors never echo paths or rejected fields."""
import argparse
import json
import sys

from mimic.frequencies import FrequencyError, FrequencyRegistry
from mimic.frequencies.comparison import compare
from mimic.frequencies.evaluation import evaluate


def command(argv):
    class PrivateParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, 'Invalid frequency arguments; use --help.\n')

    parser = PrivateParser(prog='mimic frequencies', description='Local aggregate knowledge; no downloads or generation.')
    parser.add_argument('--data-dir', help='Configured local data root (default: XDG data directory).')
    commands = parser.add_subparsers(dest='command', required=True)
    importer = commands.add_parser('import', help='Validate aggregate JSON completely before private atomic publication.')
    importer.add_argument('file')
    example = commands.add_parser('example', help='Print a bundled synthetic aggregate; never imports automatically.')
    example.add_argument('name', choices=('synthetic-a', 'synthetic-b'))
    listing = commands.add_parser('list', help='List verified evidence; optionally search metadata or canonical pattern IDs.')
    listing.add_argument('--query', default='')
    for name in ('show', 'verify', 'evaluate'):
        sub = commands.add_parser(name, help='Inspect verified evidence.' if name != 'evaluate' else 'Run fixed synthetic slot experiment only.')
        sub.add_argument('identity', help='dataset-id@version')
        sub.add_argument('--sha256', help='Optional independently retained expected canonical digest.')
    comparison = commands.add_parser('compare', help='Contrast two sources without pooling or statistical claims.')
    comparison.add_argument('left')
    comparison.add_argument('right')
    failed = False
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code != 2:
            raise
        failed = True
    if failed:
        raise SystemExit(2)
    try:
        registry = FrequencyRegistry(args.data_dir)
        if args.command == 'example':
            from importlib.resources import files
            from mimic.frequencies.registry import load_dataset
            from mimic.frequencies.models import dataset_bytes
            with files('mimic.data.frequencies').joinpath(args.name + '.json').open('rb') as stream:
                dataset = load_dataset(stream)
            print(dataset_bytes(dataset).decode('ascii'), end='')
            return 0
        if args.command == 'import':
            result = dict(status='verified', **registry.import_file(args.file).evidence())
        elif args.command == 'list':
            result = [dict(identity=d.identity, sha256=d.sha256, source=d.source.title,
                           license=d.source.license, redistribution=d.source.redistribution) for d in registry.list(args.query)]
        elif args.command == 'compare':
            result = compare(registry.get(args.left), registry.get(args.right))
        else:
            dataset = registry.get(args.identity, expected_digest=args.sha256)
            result = evaluate(dataset) if args.command == 'evaluate' else dict(status='verified', **dataset.evidence())
        print(json.dumps(result, sort_keys=True, ensure_ascii=True, indent=2, allow_nan=False))
        return 1 if args.command == 'compare' and not result['compatible'] else 0
    except FrequencyError as exc:
        print(f'{exc.code}: {exc}', file=sys.stderr)
        return 2 if exc.code in ('read', 'write', 'registry', 'integrity') else 1
    except OSError:
        print('Frequency output is unavailable.', file=sys.stderr)
        return 2
