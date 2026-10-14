# GATE 12 — Pre-Commit Password Popularity & Frequency Audit

Date: 2026-10-14. Local adversarial audit and recommendation for operator review.
No commit, push, merge, remote CI approval or release certification. Block 13 and
the compound corporate-name improvement were not started.

## Baseline

Branch `feat/password-popularity-frequency`; unchanged HEAD and required main:
`aa18849234778aed63d95477054b8c27fe17b1da`. Required ancestry is confirmed.
The initial 23 changed/new files were unstaged; all were copied and SHA-256
recorded under temporary evidence before corrections. No operator work was discarded.

The implementation report, ADRs 0011/0012, BACKLOG, every new frequency module,
resource, test and adapter change, observations, generation/request, DataPaths,
packs, ranking, API and Jobs contracts were inspected against the actual code.
The prescribed initial full suite passed **1,371 tests in 57.80 s**, before code
changes. The original implementation report remains historical evidence with a
prominent Gate follow-up; the complete Blocks 11–21 roadmap is preserved.

## Actual architecture

`mimic.frequencies` owns bounded immutable aggregate knowledge, local registry,
comparison, a synthetic experiment and a lazy CLI adapter. Web consults this
registry through existing SSR. It does not produce Candidate/Origin/Transformation,
classify observations, construct generation requests or submit Jobs. Pattern IDs
come from Block 11's twelve existing shapes. No second parser, generator,
mutator, production ranking engine, database, network client or telemetry exists.

## Frequency model

Source metadata and measurement are separate from frequency records. Dataset ID,
version and canonical digest cover source attribution, license/declarations,
methodology, optional period/population/coverage, limitations and exact counts.
Unknown optional properties remain null. Units explicitly distinguish repeated
observations from source-declared unique passwords; users/logins are unsupported.
Grammar/extractor, Unicode, 1900 lower year bound, upper year and threshold define
the measurement contract. Source assertions cannot prove actual collection quality.

## Mathematical correctness

Independent fixtures verify `5/7`, explicit `0/7`, a residual two unspecified
observations, and `6/10 - 5/7 = -4/35`. Denominators are never renormalized to the
sum of visible records. Exclusive counts must sum to at most sample size; rejected
cases cover negative/zero/tiny denominators, bools/floats, invalid counts and
signed 64-bit overflow. The maximum permitted count/denominator yields exactly 1.
Arithmetic uses integers/Fraction, with unreduced count/sample evidence retained.

A standalone helper defect did allow a valid row of 30 to be paired with a
separate measurement of 5, returning 6. Its new guard rejects a non-Measurement
argument or count above denominator. Imported datasets already enforced this
invariant; no valid imported CLI/Web distribution was demonstrated incorrect.
Unique-password measurements retain that unit rather than becoming people or
login attempts. Actual source deduplication cannot be certified from aggregates.

## Zero versus missing versus suppressed

Explicit zero is a real published row (`0/100`), and comparison retains it as
zero evidence. A missing row yields null evidence/no difference, and is omitted
from detail tables; it is never imputed as zero. A positive row below threshold is
rejected. Block 11's suppressed positive rows stay omitted when bridged.

V1 intentionally does **not** transport a per-family reason for omission. After
bridging, undeclared versus originally suppressed absence is unknown. CLI/Web
say this rather than inventing a suppressed family identity. Original aggregate
reports must be retained when their suppression context matters. Distinguishing
zero from absent evidence is supported across JSON/CLI/comparison/Web; recovering
three labeled per-family states would require information Block 11 deliberately
does not disclose, and is not claimed by this audit.

## Provenance and licensing

Required title, category, methodology, attribution, sample identifier, limitations,
local-use authorization and redistribution declarations are validated. Optional
period and coverage remain unknown unless declared; geography/sector require
supporting coverage text. A large sample establishes no representativeness.

