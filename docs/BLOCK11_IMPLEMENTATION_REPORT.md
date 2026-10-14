# BLOCK 11 — Observed Password Pattern Learning Implementation Report

Date: 2026-10-13. Recommendation: **READY FOR GATE 11**, pending independent audit.

Gate 11 subsequently completed on 2026-10-13: four demonstrated defects were
corrected with 40 audit cases; the final suite passed 1,256 tests. See the
[independent Gate 11 audit](GATE11_AUDIT.md) for current commit readiness,
descriptor-based Web confinement, bounded short-read handling, sanitized
argparse exceptions and residual suppression risks. Measurements and the
17-file working-tree description below record the original implementation
handoff before that Gate; they are preserved as historical evidence.

## Baseline

Branch remains `feat/observed-password-pattern-learning`; HEAD remains
`5dbec469bdd002a381738ef827b9341c93ab0a7a`, the PR #13 merge. Its ancestry in
local main is verified. No branch was recreated and no roadmap patch reapplied.
The HEAD baseline passed 1,044 tests in a clean temporary archive. Before the
additional specification was implemented, the existing uncommitted Block 11
work passed 1,154 tests in 52.91 seconds using the prescribed command.

All preexisting changed files were backed up under a temporary evidence folder.
The prior draft implementation was extended; no operator changes were discarded.
The initial backlog decoded as strict UTF-8 without replacement characters.
Only factual Block 11 status was subsequently updated as requested; the complete
11–21 roadmap, previous audits and permanent constraints remain intact.

## Existing architecture

Core produces immutable Candidate values with actual Origin and Transformation
metadata. Seed supplies existing mutable/combinable capabilities. Domain planning
assembles the existing staged Generator; IntelligencePlan supplies bounded seeds
and numbers. GenerationRequest is the serializable application contract;
GenerationService prepares a one-use PreparedGeneration stream. RankingOptions,
score-v1 and Top-K retain their current budgets, scores and precedence.

CLI/Web remain adapters. Packs retain digest-pinned Seed/Ready behavior;
Jobs/persistence retain their existing snapshots/schema. Observation analysis is
isolated in `mimic/application/observations.py`; there is no alternative engine.

## Learning model

The analyzer counts a fixed set of structures from authorized local observations.
ObservedPattern contains immutable structure/count data and a derived fixed ID and
reuse capability. ObservationReport owns aggregate evidence source, sample size,
resource/privacy configuration, extraction rules and version metadata. Literal
observations, tokens, separators, examples and password hashes are absent.

No ML, LLM, semantic identity inference, password recovery, remote action or
success-probability model is implemented.

## Pattern grammar

Twelve structures combine WORD or ACRONYM with no suffix, SPECIAL, YEAR, DIGITS,
SEPARATOR + YEAR or SEPARATOR + DIGITS. DIGITS is the explicit numeric component
corresponding to the specification's conceptual NUMBER. Recognition is exclusive
and rows follow fixed grammar order, without frequency sorting.

WORD allows Unicode letters and attached combining marks. ACRONYM takes
precedence for 2–12 uppercase letters and is explicitly a spelling heuristic,
not a confirmed organizational acronym. No names or personal data are inferred.
Only one `@!#_.-` separator/special is recognized; its literal is discarded.
Numeric prefixes, multiword layouts, repeated/other special characters and other
unrecognized structures remain explicit aggregate counts.

## Year and numeric classification

Exactly four ASCII digits are YEAR only inside the recorded interval. Defaults
use fixed 1900–2099. `--reference-year 2026` explicitly selects 1900–2026;
configuration accepts reference years from 1900 to 9999. No system clock is read.
Other numeric suffixes, including out-of-range four-digit values, are DIGITS.
The interval and reference configuration roundtrip through the artifact.

## Input processing

CLI file input is explicit; `--input -` explicitly reads binary stdin. Authorization
is checked before consulting the source. Strict UTF-8 supports an optional initial
BOM, LF and CRLF; values are neither trimmed nor normalized. Invalid UTF-8 and
control/format/line-separator records are counted as rejected; empty records have
a separate counter. Space-only values count as valid unrecognized observations.

Limits default to 64 MiB, 100,000 records and 1,024 content bytes per record;
hard ceilings are 64 MiB, 100,000 records and 4,096 bytes. The grammar caps
structures at twelve and artifact size at 16 KiB. Input is consumed incrementally.
Limit failures return no partial report. A 16 MiB single-line fixture stops after
1,027 logically consumed bytes under the default limit. File buffering can
perform bounded read-ahead; caller-owned streams are not materialized or closed.

## Privacy guarantees and limitations

