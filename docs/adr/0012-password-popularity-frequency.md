# ADR 0012: Local, qualified aggregate frequency knowledge

Status: implemented; Gate 12 audited, ready for operator commit review.

## Decision and boundaries

Block 12 adds `mimic.frequencies`, separate from generation, ranking, Seed/Ready
packs, observations, API requests and persistent Jobs. No generator, classifier,
production ordering option, network client, database table or dependency is added.
`score-v1` and Block 11 remain unchanged. Block 13 has not started.

The authoritative validator is `mimic/frequencies/models.py`; the packaged
`mimic/data/frequencies/frequency-knowledge-v1.schema.json` describes the JSON
shape and documents additional cross-field checks. No schema URL is fetched.
The twelve IDs come directly from Block 11 `ObservedPattern` and `SHAPES`.
There is no second parser. `from_observation` validates a Block 11 report and
copies only its visible aggregate rows, preserving its complete valid-sample
denominator, Unicode/extractor/grammar versions and year window. It does not
infer suppressed rows. Knowledge applies at least five occurrences even if the
original report deliberately used a smaller threshold. Empty/tiny samples below
five cannot become knowledge datasets.

## Immutable evidence and canonical identity

Frozen `FrequencySource`, `Measurement`, `FrequencyRecord` and `FrequencyDataset`
separate provenance from count evidence. Records hold a canonical ID and integer
count; their common exact denominator is the declared sample size. A derived
`Fraction` is available, while displayed evidence retains the original numerator
and denominator. The denominator includes unmatched, omitted and suppressed
observations. Exclusive row counts must sum to at most that denominator.

Measurement records counting unit (`observations` including repeats, or
source-declared `unique-passwords`), grammar, extractor, Unicode version, fixed
1900 year minimum, explicit maximum year and suppression threshold. Users and
successful logins are unsupported units. Deduplicated-source claims are operator
assertions; the layer cannot check a source's collection process.

Dataset identity is a bounded lowercase `id@version`. Deterministic sorted-key,
ASCII-escaped JSON with final newline is SHA-256 hashed over all validated
metadata and counts. Rows are canonicalized into grammar order. There are no
automatic timestamps, filenames, runtime Unicode defaults or floating-point
fields in persisted evidence. Input whitespace and row/property order do not
change canonical identity. Changing provenance changes the digest. Keep the
printed digest separately and use `--sha256` for an independent expected-content
check. A local envelope checksum is integrity detection, not a signature: an
operator who rewrites both data and checksum can replace the registry's evidence.

Strict import rejects unknown fields/versions, duplicate JSON keys/rows, invalid
IDs, contradictory units, unsupported grammar/extractor versions, invalid UTF-8,
non-finite numbers, floats/bools as counts, negative/overflowed counts and
partition violations. Counts are limited to signed 64-bit positive range;
zero is an explicitly reported zero, and positive rows below the threshold are
refused. Missing rows remain unknown, including possible suppression.
Unicode versions are explicit numeric triples; different versions can be
inspected but comparisons refuse numerical deltas across extraction contracts.

## Attribution, licensing and privacy

Required source fields are title, category (`synthetic`, `authorized-local`,
`published-aggregate`), methodology, attribution, license, explicit local-use
authorization, redistribution declaration, nonempty limitations and a non-sensitive
sample identifier. Collection bounds, population, geography, sector and reference
URL remain null when unknown. Geography/sector claims require explicit coverage
evidence. HTTPS reference URLs are validated for host/port/userinfo/control safety,
shown as escaped text and never fetched or loaded as resources. Dates are ISO
calendar dates; reversed known bounds are invalid. No population is inferred from
sample size or source title.

V1 deliberately supports only `CC0-1.0`, `CC-BY-4.0`, `LicenseRef-Local` and
`NOASSERTION`; this is a small declaration vocabulary, not a legal rights engine.
Redistribution is `permitted`, `forbidden` or `unknown`. Only the two recognized
public licenses can carry a permitted declaration; attribution is still mandatory.
Unknown/local-only licensing never implies redistribution rights. Import is an
explicit local-use action; it does not authorize publishing third-party data.
No repository license is applied automatically to external evidence.