CC0-1.0/CC-BY-4.0 can declare permitted redistribution; NOASSERTION/LicenseRef-Local
cannot. Forbidden and unknown remain distinct, including a recognized public
license with a conservative forbidden declaration. Attribution remains required.
These are operator declarations, not legal certification or source authentication.
Both bundled fixtures are invented, explicitly synthetic CC0 aggregate arithmetic;
no empirical leaked/password/hash corpus is bundled or downloaded.

## Schema/versioning

The `frequency-knowledge-v1` packaged schema agrees with actual property sets,
required metadata, twelve canonical IDs, units and principal limits. The Python
validator supplies explicitly documented checks JSON Schema alone does not express:
strict duplicate keys, Python integer types, partition/threshold relationships,
Unicode categories, URL details, date order and byte ceilings. The schema is a
structural description, not a substitute for application validation.

Unknown schema/grammar/extractor versions, unknown/duplicate IDs, extra/missing
fields, wrong types, bools/floats, NaN/Infinity, overflow, truncation, trailing
JSON/text/NUL/BOM, invalid UTF-8, deep/oversized arrays/objects and hostile metadata
are rejected. Other declared numeric Unicode versions may be inspected but are
incompatible for numerical comparison. These checks do not silently migrate data.

## Canonical JSON/SHA-256

Field order, record order, JSON whitespace and equivalent Unicode escaping
produce identical canonical bytes/digests. Different code-point spellings are
not normalized. Changes to counts, denominator, license, source, version, period
or limitations change identity; unsupported grammar changes are refused outright.
No clock or automatic timestamp participates.

The complete validated model is serialized with sorted keys, fixed grammar order,
ASCII escaping and final newline. Source input is bounded to 32 KiB; canonical
output is also bounded before staging. A compact non-ASCII input whose expanded
canonical form exceeds the limit is refused before registry creation.

A self-consistent replacement of data **and** its stored checksum is accepted
without an independent pin, as expected. An externally retained `--sha256` rejects
that replacement. SHA-256 checks expected content, not source truth/authenticity.
Loaded immutable objects remain stable after file modification or deletion.

## Privacy threat model

The audit considers untrusted aggregate JSON/metadata, malformed arguments,
filesystem errors, small cohorts, symlink/parent substitution, corruption and
concurrent publication. Only fictitious sentinels and small synthetic inputs were
used. Configured root/ancestor permissions and operator account integrity remain
trusted. This is not protection against a fully compromised operator account.

Transient parsing and explicit aggregate publication are necessary. Python memory
erasure, external debuggers/caller locals, shell history, operator backups, proxies
and deliberate sensitive metadata are outside the application's guarantees.
Suppression, checksums and aggregation are not anonymity or authenticity proofs.

## Metadata exposure

Invalid fields and private path/error markers were checked against CLI stdout/
stderr, controlled exception chains, DEBUG/captured logs, full HTML, remaining
staging, registry JSON and Job snapshots. Rejected input is never copied to staging.
Fixed errors do not echo rejected fields or source filenames. Accepted metadata
is intentionally displayed/stored, so `metadata_non_sensitive: true` is an operator
responsibility, not a DLP classifier. HTTPS references are escaped text, never
fetched or loaded as resources. No automatic source filename is retained.

Two filesystem error paths reached foreign exceptions/Web logging before fixes;
a concurrent conflict also retained FileExistsError as context. Reproductions and
regressions now confirm fixed public errors without that marker/context. Caller
source lines/locals and intentionally sensitive accepted metadata remain outside
this guarantee. No raw original observation was added to package resources or Jobs.

## Block 11 bridge/suppression

`from_observation` revalidates the complete serialized ObservationReport, preserves
valid-sample denominator and grammar/extractor/Unicode/year contract, copies only
visible rows, and applies `max(5, original_threshold)`. Synthetic counts 0/1/4
cannot become tiny knowledge samples; 5/6 remain exact. A source threshold of seven
keeps a six-occurrence family hidden and preserves an eight-occurrence family.
Invalid report partitions are refused. No observation literal is copied.

