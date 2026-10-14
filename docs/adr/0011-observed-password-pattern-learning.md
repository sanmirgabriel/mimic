# ADR 0011: Local observed password structures without retained secrets

Status: implemented; Gate 11 audited, ready for operator commit review.

Canonical planning remains in [BACKLOG.md](../BACKLOG.md). Validation and final
scope are recorded in [the implementation report](../BLOCK11_IMPLEMENTATION_REPORT.md).

## Context and decision

Authorized operators need descriptive structures from local password samples
without retaining literal observations or adding another generation engine.
`mimic.application.observations.PatternAnalysisService` is a small, stateless,
transport-independent analyzer. Input is a binary stream or regular local file;
output is an immutable, versioned aggregate report. GenerationRequest,
GenerationService, Candidate, Origin, Transformation, Seed, IntelligencePlan,
PreparedGeneration, score-v1, RankingOptions, Jobs and persistence keep their
existing contracts. CLI dispatch imports the analyzer lazily.

No ML, LLM, scraping, cracking, remote authentication, frequency dataset, new
SQLite table, Job type, provider framework or alternative generator is added.
Block 12 remains planned: descriptive frequency inside one operator-supplied
sample is distinct from externally sourced empirical frequency knowledge.

## Grammar and exclusive recognition

Schema: `observed-patterns-v1`; extractor: `pattern-extractor-v1`;
grammar: `observed-shapes-v1`. Twelve fixed structures exist:

| Prefix | Possible suffixes |
| --- | --- |
| WORD | none; SPECIAL; YEAR; DIGITS; SEPARATOR + YEAR; SEPARATOR + DIGITS |
| ACRONYM | none; SPECIAL; YEAR; DIGITS; SEPARATOR + YEAR; SEPARATOR + DIGITS |

Recognition scans the terminal ASCII digits, optionally removes one separator,
then validates the remaining Unicode letters/attached combining marks. Without
numeric digits, a single allowed trailing special character is recognized.
There is no normalization, whitespace trimming, dictionary or semantic name
inference. Composed and decomposed accented spellings can match the same shape
without their literals being saved. Uncased scripts remain WORD.

ACRONYM takes precedence for 2–12 uppercase letters. This is explicitly an
uppercase spelling heuristic, not a proven acronym or authorized organization
identity. YEAR takes precedence over DIGITS only for exactly four ASCII digits
inside the recorded interval. The default is fixed 1900–2099. With an explicit
`reference_year`, the interval is 1900 through that year, accepted in 1900–9999.
The system clock is never consulted. Other four-digit numbers remain DIGITS.
SEPARATOR/SPECIAL is one character from `@!#_.-`; its literal is not retained.

Rows follow fixed grammar order (WORD before ACRONYM; bare, SPECIAL, YEAR,
DIGITS, separator/YEAR, separator/DIGITS). There is no frequency sorting or
unstable tie. Numeric prefixes, multiple words, other separators, repeated
specials and other layouts are explicitly unrecognized. This is a small grammar,
not a universal password parser.

## Streaming, duplicates and privacy

Explicit `authorized=True` (CLI `--authorized`) is required before any source
read or filesystem lookup. File input rejects final symlinks, directories and
FIFOs, verifies the opened descriptor and uses no-follow/nonblocking flags where
available. No-follow race protection depends on platform support; Linux was
validated. Caller-owned streams remain open; file-owned descriptors are closed.

Strict UTF-8 supports an optional BOM only on the first record. Physical records
use LF/CRLF. Byte lengths exclude these terminators but include a leading BOM;
total bytes include terminators. Bare CR, controls, format characters, surrogates
and Unicode line/paragraph separators are rejected. Invalid UTF-8/Unicode records
are counted, never printed. Empty records are separate; space-only values are
valid unrecognized observations. Unicode database version is explicit metadata;
logical determinism assumes that recorded version and extraction configuration.

Defaults: 64 MiB input, 100,000 records, 1,024 content bytes per record. Hard
ceilings: 64 MiB, 100,000 records, 4,096 content bytes. There are at most twelve
structures and artifacts are limited to 16 KiB. Bounded `readline(size)` avoids
whole-file loading; a bounded record or one additional byte distinguishes
exact-limit EOF from overflow. Normal Python file buffering can read ahead by
its bounded internal buffer. Limits apply to logical input consumption. Limit
failure aborts without a partial report.

Every valid nonempty record counts, including repeats. No plaintext/hash dedup
set is retained, so counts describe observations, not unique passwords/users.
Relative frequency is an exact numerator/valid-sample denominator; the denominator
includes valid unrecognized observations. There is no global prevalence claim.

`min_occurrences=5` conservatively suppresses small pattern rows by default.
An explicit 1–100,000 threshold is supported. Suppressed occurrences and the
number of suppressed structures are aggregate counters; suppressed rows are not
directly exported or reused. Complementary totals and overlapping samples can
allow inference of hidden structures/counts (including the last hidden family
when every other family is visible). Five repeated records of one value satisfy
the threshold: this is observation-count suppression, not unique-user anonymity.
This does not guarantee anonymity: sample size, frequencies and explicit source
metadata can still be sensitive. The source label defaults to `local-observations`,
not a filename. Explicit labels must be non-sensitive lowercase ASCII identifiers
of at most 64 characters. Operators are responsible for that metadata.

