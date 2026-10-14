# GATE 11 — Pre-Commit Observed Password Pattern Learning Audit

Date: 2026-10-13. Recommendation: **READY FOR COMMIT**, for operator review;
no commit, push or merge was performed. This is a local pre-commit audit,
not remote CI approval or release/platform certification.

## Baseline

Branch `feat/observed-password-pattern-learning`, HEAD
`5dbec469bdd002a381738ef827b9341c93ab0a7a`; required ancestry in main confirmed.
Initially seventeen changed/new files were present, with 1,216 tests passing
in **51.05 s** before production corrections. All initial changes were backed
up and hashed in a temporary evidence folder. The existing implementation report,
backlog, ADR, changed source/tests and relevant core/application/ranking/Job
contracts were inspected; their claims were tested against actual behavior.

## Actual architecture

The analyzer counts exclusive shapes in bounded local input, producing an
immutable report with fixed IDs, versions and aggregate evidence. It does not
construct Candidate/Origin/Transformation values from observed literals or
create Jobs, packs, databases or network calls. CLI analyze/show are explicit
adapters; Web reads aggregates only. Reuse is an application-only filter over
GenerationService/PreparedGeneration, after existing scoring and Top-K.

Candidate, Origin, Transformation, Seed, Generator, policy/first-cause dedup,
IntelligencePlan, GenerationRequest, score-v1 and RankingOptions retain the HEAD
implementation. No independent generation/mutation loop was found or added.

## Privacy threat model

Sensitive observations, malformed/untrusted aggregate files, accidental small
cohort disclosure, filesystem errors, directory/file substitutions and argument
errors were considered. Only unique fictitious sentinels and synthetic inputs
were used. Explicit source labels/output filenames are operator-supplied metadata
and must be non-sensitive. The configured data root and its ancestors are trusted;
this application does not defend against a fully compromised operator account.

Transient parsing memory is necessary. Absence of automatic raw persistence is
not secure memory erasure or anonymity. External debuggers, shell history,
operator backups, proxies and deliberate unsafe caller input are outside the
application's guarantees.

## Original-password leakage audit

Sentinels were searched in aggregate bytes/IDs, serialized candidate metadata,
normal/debug logs, stdout/stderr, controlled tracebacks, full HTML (including
hidden attributes), Job snapshots, remaining files and installed CLI/SSR output.
Analyzer output retains no literal words, numeric suffixes, separator values,
examples or password hashes. Generation uses independently supplied operands.

Two error paths did expose sensitive metadata before correction: directory errors
could reach the general Web exception logger, and sanitized argparse stderr still
had a private ArgumentError/ValueError chain attached to SystemExit. Both were
reproduced and corrected; fixed error messages/codes now reach those surfaces.
Caller stack locals/source code and intentionally sensitive explicit metadata
remain outside this guarantee.

## Suppression policy

Suppression occurs during report construction, not only rendering: counts below
the default five are removed from the pattern tuple. JSON/show/Web/reuse all
consume that same visible tuple. Counts 0, 1, 4, 5 and 6 were checked across all
four workflows, with identical decisions. Explicit `--min-occurrences` is
validated in 1–100,000, recorded and honored when inspecting an artifact.

Valid-sample denominators are not renormalized after suppression. Aggregate
suppressed occurrences/structure count remain visible. They are not a privacy
proof: complementary totals can reveal the remaining hidden family when eleven
of twelve are visible, and overlapping/differential reports can reveal hidden
counts. An audit case demonstrates that residual inference explicitly. Five
repetitions of one password meet the threshold; unique users/passwords are not
counted. ADR and the PT-BR/EN warning now state these limits without promising
perfect anonymization.

## Sensitive input handling

Authorization is checked before file lookup/read. Regular files are read lazily;
final symlinks, directories, FIFOs and non-regular descriptors are refused.
Limits are 64 MiB/100,000 records by default, 1,024 content bytes per record
(default; maximum 4,096), with bounded EOF/overflow probes. Empty input, malformed
UTF-8, NUL/control bytes, long records and byte/record ceilings are covered.

A midstream read error carrying a raw sentinel becomes a fixed read_failed error
without foreign cause/context or partial output. Keyboard interruption closes an
owned file stream and leaves only the original input. Caller-owned streams stay
caller-owned. CLI accepts explicit local relative/absolute paths; Web never
accepts arbitrary filesystem paths. No source material is copied into staging.