A complementary-inference fixture has eleven visible families of five and a last
family of four, with externally known zero unmatched observations. The residual
59 minus 55 reveals four; the hidden ID/count are still not exported individually.
The application cannot prevent this external inference. Neither suppression nor
repetition counting establishes five distinct people/passwords or anonymity.

## Registry filesystem security

Reads pin root and child directory descriptors, then open relative validated
filenames with no-follow/nonblocking and regular-file checks. Missing/corrupt/
modified entries, traversal, file/directory symlinks, FIFOs, unsafe names and
permission/read failures are refused. A selected read remains on its pinned
folder after a parent swap. Publication likewise stays in the original pinned
folder and does not write into the replacement symlink destination.

Live in-place content mutation is not historical snapshotting. Strict parsing
and checksum validation apply to bytes read; an independent digest is needed for
an expected historical object. No stronger concurrent-writer authenticity claim
is made. Platforms missing required primitives fail without an unsafe fallback;
unsupported scans/links now use controlled errors instead of raw exceptions.

Directory scanning stops at 129 probes and refuses more than 128 entries. Temporary
entries count toward that limit; import reserves one slot for staging, so a
sequentially filled registry admits at most 127 final files through this method.
Existing identical identities remain idempotent at the directory limit. One corrupt
or foreign invalid entry can block the entire list/search/Web view; this deliberate
fail-closed behavior is documented. Direct get verifies the selected identity.

## Atomic publication

Validation and canonical-size checks finish before directory creation/staging.
Only aggregate evidence enters private mode-0600 staging. Checked writes,
flush/fsync and a no-overwrite hard link publish one complete envelope containing
both evidence and digest. Existing destinations are preserved; identical imports
are idempotent, differing identities conflict, and concurrent winners are rechecked.

Short writes, open/write/fsync/link failures and keyboard interruption leave no
partial final file; owned streams close and normal staging cleanup runs. A failed
write-stream setup previously leaked its opened descriptor despite unlinking the
stage; explicit ownership transfer/cleanup now closes it. Parent-directory crash
durability, forced termination cleanup and an OS refusing cleanup are not promised;
abandoned staging contains only private aggregate evidence. No raw source is staged.

## Dataset comparison correctness

For compatible contracts, exact per-source fractions and `right - left` deltas
match manual calculations. Missing evidence on either side prevents a delta;
explicit zero remains comparable. Grammar order fixes all twelve output rows.
Unit, Unicode or year-window differences explain incompatibility with no numerical
deltas; unsupported grammar/extractor versions are refused at import. Both full
source objects and digests remain visible. No pooling, frequency rank, significance
test or authentication-success probability is constructed.

## Population and overlap limitations

Same, different and unknown declared populations are correctly distinguished.
Differences/unknowns in methodology, period, category and coverage are reported.
Matching scope labels do not prove equivalent recruitment or representativeness.
Sample-ID equality adds an overlap warning; different IDs do not prove independence.
Identical evidence is not independent replication. Numerical contrasts describe
those samples only; no transfer to regions, sectors or universal populations is
justified. Comparisons may themselves expose small-cohort information.

## Synthetic evaluation methodology

`synthetic-slot-coverage-v1` operates on exactly twelve opaque declared slots.
The baseline is grammar encounter order, **not score-v1**. Experimental order uses
descending reported counts, with stable encounter ties and all missing rows after
reported rows, including explicit zeros. Budgets are 1/3/5/12. On bundled A, manual
baseline/experimental hits are `(2,2), (5,8), (8,8), (12,12)` out of twelve;
experimental coverage at three is exactly 2/3. Equal counts reproduce baseline.

Construction bias matters: holdout mass lies only on six even-index slots, and
bundled references favor slots also favored by that holdout. Ranking an odd slot
first gives **0 versus 2** hits at budget one. This is a toy arithmetic/correctness
demonstration with a favorable fixture, not unbiased evidence of efficacy.
Structural slot coverage is not real-candidate Recall@K, recovery, operational
improvement or a production ranking recommendation. No Block 16 expansion was made.

## Holdout separation