Analysis never creates a SQLite entry, Job, pack, temporary observation copy,
network request, telemetry event or raw-value log. Reports contain only validated
aggregate information. Errors and controlled tracebacks use fixed messages/codes,
without raw observations, operator paths or foreign exception chains. Invalid
CLI arguments and untrusted artifact fields are never echoed.

Source labels are explicit non-sensitive lowercase identifiers, defaulting to
`local-observations`. Original filenames are not inserted into artifacts. Pattern
rows below five occurrences are suppressed by default; operators can explicitly
configure a threshold from 1 to 100,000. Suppressed structures cannot be reused.

Aggregate counters/source labels can still be sensitive; this is not irreversible
anonymization. Raw observations exist transiently in Python memory; secure memory
erasure, debugger/caller buffers, shell history/redirection, external proxies and
operator backups are outside the application's guarantees. Original source files
are preserved. Operators must have authorization and keep explicit metadata safe.

## Duplicate handling

Repeated records count as repeated observations. No exact-dedup plaintext/hash set
or unique-password metric is maintained. Frequencies therefore do not estimate
unique users or unique values. This keeps analyzer memory independent of corpus
size, apart from one bounded record and fixed counters.

## Aggregate statistics

The report records physical lines/bytes, valid observations, rejected UTF-8/Unicode
records, empty records, recognized/unrecognized observations, distinct/visible
structures and suppressed occurrences/structures. Each visible pattern carries
occurrences and an exact relative-frequency numerator/valid-sample denominator.
The denominator includes valid unrecognized observations. Suppression never
renormalizes it. No local frequency is presented as population prevalence.

## Pattern artifact schema

`observed-patterns-v1` JSON includes source, limits, options, versions, year
interval, counters, twelve-or-fewer rows and fixed explanatory text. Row IDs derive
only from approved grammar names. There are no arbitrary example/free-text fields.
Serialized artifacts are bounded at 16 KiB (approximately 5 KiB for all twelve rows).

Import validates exact fields/types, duplicate JSON keys and rows, known versions,
counts and suppression partitions, sample denominators, IDs, capabilities and row
order. Unknown fields, malformed/deep/oversized JSON, raw-password payloads and
inconsistent metadata are rejected without reflection. Canonical reserialization
produces deterministic ASCII-escaped JSON and a final newline.

## Versioning

Schema `observed-patterns-v1`, extractor `pattern-extractor-v1`, grammar
`observed-shapes-v1`; the Unicode database version and extraction configuration
are explicit. Unknown schema/extractor/grammar versions fail closed. Artifacts
with a syntactically valid different Unicode database version can be inspected,
but reuse requires the current runtime's Unicode database version. No automatic
timestamp enters artifacts. This is the first unreleased artifact contract;
earlier uncommitted draft JSON is not a released migration contract.

## CLI analyze/show

```sh
mimic patterns analyze --input synthetic-password-sample.txt --authorized --reference-year 2026 --output observed-patterns.json
mimic patterns show observed-patterns.json
```

Analyze supports source label, bounded input limits, explicit reference year,
minimum occurrences and output destination. With no output file, only aggregate
JSON goes to stdout. Show validates and displays an existing aggregate without
starting analysis or generation. Messages remain English; codes remain 0 success,
1 input/validation, 2 I/O. There is no raw/debug output option.

Publication stages a private complete aggregate, flushes/syncs, then atomically
links it to an absent destination. Existing files/symlinks/directories, including
an input accidentally chosen as output, are preserved. Write/link failures and
cancellation remove staging. Filesystems without hard links fail explicitly.

## Web integration

Existing SSR now provides `/patterns` and `/patterns/ID`, linked from navigation.
The operator explicitly exports validated aggregates to the configured data
folder's `patterns/ID.json`; the application creates no artifact directory by
viewing it. Directory listing is bounded at 64 entries; filenames are confined
to short lowercase identifiers and symlink directories/files are rejected.

Only validated aggregates are listed/rendered. Successful views are `no-store`.
There is no password textarea, upload, analysis route, persistent import, raw
request-body processing or Job submission. This deliberately keeps sensitive
sample analysis in the CLI while providing aggregate consultation on the Web.
Existing CSP, locale preferences, CSRF controls and theme behavior are retained.

## Integration with existing Generator

The application-only `prepare_reuse(report, operator_request, enabled=True)`
delegates once to GenerationService and filters its existing result stream by
visible compatible structures. The request uses separately supplied operator
operands; none are extracted from observed passwords. There is no mutation loop,
second generator, new source option or automatic Web/CLI generation action.

## Supported and unsupported learned structures

