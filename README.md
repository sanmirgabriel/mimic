# Mimic

> **Mimic the target's mind. Forge the wordlist.**

```
    __  ___________  _______________
   /  |/  /  _/  |/  /  _/ ____/
  / /|_/ // // /|_/ // // /
 / /  / // // /  / // // /___
/_/  /_/___/_/  /_/___/\____/
```

![CI](https://github.com/YOUR_USER/mimic/actions/workflows/ci.yml/badge.svg)

Target-aware wordlist generator for credential attacks. Profiles the human behind the password.

## Screenshots

<!-- TODO: Replace with actual asciinema recording -->
![Demo](https://placeholder.example.com/mimic-demo.gif)

## Installation

```bash
# Core (no banner)
pip install -e .

# With interactive banner (pyfiglet + rich)
pip install -e ".[ui]"
```

## Usage

### Pipe to hashcat

```bash
echo -e "joao\nsilva" | mimic --leet partial --year-range 2020:2026 | hashcat -m 0 hashes.txt
```

### Pipe to Hydra

```bash
mimic --names targets.txt --numbers dates.txt --combine \
  | hydra -L users.txt -P /dev/stdin ssh://192.168.1.100
```

### Generate with password policy

```bash
mimic --names names.txt \
  --min-len 8 --max-len 16 \
  --require-upper --require-digit --require-special \
  --year-range 2020:2026 \
  --output wordlist.txt
```

### Export hashcat rules

Instead of generating an expanded wordlist, export the transformation logic as a `.rule` file for GPU-accelerated cracking:

```bash
mimic --names names.txt --year-range 2020:2026 --export-rules mutations.rule
hashcat -m 0 -r mutations.rule hashes.txt base_words.txt
```

## CLI Reference

```
mimic [OPTIONS]

--names FILE        Base names/keywords file (reads stdin if omitted)
--numbers FILE      Extra numbers/years file
--output FILE       Output file (default: stdout)
--leet {none,partial,full}   Leet-speak mode (default: partial)
--combine           Cross-combine names (joao+silva -> joaosilva, jsilva, ...)
--min-len N         Minimum password length
--max-len N         Maximum password length
--require-upper     Require uppercase letter
--require-lower     Require lowercase letter
--require-digit     Require digit
--require-special   Require special character
--separators CHARS  Separator characters (default: @!#_.)
--export-rules FILE Export hashcat .rule file instead of wordlist
--year-range S:E    Auto-generate year numbers (e.g. 2018:2026)
--quiet             Suppress progress and banner on stderr
--no-banner         Suppress ASCII banner only
--version           Show version and exit
```

## Why another wordlist generator?

| Feature | CUPP | Crunch | Mentalist | Mimic |
|---------|------|--------|-----------|-------|
| OSINT-driven input | Yes | No | Yes | Yes |
| Partial leet combinatorics | No | No | No | Yes (C(n,k) combinations) |
| Cross-name combination | Limited | No | Limited | Yes (initials, dotted, separated) |
| Password policy filter | No | Length only | No | Full (upper/lower/digit/special) |
| Hashcat rule export | No | No | Yes | Yes |
| Streaming output | No | Yes | No | Yes (generator-based) |
| Pipeable (stdin/stdout) | Partial | Yes | No (GUI) | Yes |

**CUPP** generates a flat list from a single profile -- no combinatorial leet, no policy filtering, no rule export. **Crunch** is a brute-force permutation engine -- powerful but blind to target context. **Mentalist** has a GUI workflow but no CLI pipeline integration. **Mimic** sits in the sweet spot: target-aware like CUPP, with combinatorial depth, policy enforcement, and native hashcat rule export for GPU-accelerated cracking.

## Benchmarks

<!-- TODO: Fill with actual benchmark numbers -->

| Names | Numbers | Leet Mode | Candidates | Time | Memory |
|-------|---------|-----------|------------|------|--------|
| 10 | 20 | partial | -- | -- | -- |
| 50 | 50 | partial | -- | -- | -- |
| 100 | 100 | full | -- | -- | -- |

## Architecture

```
mimic/
├── cli.py              # argparse entry point
��── core/
│   ├── generator.py    # Orchestrates mutators + dedup + policy
│   ├── policy.py       # PasswordPolicy filter
│   └── sink.py         # Streaming output (stdout or file)
├── mutators/
│   ├── base.py         # ABC Mutator
│   ├── case.py         # Case variations
│   ├─��� leet.py         # Partial/full leet-speak
│   ├─��� affix.py        # Number prefix/suffix with separators
│   ├── combine.py      # Cross-name combination
│   └── reverse.py      # Word reversal
├── rules/
│   └── hashcat.py      # .rule file exporter
└── ui/
    └── banner.py       # ASCII banner (pyfiglet + rich, optional)
```

## Roadmap

- **v0.2.0** -- OSINT integration (crt.sh, GitHub orgs, CeWL-style site crawler)
- **v0.3.0** -- Brazilian-Portuguese profile mode (DD/MM/AAAA dates, common PT patterns)
- **v0.4.0** -- Markov-chain mode trained on leak corpora

## Development

```bash
pip install -e ".[dev,ui]"
pytest -v
```

## License

MIT