Reference identity/digest/full measurement, fixed universe, holdout observation
indices, budgets, fixture digest, both orders and exact hits/fractions are emitted.
Holdout constants are not derived from an evaluation call's counts/results;
incompatible units/year/Unicode and non-synthetic/same-sample references are refused.
The fixed symbolic Unicode contract does not consult runtime classification.

Separate constants, category labels and different IDs cannot certify independent
construction or prevent copied/relabelled holdouts. Historical independence cannot
be proven from these declarations. Repeated evaluation must not become tuning.
The ADR now states this construction-sensitive limitation explicitly. No claims
of robust real-password effectiveness or score-v1 superiority remain.

## CLI

Twenty-nine installed real entrypoint commands reproduce help, required example
name, synthetic export, valid/invalid/idempotent/conflicting import, search, show,
verify with/without/correct/incorrect external pin, compatible/incompatible compare,
supported/rejected evaluation, custom data root, missing data and private paths.
`example` requires `synthetic-a` or `synthetic-b`; omission deliberately exits 2.
`--data-dir` precedes its subcommand, matching actual help and ADR examples.

Status 0/1/2 behavior remains documented: incompatible comparisons return 1 with
reasons; I/O/integrity/unsafe filesystem and syntax errors return 2. Sanitized
argument errors have no private argparse exception context. JSON is deterministic;
show/verify retain source/license/limitations, exact denominators and digest status.
No parallel CLI, raw/debug option, implicit import or source download was added.

## Web

`/frequencies` and `/frequencies/id@version` remain read-only registry inspection.
All selected content is validated before rendering. Escaping handles hostile prose;
invalid/corrupt entries and filesystem failures yield a fixed 422 before general
exception logging, including the newly covered stream-setup/unsupported-scan errors.
CSP and no-store remain in place; reference URLs stay text. No arbitrary filesystem
path, password upload, generation action, new API endpoint or Job option exists.

Zero/unknown/licensing/limitations are visible as documented. Missing positive
suppressed rows do not become zero rows. A separate ordinary API Job after registry
consultation has no frequency identity/metadata and retains normal download bytes
across restart. No uploads are created by this area.

## PT-BR/EN and responsive validation

Firefox **140.12.0esr** independently passes all **24 combinations** of listing/
detail, PT-BR/EN, dark/light and actual 375/768/1440 px content widths. Near-maximum
prose and a long HTTPS reference wrap without page overflow or clipped metadata.
Native Tab moves from search to its button in every case. Sampled text contrast
is at least **6.15:1**. Resource requests are same-origin; there are no uploads or
Jobs. Four 375 px screenshots were retained temporarily, with a full-page screenshot
visually inspected. This Gate did not redesign CSS or templates.

All **574** PT-BR/EN keys match, with equal placeholder sets. Existing locale/theme/
accessibility checks also pass in the complete suite. Installed SSR verifies locale,
CSP, no-store and local static assets outside the checkout.

## Generation isolation

Core, mutators, GenerationService/GenerationRequest, domain/intelligence planning,
observations, packs, API, Job manager/snapshots, persistence and CI source remain
byte-identical to required main. Importing/listing/comparing/evaluating frequency
knowledge does not change a later generation. Fresh ordinary generation processes
never import `mimic.frequencies`. There is no automatic dataset selection or bonus.
The corporate-name improvement and Block 13 remain untouched.

## Score-v1 invariance

RankingOptions, scoring weights/components, score-v1 and Top-K source are unchanged.
Candidate scores, rank gaps, budgets, encounter order and provenance remain equal
to required main in historical comparisons. Experimental slot ordering never calls
or modifies production scoring. Neither heuristic scores nor empirical proportions
are represented as probabilities of authentication success.

## Historical regression comparisons

A fresh archive of required main and the final working tree reproduce all sixteen
application scenarios and two legacy/modern CLI modes. Wordlist bytes/order, full
Origins/Transformations, scores/components/ranks, warnings/summaries, request JSON
and evaluated/emitted counters match exactly. Cases include target/context,
organization, leet/combine, Ready/Dataset/PT-BR, service/common values, Seed/Ready
packs and exhaustive/ranked output. ACME + WordPress/year 2026/partial leet remains
**159,175 evaluated**, with **100** retained by Quick. Existing Job lifecycle,
restart/download and observation suites remain passing and unchanged.