Ten non-SPECIAL shapes correspond to existing bare Case/Affix outputs given
compatible operands and options. Recognizing them does not guarantee coverage:
existing policy, stage caps and available numbers/separators still constrain output.
SPECIAL without a number is explicitly analysis-only; no new mutator, empty-token
hack or simulated expansion is introduced. Unrecognized and suppressed structures
are never manufactured or applied.

## Provenance

Report source, extractor/configuration, sample denominator, structure ID and
occurrences describe aggregate evidence. Candidate Origin/Transformation values
remain their actual independent generation causes. No observed password is copied
into Origin.value and no fictitious observed-pattern transformation is appended.
Observed evidence, common weak values, service tokens and documented credential
pairs remain distinct claims. An observed format is not an authentication result.

## Score-v1 invariance

No scoring/ranking code or weights change. Sample counts do not grant a bonus.
The explicit structural filter runs after existing Top-K: output can be below K
and original rank gaps remain. Nothing is rescored, refilled or globally reprioritized;
the reuse warnings and ADR document these consequences.

## Request/Job compatibility

GenerationRequest serialization, GenerationService, PreparedGeneration, JobManager,
API request schemas, SQLite schema and pack snapshots are untouched. Artifacts
are explicitly saved aggregate files, outside routine Job storage. Legacy Job
roundtrips remain covered by the original suite. New privacy tests confirm that
artifact consultation/rejected Web requests create no Jobs/uploads and place no
synthetic raw sentinel into other persisted files.

## Determinism

Complete artifact bytes match under PYTHONHASHSEED 1, 42 and 777. Input buffered
through underlying chunks of 1, 7, 64 and 8,192 bytes produces the same artifact.
Exclusive grammar precedence, fixed row ordering, exact rational frequencies,
version metadata and absence of timestamps remove hidden nondeterminism.
Original generation determinism tests also pass. Benchmark timing is deliberately
non-deterministic measurement metadata, separate from learned artifacts.

## Legacy byte compatibility

Sixteen application scenarios against HEAD compare wordlist byte/order hashes,
full candidate origins/transformations/score/rank metadata, counts, warnings,
request snapshots and summaries. All match. Legacy and modern CLI output hashes
also match. Cases cover target/context/organization, Case/Leet/Combine,
Ready/Dataset/PT-BR, services/common values, Seed/Ready packs and ranked output.

ACME + WordPress at reference year 2026 with partial leet still evaluates
**159,175** candidates; Quick still retains **100**. All seven existing service
profiles, catalog bytes and two documented credential pairs remain unchanged.

## Performance

Repository benchmark: `venv/bin/python -B -m benchmarks.observed_patterns`.
It generates an O(1)-memory synthetic source, measures elapsed time and allocation
peak in separate runs, and emits only non-sensitive metrics.

| Synthetic observations | Structures | Time | Peak Python allocations | JSON size |
| --- | --- | --- | --- | --- |
| 10,000 | 12 | 0.0561 s | 4,824 bytes | 5,107 bytes |
| 100,000 | 12 | 0.2358 s | 4,792 bytes | 5,148 bytes |

Allocation peaks exclude caller input and total process RSS. Times are local
measurements, not a portable performance guarantee. Recognition has no quadratic
password dedup/list retention. Generation's disabled-observation hot path is
unchanged; five exhaustive runs per snapshot produced the same 159,175 count,
with medians 1.0464 s base / 0.9848 s current and max RSS 53,724 / 53,568 KiB.
Host load/cache variation prevents attributing that timing difference to a speedup.
No material regression was observed.

A separate three-record synthetic training fixture and eight-record holdout have
six supported observations covered by the learned structure families, with two
unrecognized. The **6/8 structural coverage** is only a small development baseline,
not Recall@K, password recovery, population frequency or authentication success.
No real/leaked corpus is used. This prepares future measurement without starting
Block 12 or implementing the full Block 16 benchmark system.

## Security tests

Tests cover authorization-before-read, strict Unicode/UTF-8/BOM/CRLF, malformed
bytes, controls/bidi, ambiguity/year boundaries, limits, huge records, duplicates,
small-sample suppression, schema/type/version/duplicate validation and deterministic
serialization. Synthetic sentinels are searched in aggregate JSON, logs, controlled
tracebacks, errors, Web responses and persisted files other than the original
synthetic input. Tests cover original file preservation, private permissions,
symlink/FIFO/directory rejection, atomic publication failures/cancellation cleanup,
no automatic analysis/generation/Jobs and filtered score/provenance preservation.

## PT-BR/EN and responsive validation