## Twelve-pattern grammar audit

Examples below are fictitious. Negative examples mean “not this structure”; some
are valid members of another family. All twelve positive/negative pairs were
executed with explicit minimum one for synthetic fixtures, confirming exactly
one classification per valid recognized observation.

| Canonical structure | Synthetic positive | Synthetic negative | Recognition/precedence |
| --- | --- | --- | --- |
| WORD | Olá | TI | Unicode letters/attached marks; acronym rule first |
| WORD + SPECIAL | Olá! | Olá!! | One allowed terminal special without digits |
| WORD + YEAR | Olá2026 | Olá7777 | Four ASCII digits in recorded interval |
| WORD + DIGITS | Olá7777 | Olá2026 | Numeric suffix; year classification first |
| WORD + SEPARATOR + YEAR | Olá@2026 | Olá@@2026 | One separator, then recognized year |
| WORD + SEPARATOR + DIGITS | Olá-7777 | Olá-2026 | One separator, then non-year digits |
| ACRONYM | TI | Ti | 2–12 uppercase letters, explicit spelling heuristic |
| ACRONYM + SPECIAL | TI! | Ti! | Acronym heuristic and one terminal special |
| ACRONYM + YEAR | TI2026 | Ti2026 | Acronym before WORD; YEAR before DIGITS |
| ACRONYM + DIGITS | TI7777 | TI2026 | Acronym with non-year numeric suffix |
| ACRONYM + SEPARATOR + YEAR | TI_2026 | Ti_2026 | Acronym, one separator, recognized year |
| ACRONYM + SEPARATOR + DIGITS | TI_7777 | TI_2026 | Acronym, one separator, non-year digits |

Only component kind/order, fixed ID and occurrence count are preserved. Word,
year/number, case spelling and actual separator/special literals are discarded.
Uppercase is not proof of a real acronym or organization identity. Long uppercase
words and one-letter values fall under WORD according to the recorded heuristic.

## Year and numeric classification

Defaults use fixed 1900–2099. An explicit reference year defines 1900 through
that year; the accepted configuration range is 1900–9999. Exactly four ASCII
digits within the interval are YEAR, otherwise DIGITS. This distinguishes 2026
from out-of-window 7777 without consulting the system clock or OS locale.

Existing and audit cases cover endpoints, out-of-range four digits, longer digits,
zero-prefixed numbers, initial numbers, repeated/prefix/suffix separators, dates,
letterless values, Unicode/accents/combining marks, Unicode digits, emoji and case.
The captured interval survives import and reuse preparation.

## Statistics and frequency correctness

The unit is a valid nonempty observation, including repeats, not a unique password
or number of matches. A nine-record fixture gives six valid observations, five
recognized, one unrecognized, one empty and two rejected (UTF-8/Unicode).
The two recognized rows have occurrences two and three, frequencies **2/6 and
3/6**, never 2/5 and 3/5. Below threshold, five occurrences in two hidden families
remain aggregate counters without visible rows.

Partitions were checked: sample + empty + rejected = physical records;
visible occurrences + suppressed occurrences = matched;
matched + unrecognized = valid sample. Zero denominators produce no pattern
frequency rows, not NaN/Infinity. Duplicates contribute repeatedly. Local sample
frequencies do not claim worldwide, Brazilian or corporate prevalence.

## Determinism

Complete artifact bytes match under PYTHONHASHSEED 1/42/777. Buffered underlying
chunks 1/7/64/8,192 and artifact short reads 1/7/97 produce equivalent results.
Non-BOM record reordering with identical physical size preserves complete bytes;
adding a terminal newline changes bytes_read by exactly one while other report
fields remain equal. A leading BOM is a file preamble and must remain first;
relocating it changes validity by the documented rule.

Rows use fixed grammar order, independent of ties and set iteration. Configuration,
Unicode database and grammar/extractor/schema versions are explicit; no automatic
timestamp or current date is part of the artifact. Cross-Unicode-version reuse
is rejected. Benchmark elapsed time is separate measurement metadata.

## Streaming and memory

Independent fresh-process measurements reproduce twelve structures:

| Observations | Analyzer time | Total two-pass benchmark time | Peak RSS | Peak traced allocations | JSON bytes |
| --- | --- | --- | --- | --- | --- |
| 10,000 | 0.0243 s | 0.1842 s | 24,184 KiB | 4,744 | 5,107 |
| 100,000 | 0.2350 s | 1.8612 s | 24,192 KiB | 4,712 | 5,148 |