## Determinism

Complete artifact bytes/SHA-256, comparison/evaluation evidence and tie handling
match PYTHONHASHSEED **1/42/777**, including missing/zero rows, equal counts,
combined Unicode metadata and reordered serialization. Canonical resource bytes
are unchanged by Gate fixes. There is no runtime clock or external-source input.
All **1,371** initial node IDs are retained; **43** new Gate cases have a maximum
node-ID length of **111** characters, without embedded large payloads.

## Performance

The 1,629-byte synthetic fixture gives local medians: fresh import **0.1572 ms**
(20 runs, 14,792 peak traced bytes), idempotent import **0.2199 ms** (100 runs),
externally pinned verification **0.1640 ms**, load **0.0567 ms**, compare
**0.1573 ms**, evaluation **0.0751 ms** (200 runs each). Corresponding verify/load/
compare/evaluate traced peaks were 42,182/39,929/8,654/6,720 bytes.

Five-run verified list medians at 1/64/120 datasets were **0.1356/6.5120/12.2059 ms**;
traced peaks were 41,704/224,756/381,027 bytes. Whole-process observed peak RSS
was 26,940 KiB. Limits bound input/canonical bytes, rows, metadata and registry
entries; there is no corpus-sized password map, unbounded classifier or regex.
These small Linux measurements are descriptive, not portable performance promises.

Five alternating fresh-process main/final generation pairs retain 159,175 candidates
with median wall times **1.1259/1.0279 s** and CPU times **1.1257/1.0274 s**.
No slowdown was reproduced and no speedup is claimed. Generation source is unchanged;
knowledge was not imported in any ordinary generation process. No optimization
was made to chase timing noise.

## Wheel/sdist installation

Offline build from a fresh temporary final source snapshot produces wheel/sdist.
Sixteen frequency/adapter/resource production files match checkout bytes in both,
including schema, synthetic fixtures, template, CSS and translations. A fresh
isolated venv installs with no-index/no-deps and passes pip check. Actual module
locations resolve inside that installation while commands run outside the checkout.
Installed examples/import/search/show/verify/compare/evaluate, invalid input/pin,
expected refusal and byte-identical Quick Top-100 pass. Installed SSR/PT-BR/EN/
CSP/no-store/assets pass using already available optional Web dependencies; no
network installation occurred. The inherited license-table build deprecation is
unchanged. No temporary evidence or external corpus entered package resources.

## CI compatibility

Local runtime: Python **3.13.5**, pytest **9.1.1**, Unicode **15.1.0**. Changed/new
production syntax parses under Python 3.10 grammar; supported-version APIs were
reviewed. The declared >=3.10 requirement and Ubuntu 3.10/3.11/3.12 CI matrix are
unchanged. Those interpreters were unavailable locally; no actual supported-matrix
execution or new remote CI approval is claimed. Operator PR/CI remains subsequent.

## Demonstrated defects

| Finding | Severity/scope | Reproduced failure |
| --- | --- | --- |
| Concurrent conflict exception context | Medium, controlled filesystem error boundary | A conflicting hard-link winner left FileExistsError and a fictitious private filesystem marker attached to the public error |
| Unsupported descriptor scan/link | Medium, unavailable-platform error path | NotImplementedError escaped; descriptor-scan failure reached Web 500/general logging |
| Read stream setup | Medium, rare forced I/O setup failure | fdopen OSError escaped validation into Web 500/general logging |
| Write stream setup descriptor leak | Low, application imports after failed stream creation | Stage was removed but the opened staging descriptor remained live |
| Standalone ratio range | Low, direct helper misuse only | A 30-count row paired with denominator 5 returned Fraction(6, 1); valid datasets already refused it |

No high-severity confinement escape, corrupt accepted ordinary artifact, incorrect
valid-dataset proportion, source download or generation regression was demonstrated.