Translation catalogs contain **544 matching keys**: 512 original plus 32 pattern
labels, with original text preserved and existing placeholder/parity tests passing.
The one Gate 10 fixed-count assertion was updated to the new explicit total;
no regression assertion was removed. The old literal-template test detected two
unlocalized labels; implementation was corrected and the test remained unchanged.

Firefox 140.12.0esr passed **24** combinations: two pages, PT-BR/EN, dark/light and
375/768/1,440 px actual content viewports. Checks cover visible headings, correct
locale/theme, no page overflow, no clipped source metadata, no raw sentinel,
no upload control and no Jobs. Native headless windows have a minimum width;
Marionette controlled browser content width and verified actual innerWidth.
Screenshots at 375 px were inspected; long source labels now wrap inside cards.
The pattern table uses existing local horizontal scrolling and semantic headings.
CSP, CSRF preference tests, keyboard controls and existing theme tests pass.

## Package installation

Wheel and sdist were built offline with `build --no-isolation` from a temporary
source snapshot. All eight changed/new production files match both artifacts
byte-for-byte, including the new template and analyzer. No dependencies, build
configuration, Python requirement, version or CI matrix changed.

A fresh temporary virtualenv installed the wheel with `--no-index --no-deps`,
passed `pip check` and imported from the installed location outside the checkout.
Installed CLI analysis/publication/show, authorization refusal, refusal to overwrite
and legacy-compatible Quick generation were validated. Optional Web installed
smoke uses already available Web dependencies, without new network installation.
The existing setuptools license-table deprecation warning remains outside scope.

## ADR and Backlog

[ADR 0011](adr/0011-observed-password-pattern-learning.md) describes grammar,
algorithm/precedence, privacy/retention, bounded I/O, artifact versions, integration,
unsupported capabilities and future frequency separation. [BACKLOG.md](BACKLOG.md)
now records implementation with Gate 11 review pending; the prior 11–21 roadmap,
audit history and permanent constraints are preserved. README is unchanged.

## Tests

Runtime: Linux, Python 3.13.5, pytest 9.1.1, Unicode database 15.1.0.
The final prescribed full command passed **1,216 tests in 56.07 s**:

```sh
PYTHONDONTWRITEBYTECODE=1 venv/bin/python -B -m pytest -q -p no:cacheprovider -ra --durations=25
```

All 1,044 HEAD test nodes are retained; 172 Block 11 nodes are added. Focused
validation passed 173 cases, including one existing locale regression. After the
localization correction, its existing test and the Web tests passed separately.
No tests are skipped/weakened. Existing TestClient needs execution outside the
sandbox in this environment; no product/test logic was changed to avoid it.

Python 3.10 syntax parsing passes across production Python modules; the declared
`>=3.10` requirement and CI 3.10/3.11/3.12 matrix remain unchanged. Those interpreters
are unavailable locally; runtime matrix execution remains an independent Gate/PR
check. No new remote CI success is claimed.

## Remaining risks

Aggregate disclosure and explicit metadata remain operator decisions. Small
samples are suppressed conservatively but not guaranteed anonymous. Grammar
coverage is deliberately narrow and uppercase acronyms are heuristics. Unicode
version differences prevent reuse until compatible. Filtering after Top-K can
underfill output. No-follow and hard-link support varies by filesystem/platform;
Linux was validated, other supported platforms need independent checks. Full
Python runtime matrix and independent Gate 11 audit remain pending.

## Diff summary

Production: one new application analyzer/artifact module, CLI analyze/show,
read-only Web artifact helper/routes/template, 32 translations, a navigation link
and one scoped source-label wrapping rule. No Core, mutator, scoring, generation
request/service, intelligence/catalog, pack, API schema, Job or database change.

Validation/documentation: four Block 11 test modules, one existing translation
count update, a small synthetic benchmark, ADR 0011, this report and factual
backlog status. Git's tracked diff includes the preserved earlier roadmap update;
new files remain untracked until the operator reviews/stages them.

## Working tree final

Branch `feat/observed-password-pattern-learning`; HEAD
`5dbec469bdd002a381738ef827b9341c93ab0a7a`. Seventeen changed/new files, all
unstaged; no commit, push or merge. The working tree intentionally contains both
the preserved roadmap and Block 11 implementation. Temporary test/build/browser
evidence is outside the repository. `git diff --check` and equivalent whitespace
checks on new files pass. Block 12 has not started.

## Recommendation

Implementation matches the supplied Block 11 specification and is ready for
independent Gate 11 review, with the runtime/platform checks above clearly pending.
This is not Gate approval or remote CI/release completion.

**READY FOR GATE 11**