RSS includes interpreter/imports; traced allocations exclude caller-owned input.
A tenfold increase added only eight KiB to observed peak RSS. Timing is a local
measurement, not a portable guarantee. The parser is linear in input length,
record length is bounded, and the counter map has exactly twelve keys. No
password/substring list, corpus-size dictionary, unbounded exact dedup or
catastrophic regex was found. The existing Generator's global dedup still grows
with generated candidates; it is separate from analyzer memory and unchanged.

## JSON schema and validation

Schema observed-patterns-v1/extractor pattern-extractor-v1/grammar
observed-shapes-v1 retain strict known fields, IDs, rows, counters, suppression
partitions and rational frequencies. Missing/additional fields, unknown versions,
wrong types/bools/floats, negative/non-finite values, duplicate keys/rows,
long/invalid source metadata, controls, malformed/deep JSON and invalid UTF-8
are rejected without input reflection. Other numeric Unicode versions can be
inspected but cannot be reused on a different Unicode database.

A demonstrated defect existed in the generic binary-stream importer: one short
read could reject valid fragments or accept a complete JSON prefix while ignoring
invalid/oversized trailing data. It now reads through EOF within a 16 KiB + one-byte
probe, without unbounded accumulation. Five regression cases failed before this
correction and pass afterward. Ordinary artifact bytes/schema remain unchanged.

## Artifact publication

Validated aggregate bytes alone enter a private temporary file. Publication
flushes/fsyncs and hard-links to an absent destination; existing files, symlinks,
directories and an input accidentally used as output are preserved. Forced write,
fsync, link and concurrent destination failures plus keyboard cancellation were
checked. Staging cleanup leaves no raw material; final publication never occurs
before a complete staged artifact is written.

Hard-link support is required. This does not promise power-loss durability of the
parent directory or recovery after SIGKILL; forcibly terminated staging would
contain only private aggregate JSON, not input observations. Publication folders
and their ancestors remain operator-controlled/trusted.

## Opt-in generation integration

Reuse requires explicit enabled=True and a selected validated report object.
Nothing is loaded implicitly. It delegates once to the existing service and filters
its result stream. Existing budget/caps/policy/dedup and metadata remain active;
unsupported and suppressed families are never synthesized. SPECIAL rows are
analysis-only; ten other families require compatible independently supplied operands.
No new generator, mutator, score weight or frequency ranking was found or added.

## Snapshot and artifact integrity

There is **no artifact path/reference in GenerationRequest or Job snapshots**.
Consequently no Job captures learned identity, digest or schema/extractor version,
and no external learned JSON is reopened during Job execution. Filtered reuse is
not a persistent/API Job feature. Submitting reuse.prepared.request produces
ordinary unfiltered generation; it must not be described as persisting that filter.

Application reuse holds an immutable fully validated ObservationReport. Replacing,
modifying in place or deleting its former JSON file after preparation has no effect
on results or canonical report bytes; all three scenarios were tested. Web is a
current-state inspection, not a historical Job snapshot. No-follow directory/file
descriptors now prevent parent/file substitution from redirecting a read. A
concurrent in-place writer can still change bytes during reading; strict JSON
validation applies, but historical content stability is not promised for such a
live view. Historical replay requires the retained aggregate object/configuration.

## Provenance

Aggregated evidence source/configuration/version/structure/count remains in the
report. Candidate origins and transformations describe independently supplied
actual operands; selection does not invent an observed-pattern transformation or
copy original observation values into Origin.value. Tests compare full metadata.
Observed structure, common weak value, service token and documented default
credential remain distinct categories, not evidence of successful authentication.

## Score-v1 and Top-K invariance

Scoring/ranking source is byte-identical to HEAD. There are no learned-frequency
bonuses. Budgets 1, 5, 20 and exhaustive were compared with the exact ordinary
service results, then filtered. Original scores, components, encounter order,
ranks and gaps remain intact. Policy/cap truncation cases retain old behavior.

This is **filter-after-Top-K**, not Top-K among matching candidates. It may return
fewer than K or zero despite matches outside the retained window, and does not
refill. That is the advertised explicit contract, not an undisclosed selection
change. Exhaustive mode remains encounter order without scoring.