## Fixes and regressions

Six failing cases were run before their corresponding production corrections.
An isolated reconstruction of all 23 preserved initial files additionally reproduces
both Web symptoms: **8 failed, 35 passed** across the final Gate module on initial
source. Current source passes all **43** Gate cases. The additional passing cases
audit mathematics, canonical identity, privacy/suppression, incompatible contracts,
construction bias, digest trust boundaries, confinement/publication, entry caps,
installed-command semantics, schema bounds, Web/Job isolation and determinism.

The minimal production diff is restricted to two existing new modules: a ratio
type/range guard, read-stream setup inside the sanitization boundary, guarded
unavailable scans/links, explicit staging-descriptor ownership cleanup, and winner
validation after leaving FileExistsError's handler. No schema, ordinary artifact
bytes, frequency ordering, experiment, adapter, stylesheet or generation behavior
was otherwise changed. Documentation adds factual Gate status and methodological
clarifications; original implementation reports/tests are preserved.

## Tests

Initial prescribed suite: **1,371 passed in 57.80 s**. Focused Block 12/Gate suite:
**157 passed in 4.76 s** before the last schema-contract audit case was added.
Final prescribed complete suite including that case: **1,414 passed in 58.66 s**.
JUnit records zero failures, errors or skips. All initial tests remain present;
no assertion was weakened or original test removed by this Gate.

```sh
PYTHONDONTWRITEBYTECODE=1 venv/bin/python -B -m pytest -q -p no:cacheprovider -ra --durations=25
```

The equivalent final run also wrote JUnit under /tmp. TestClient checks require
the same established asyncio-portal sandbox exception used by prior Gates.
Browser, build, benchmark, baseline and reproduction evidence remains under /tmp.
An untracked wordlist generated by an existing CLI suite fixture was removed;
it was absent from the initial 23 files and is not part of the change set.

## Remaining risks

Accepted metadata can still be sensitive; licensing, source truth, unique counts,
coverage and sample independence remain declarations. Suppression/complements and
overlapping comparisons are not anonymity. Per-family omission reasons are unknown
after bridging; no hidden reason/count is invented. Stored checksums need external
pins for historical expected content and do not provide authenticity. Live writers
and trusted-root permissions matter. Atomic publication does not promise parent
crash durability or forced-termination cleanup. Corruption blocks full registry
listing; concurrent imports near the cap can temporarily exceed it and then fail
bounded reads. The favorable tiny symbolic holdout cannot justify real prioritization.
Local Linux/3.13 checks do not replace subsequent supported-runtime CI/Gate review.
No uncorrected demonstrated defect remains in the audited configuration.

## Diff summary

Gate work changes only the two existing frequency modules, factual/limitations
notes in the existing ADR/report/BACKLOG, and adds `tests/test_gate12_audit.py`
and this report. All 23 initial files are preserved. No Block 11/Core/mutator/
ranking/planning/pack/API/Job/database/dependency/version/CI source changes; no
new production engine, automatic prioritization, raw corpus or remote access.

## Working tree final

Branch remains `feat/password-popularity-frequency`; HEAD remains
`aa18849234778aed63d95477054b8c27fe17b1da`. **25** changed/new files remain unstaged:
the original 23 plus this audit report and the Gate test module. Tracked/untracked
whitespace, UTF-8, local-link, final status/stat/name, initial-node retention and
protected-source checks pass. The complete original roadmap is unchanged. No
sensitive customer material, private benchmark corpus, runtime build artifact or
temporary evidence belongs to the intended change set. No commit, push, merge,
Block 13 or compound corporate-name implementation.

## Recommendation

The demonstrated boundary defects are corrected with failing-before/passing-after
evidence. Aggregate arithmetic, disclosure limits, source-qualified comparisons,
synthetic experiment limitations, CLI/Web, historical generation and installed
artifacts are verified locally. Ready for the operator's commit/diff review,
followed by the normal manual PR and supported CI matrix.

**READY FOR COMMIT**