Metadata is bounded (512 characters per prose field, eight limitations, short
identifiers); controls, format/surrogate characters and line separators are
rejected. The entire JSON input is bounded to 32 KiB, including short-read EOF and
one-byte overflow probing. Only twelve records exist. Free-form metadata requires
`metadata_non_sensitive: true`. The application cannot establish whether honest
looking text contains personal data, an organization name, an observation, a
hash or a sensitive URL. Operators must sanitize it before import: declarations
are not a DLP detector or source certification. Original input files are neither
copied into staging nor deleted. Invalid input, paths and foreign exceptions are
not reflected in fixed CLI/Web errors or chained controlled tracebacks.

Five repeated observations satisfy suppression; this is not five independent
people or passwords. Complements, overlapping sources, totals and successive
comparisons can reveal hidden cohorts. Aggregates and explicit metadata can be
sensitive. No anonymity or secure Python memory erasure is promised. No plaintext
credential dataset is bundled or automatically downloaded. Bundled fixtures A/B
are invented arithmetic aggregates, labeled synthetic and declared CC0-1.0; they
have no collected observations or empirical population claims.

## Local registry and publication

`FrequencyRegistry` uses existing `DataPaths` resolution and a private
`DATA_DIR/frequencies` folder, without changing DataPaths/SQLite contracts.
Each `id@version.json` is a single envelope containing version, canonical digest
and the full validated dataset; no second manifest can be partially published.
All reads pin the data-root and child directory descriptors, use relative names
and refuse symlinks/nonregular files. Directory scans are bounded to 128 entries
(including temporary/foreign entries) and fail explicitly on invalid/corrupt
entries, rather than silently presenting an incomplete healthy registry.

Import validates everything before creating directories. It writes aggregate
bytes only to a private random temporary file, checks the write, flushes/fsyncs,
then hard-links to an absent final name. Existing identities with identical
canonical content are idempotent; different content conflicts. Concurrent link
races revalidate the winner and never overwrite it. Exceptions and keyboard
interrupts remove staging. Filesystems/platforms without required POSIX directory,
no-follow and hard-link primitives fail closed. Root ancestors and operator
permissions are trusted. Concurrent imports near the cap can briefly exceed the
entry budget; subsequent bounded listing fails explicitly. No power-loss parent
directory durability or SIGKILL staging cleanup is promised. Abandoned staging
contains private aggregate evidence only. Digests pin loaded bytes, not the
truth of source declarations or historical stability of a mutable local registry.

## CLI and search

```sh
mimic frequencies example synthetic-a > synthetic-a.json
mimic frequencies example synthetic-b > synthetic-b.json
mimic frequencies --data-dir ./local-data import synthetic-a.json
mimic frequencies --data-dir ./local-data import synthetic-b.json
mimic frequencies --data-dir ./local-data list --query separator
mimic frequencies --data-dir ./local-data show synthetic-a@1
mimic frequencies --data-dir ./local-data verify synthetic-a@1 --sha256 EXPECTED_DIGEST
mimic frequencies --data-dir ./local-data compare synthetic-a@1 synthetic-b@1
mimic frequencies --data-dir ./local-data evaluate synthetic-a@1
```

The global `--data-dir` precedes the subcommand; default uses existing XDG rules.
Examples only print JSON and never import automatically. Show/verify include full
source context, exact unreduced fractions, content digest and privacy/methodology
warnings. List verifies all entries before applying bounded case-insensitive
metadata/canonical-pattern search. CLI JSON is deterministic; errors use fixed
messages. Exit codes: 0 success, 1 invalid data/conflict/incompatible comparison or
evaluation, 2 I/O/unsafe registry/integrity or sanitized argument errors. There is
no raw/debug mode, source download, source pooling or automatic generation option.
Shell redirection, history and explicit sensitive metadata remain operator concerns.

## Comparison semantics

Comparison records both full datasets and digests, all twelve rows in grammar
order, exact per-source fractions and exact right-minus-left rational deltas.
A missing row on either side yields no delta. Grammar, extractor, counting unit,
Unicode and year-window mismatches produce reasons with no numerical deltas;
CLI returns status 1. Unknown grammars are refused at import.