## CLI commands

Real analyze/show and installed entrypoints were exercised, including help,
explicit stdin, valid/empty/malformed input, authorization refusal, minimum
suppression/override, output existing/symlink/concurrent failure, malformed/versioned
JSON and stdout/stderr. Messages remain English, JSON deterministic, exit codes
0/1/2 preserved. Root DEBUG logging reveals no input sentinel. The sanitized
SystemExit regression now has neither private argparse context nor cause.
Legacy and modern generation command outputs match the fresh required base.

## Web security

Web has only aggregate consultation; no plaintext analysis/upload workflow.
Invalid files/unknown fields/XSS/control metadata are not displayed, echoed into
hidden attributes or saved into uploads/Jobs. Artifact IDs cannot contain paths,
slashes/extensions or long identifiers. Valid entries are bounded/sorted, and
successful views use no-store plus existing CSP/nosniff/referrer protection.

A parent-directory substitution race was independently reproduced: after path
validation, a symlink swap redirected the selected read to a valid confidential
aggregate outside DATA_DIR. Corrected reads pin the trusted root and child
directories and resolve filenames relative to those descriptors, with no-follow
flags and regular-file verification. Directory errors also now become controlled
422 responses rather than raw general-logger tracebacks. Unsupported descriptor
platforms fail closed for the viewer; CLI and old generation remain separate.

## PT-BR/EN and responsive validation

Firefox 140.12.0esr independently passed the reported **24 combinations** of
two pages, PT-BR/EN, dark/light and actual content widths 375/768/1,440 px.
Real Tab actions moved focus to the next interactive element. Text contrast
measured at least **14.38:1** against panel backgrounds; inherited palette contrast
regressions also pass. Only same-origin assets load. Checks cover no page overflow,
no clipped 64-character metadata, no raw sentinel in full HTML/hidden attributes,
no upload control and no Jobs. Empty, suppressed and invalid states additionally
passed browser checks. Four 375 px screenshots were inspected/retained temporarily.

Translation catalogs stay at 544 matching keys. Only the existing Block 11 privacy
warning gained explicit comparative-inference wording; no key/count/framework,
CSRF, CSP, theme or layout system was added or broadly changed.

## Legacy byte compatibility

Fresh git archive of required HEAD was used to reproduce the sixteen reported
application scenarios and two CLI modes. All wordlist byte/order hashes,
candidate origins/transformations, score components/ranks, summaries, warnings,
request JSON and evaluated/emitted counts match. Cases include target/profile,
organization/context, leet/combine, Ready/Dataset/PT-BR, services/common values,
Seed/Ready packs, exhaustive/ranked output.

ACME + WordPress, 2026, partial leet still evaluates **159,175**, Quick retains
100. All seven service profiles, catalog/default credential source bytes, Core,
mutators, planning, packs and score-v1 are unchanged against HEAD.

## API/Jobs/persistence

Existing complete-suite cases cover old request JSON, preview, completion,
cancellation, pending cancellation, failure/cleanup, target snapshot edits,
restart/recovery and downloads. An additional audit case verifies that ordinary
API Job snapshots contain no learned artifact or observation sentinel and retain
unfiltered generation/download bytes across restart. Application reuse is tested
separately because it has no Job/API transport option. No SQLite migration or
snapshot field was added. Raw-sensitive observations never enter this flow by
analyzer action; normal generation operands remain the operator's responsibility.

## Wheel/sdist

Independent offline build from a fresh temporary source snapshot produced wheel
and sdist. The eight Block 11 production files match both artifacts byte-for-byte,
including analyzer, CLI, secure viewer/helper, template, translations and assets.
A fresh isolated virtualenv installed the wheel with no-index/no-deps and passes
pip check; execution occurred outside the checkout with installed module-location
verification. Installed analyze/show, refusal/exit codes, preserved destination,
invalid-version rejection and Quick output pass. Installed SSR/locale/CSP/assets
were exercised with already available optional Web dependencies and no network
installation. Existing license-table deprecation remains unchanged/out of scope.

## CI compatibility