No original words, years, separators, passwords, password hashes, filenames or
example records are learned or returned. The analyzer creates no files, logs,
Jobs, packs, remote requests or telemetry. Errors use fixed public codes/messages
and optional record numbers, without paths, raw values or foreign exception
causes/contexts. Controlled tracebacks never include plaintext messages. Python
cannot guarantee secure memory erasure; callers/debuggers can inspect their own
input buffers and stack locals. Original operator files are never deleted.

## Artifact contract and publication

ObservationReport records source, resource limits, extraction/privacy options,
schema/extractor/grammar/Unicode versions, the accepted year interval, input and
sample counters, suppressed/unrecognized counters and visible patterns. Each row
has a fixed non-secret ID, structure, occurrences, exact relative frequency and
an explicit reuse capability. Extraction rules and limitations are fixed text.

Imports reject unknown/missing fields, duplicate JSON keys/patterns, unknown
versions/shapes, inconsistent counts/denominators/IDs/capabilities, incorrect
numeric types, free text, malformed UTF-8 and artifacts above 16 KiB. Rendering
always follows validation and canonical reserialization; arbitrary input JSON is
never displayed as a report. Other numeric Unicode database versions may be
inspected, but reuse requires the current database version.
Binary streams are read to EOF with a 16 KiB + one-byte overflow probe;
short reads cannot hide trailing data or bypass the artifact limit.

`report_bytes()` generates deterministic ASCII-escaped JSON with a final newline,
without automatic timestamps. `save_report()` writes only validated aggregates
to a private temporary file, flushes/syncs and atomically links the complete
artifact to an absent destination. Existing files, symlinks and directories are
refused, including concurrent destinations; no overwrite option is introduced.
Failures/cancellation clean staging. Filesystems without hard-link support fail
explicitly. Raw input is never copied to staging. JSON artifact persistence is an
explicit operator action, outside routine Job storage.

## CLI and read-only Web

```sh
mimic patterns analyze --input authorized-local.txt --authorized --reference-year 2026 --output observed-patterns.json
mimic patterns analyze --input - --authorized --min-occurrences 5
mimic patterns show observed-patterns.json
```

Analysis is offline; stdin is explicit, never implicit. Without `--output`, only
aggregate JSON is printed. Show validates/reformats an existing artifact without
analysis or generation. Options expose bounded input configuration, reference
year and minimum occurrences. Argument errors suppress argparse's invalid-value
echo and re-raise status 2 outside its foreign exception handler, so controlled
tracebacks contain no private argparse context. Exit codes remain 0 success,
1 validation/input, 2 I/O. No raw/debug option
exists in this command family. stdout redirects remain an operator decision.

Web `/patterns` and `/patterns/ID` read validated `DATA_DIR/patterns/ID.json`.
The operator explicitly creates that folder and exports there through the CLI.
IDs are short lowercase ASCII filenames, without paths/extensions in the URL;
symlink folders/files are refused. Root and patterns directories are pinned by
no-follow directory descriptors; child reads use dir_fd rather than reopening
a path whose parent can be swapped after validation. Directory permission/read
errors are sanitized before reaching the Web logger. Trusted data-root ancestors
remain an operator/OS assumption. Platforms lacking the required descriptor and
no-follow capabilities fail closed for this viewer; CLI analysis remains separate.
Directory scanning is bounded at 64 entries,
artifact reads at 16 KiB, and ordering is lexical. Invalid files are not linked
or rendered. There is no server-side artifact import, password textarea, upload
handler, temporary password file, analyzer call or Job submission. Responses
use existing SSR, PT-BR/EN, theme controls, CSP and local cookie/CSRF behavior;
successful aggregate views use `Cache-Control: no-store`. Tables scroll locally
on narrow screens; long source identifiers wrap inside their cards. External
proxies or operator backups remain outside application guarantees.

## Explicit reuse through the existing Generator

`prepare_reuse(report, operator_request, enabled=True)` validates the report and
delegates exactly once to the existing GenerationService. Its result stream is
filtered by visible compatible structures using independently supplied operator
operands. No observed literal is available to copy into GenerationRequest,
Origin.value, Job snapshots or generation logs. Report source/version/aggregate
evidence remain separate from actual candidate origins and transformations.
There is no new score weight, synthetic transformation, mutation loop or sorting
by observed count.

The ten non-SPECIAL layouts correspond to existing bare Case/Affix outputs with
appropriate seeds, numeric operands and separators. SPECIAL without a numeric
token is analysis-only: the ordinary pipeline has no dedicated bare-special
suffix operation, and this Block does not manufacture empty operands or another
expansion path. Unsupported observations remain aggregate counts; suppressed
patterns are never applied. Existing policy, dedup and stage caps still apply.
Recognizing a shape guarantees neither coverage nor authentication success.

Filtering follows existing score-v1/Top-K. A finite budget may return fewer than
K matches, with original rank gaps; nothing is rescored or refilled. Warnings
make these limits explicit. PreparedGeneration and the filter share the normal
one-consumption contract. CLI/Web show never invoke this opt-in application API.