Population status is unknown, same declared scope or different declared scopes.
Different or unknown populations can still be displayed side by side, but
numerical deltas describe those two samples only. Sampling differences and unknown
fields are reported (methodology, category, period, population, geography, sector,
coverage evidence). Equal scope labels do not establish comparable recruitment,
representativeness or independence. Shared sample identifiers and identical
content trigger extra warnings; different identifiers never prove non-overlap.
There is no pooling, significance test, causal inference or universal ranking.

## Isolated synthetic evaluation

`synthetic-slot-coverage-v1` is a deliberately small foundation experiment.
Its fixed universe contains exactly twelve opaque slots, one per canonical shape;
it contains no password values and calls neither Generator nor the classifier.
The entire baseline order, universe, holdout observation indices, budgets and
fixture digest are emitted. Baseline is fixed grammar encounter order, not
score-v1. Experimental order puts reported shapes first by descending count
(one common denominator), then missing shapes; all ties preserve encounter order.
Explicit zero remains reported evidence and precedes missing evidence.

The holdout is separately specified in source as twelve observation indices and
is never derived from reference counts/results. Budgets 1/3/5/12 measure exact
weighted observation hits and rational coverage. Reference identity, digest,
measurement and full provenance are retained. Only declared synthetic references
with a different sample ID and the fixed fixture's observations/1900–2099/
Unicode 15.1.0 measurement contract are accepted. The symbolic fixture does not
require the interpreter's Unicode version, so it is reproducible across supported
runtimes. Matching these declarations cannot prove independence; copied/relabelled
fixtures are an operator threat. No method parameters are tuned against holdout
results; repeated use must not become test-set tuning.

This measures structural slot coverage, not real candidate recovery, password
success, or score-v1 quality. One candidate per family omits within-family
uncertainty and cannot justify production ordering integration. Robust comparison
against scored real candidate universes is deferred until independently authorized
holdouts and an appropriate evaluation design exist. No production ranking engine
or request/snapshot field is added to imply more mature evidence.

## Gate 12 audit clarifications

The fixed holdout puts all its mass on six even-index slots. The bundled
references assign their largest counts to slots also favored by that holdout;
this is a construction-sensitive arithmetic demonstration, not evidence of an
unbiased experiment or external validation. An opposite synthetic reference
makes budget-one coverage worse than baseline; equal counts reproduce baseline.
Independent construction cannot be certified from category/sample labels or
separately declared constants. No method was fitted during execution. No
real candidate Recall@K or operational improvement is established here.

Zero is a published exact zero. A positive count below the threshold is refused;
a suppressed Block 11 row stays omitted. V1 intentionally cannot distinguish an
undeclared family's absence from an originally suppressed family's absence after
bridging: that reason is unknown, and no hidden family ID/count is reconstructed.
Retain the original aggregate report when its suppression context is needed.
Complementary inference remains possible with additional external information.

Gate fixes guard standalone record ratios against incompatible denominators,
remove foreign filesystem context from concurrent publication conflicts, sanitize
unavailable descriptor scans/links and read-stream setup errors, and close an
owned staging descriptor if write-stream setup fails. Ordinary artifact bytes and
schema remain unchanged. See [Gate 12](../GATE12_AUDIT.md) for reproductions,
validation and the final recommendation.

## Read-only SSR

`/frequencies` provides bounded source/structure search; `/frequencies/id@version`
shows verified digest, exact counts, complete source context, limitations and
licensing. It shares PT-BR/EN catalogs, dark/light, local assets, escaping, CSP,
responsive tables and no-store. Metadata is data, never template code or external
resources. Invalid entries fail closed with a fixed 422 message, including errors
before the general Web logger. No Web import/upload, analysis, evaluation,
comparison endpoint or Job mutation is introduced. Comparison/evaluation remain
explicit CLI/application operations.

Validation, compatibility, performance and package evidence are recorded in the
[Block 12 implementation report](../BLOCK12_IMPLEMENTATION_REPORT.md). The complete
[Blocks 11–21 roadmap](../BACKLOG.md) remains preserved.