Declared >=3.10 and Ubuntu CI's complete-suite 3.10/3.11/3.12 matrix remain
byte-identical to HEAD. Production syntax parses under Python 3.10 grammar;
standard POSIX directory APIs are available on the configured CI platform.
Local execution uses Python 3.13.5, pytest 9.1.1 and Unicode database 15.1.0.
No 3.10/3.11/3.12 interpreter run or remote CI approval is claimed. Those runs
belong to the subsequent operator PR. No test was removed or skipped and new
parametrization uses short explicit IDs, not embedded large payloads.

## Fixes made

| Finding | Severity and scope | Demonstrated failure | Minimal correction |
| --- | --- | --- | --- |
| Web parent substitution | High for the advertised aggregate confinement boundary; requires local directory manipulation | Outside valid aggregate rendered after directory symlink swap | Pin root/child descriptors; open relative child names; reject unsupported safe access |
| Directory error disclosure | Medium; controlled filesystem metadata/error path | Permission error reached 500/general logger with sensitive marker | Catch/sanitize filesystem errors before Web exception logging |
| Short-read import integrity | Medium; generic BinaryIO import, ordinary buffered file reads were unaffected | Valid JSON prefix accepted with invalid/oversized unread tail; valid fragments rejected | Bounded read-to-EOF and overflow probe; no schema/output change |
| Argparse exception disclosure | Medium; invalid private CLI arguments | Fixed stderr but private values retained in chained SystemExit traceback | Re-raise status 2 outside argparse's active exception handler |

All four were reproduced before production changes and have failing-before,
passing-after regression evidence. No extra grammar, frequency system, generation
path or broad cosmetic refactor was introduced. Documentation clarifies residual
inference and the application-only integration rather than overstating privacy
or historical Job determinism.

## Tests

Initial prescribed full suite: **1,216 passed in 51.05 s**. Final prescribed full
suite after all four fixes: **1,256 passed in 57.52 s**, including **40** new Gate
cases and all original 1,044 HEAD nodes plus the pre-Gate 172 Block 11 nodes.
Focused all-Block-11/Gate validation: **212 passed in 3.90 s**. JUnit has no
failures/errors/skips. The reproduction runs intentionally failed two confinement/
error cases, five partial-read cases and one argparse case before corrections.

```sh
PYTHONDONTWRITEBYTECODE=1 venv/bin/python -B -m pytest -q -p no:cacheprovider -ra --durations=25
```

TestClient runs outside the sandbox due its existing asyncio portal restriction;
no test logic was weakened. One browser execution approval review expired before
starting; the permitted retry succeeded. This timeout was not treated as a security
rejection or bypassed. Browser and build evidence stayed under /tmp.

## Remaining risks

No perfect anonymization/secure Python memory erasure; metadata, duplicates,
complementary/overlapping totals and operator disclosure can expose sensitive
aggregate facts. Unsupported layouts are unrecognized/analysis-only. Live artifact
in-place mutation is not historical content pinning. The filter has documented
Top-K underfill and is not transported into persistent Jobs. Trusted root/ancestor
permissions and filesystem hard-link/no-follow/descriptor support matter;
unsupported viewer platforms fail closed. Local Linux/Python 3.13 validation does
not replace the subsequent supported runtime matrix or broader platform review.
No uncorrected demonstrated Gate defect remains in the audited configuration.

## Diff summary

Gate changes are limited to the existing analyzer's bounded JSON reader, the
private CLI parser boundary, Web's confined descriptor reader/route, the existing
localized privacy warning, forty regressions in one new audit module, and audit
notes/report. Existing tests and all preexisting implementation/roadmap files
remain preserved. No Core, mutator, ranking, request/service, intelligence/catalog,
pack, API schema, Job, database, dependency, version or CI source change.

## Working tree final

Branch remains feat/observed-password-pattern-learning; HEAD remains
5dbec469bdd002a381738ef827b9341c93ab0a7a. Nineteen changed/new files are unstaged,
including the original seventeen, the new Gate test module and this report.
Canonical BACKLOG's roadmap 11–21 remains unchanged; only factual Gate status
was added. UTF-8/local links and tracked/new-file whitespace checks pass.
No real/customer password sample or temporary evidence is present in the intended
change set. Source fixtures are explicitly fictitious; runtime/build/profile/venv
artifacts remain outside the repository. No commit, push or merge. Block 12 has
not started.

## Recommendation

The four demonstrated defects are corrected and verified. The audited local
implementation is ready for the operator's commit/diff review, followed by the
normal manual PR and supported CI matrix. No publishing action was performed.

**READY FOR COMMIT**
