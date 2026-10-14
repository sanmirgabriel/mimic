# BLOCK 12 — Password Popularity & Frequency Implementation Report

Date: 2026-10-14. Local implementation handoff for independent Gate 12 review;
no commit, push or merge. Block 13 has not started.

Gate 12 subsequently audited this implementation on 2026-10-14. The original
measurements and 23-file handoff below remain historical evidence. The audit
corrects isolated ratio validation and filesystem error/descriptor boundaries;
see [the Gate 12 audit](GATE12_AUDIT.md) for current validation, explicit synthetic
construction bias, suppression-context limits and commit-review recommendation.

## Baseline and branch

Required main and unchanged HEAD: `aa18849234778aed63d95477054b8c27fe17b1da`
(PR #14 merge). The initial working tree was clean. The requested branch
`feat/password-popularity-frequency` already existed at that exact commit and
was retained. No preexisting operator changes were discarded. Required ancestry
is verified. Baseline from a fresh temporary git archive: **1,256 passed in
59.17 seconds**. The user supplied the previous supported CI matrix success;
this report claims no new remote CI run.

BACKLOG, ADR 0011, both Block 11 reports, observations, generation/request,
score-v1/Top-K, packs, CLI, DataPaths and SSR/i18n contracts were inspected before
implementation. The complete original Blocks 11–21 roadmap remains unchanged;
a separate factual Block 12 status section was added.

## Architectural changes and frequency knowledge model

`mimic.frequencies` contains immutable models, bounded import/registry, comparison,
a fixed synthetic evaluation and a lazy CLI adapter. No model or service is
inserted into generation. `FrequencySource` separates attribution, methodology,
licensing, scope and limitations from `Measurement` and `FrequencyRecord`.
`FrequencyDataset` owns versioned identity and immutable evidence.

All twelve canonical IDs derive from Block 11 `SHAPES`/`ObservedPattern`.
There is no second observation parser/classifier. Every row has an integer count
and the dataset's exact declared denominator, with a derived rational `Fraction`.
The original count/denominator are displayed without floating-point conversion.
Exclusive counts cannot sum above sample size. Zero is explicit evidence;
missing rows mean unavailable or suppressed, never zero. Unknown source scope,
period and coverage stay null. Sample size alone establishes no representativeness.

## Dataset provenance, licensing and schema/versioning

Schema `frequency-knowledge-v1` records identity/version, grammar/extractor,
Unicode database, fixed 1900 lower year bound, explicit upper year bound,
counting unit, sample size and suppression threshold. Supported units distinguish
repeated observations from source-declared unique passwords; users/logins are
unsupported. Required source declarations include title, category, methodology,
attribution, local-use authorization, license, redistribution, limitations and a
non-sensitive sample identifier. Geography/sector need explicit coverage evidence.
Optional HTTPS references are validated, shown as text and never fetched.

The intentionally small license vocabulary is CC0-1.0, CC-BY-4.0,
LicenseRef-Local and NOASSERTION. Redistribution is separate: permitted, forbidden
or unknown. Only the two recognized public licenses allow a permitted declaration;
unknown licensing never implies redistribution permission. These are operator
assertions, not a rights adjudication or certification of collection practices.

The packaged JSON schema accompanies the authoritative Python validator, which
also enforces cross-field counts, date order, Unicode/URL safety and suppression.
Unknown fields/versions/grammars, duplicate keys/rows, invalid UTF-8, controls,
non-finite values, bool/float/negative/overflow counts and malformed/oversized JSON
are rejected. Input is at most 32 KiB, twelve rows, eight limitations and 512
characters per prose field; counts are bounded to signed 64-bit range.

Canonical sorted-key ASCII JSON in grammar row order, with a final newline,
defines SHA-256 over counts and metadata. Equivalent field/row ordering and
whitespace canonicalize to the same identity. No automatic timestamp or clock
input is stored. The registry envelope stores this digest; `--sha256` compares
against an independently retained expected digest. This is content integrity,
not a source signature or protection against an operator rewriting both evidence
and its local checksum.

## Privacy boundaries and compatibility with Block 11

Only aggregate fields are accepted. The bundled A/B examples are clearly labeled,
invented synthetic arithmetic, declared CC0-1.0; no corpus, password/hash record,
real organization or customer data was introduced. Imports never stage original
source bytes or preserve source filenames. Fixed errors omit rejected fields,
paths and foreign exception contexts, including invalid configured directories.

A required non-sensitive-metadata declaration is an operator responsibility;
free text cannot be automatically certified free of secrets, personal details,
organization names or sensitive URLs. The layer is not a DLP detector. Aggregates
can still disclose small cohorts through repetitions, complements and overlapping
comparisons. No anonymity, secure memory erasure or source-truth guarantee is made.

The optional `from_observation` bridge revalidates Block 11 reports and copies only
visible rows. It preserves the valid-sample denominator and extraction contract,
and enforces at least five occurrences even after an original explicit smaller
threshold. It never reconstructs suppressed rows. Samples below five are refused.
Block 11 analyzer/artifact/reuse source remains byte-identical to required main.

## Import, registry and verification

`FrequencyRegistry` uses existing DataPaths resolution and
`DATA_DIR/frequencies/id@version.json`, without SQLite changes. Listing/search
verifies every entry, fails on corruption and is bounded to 128 directory entries.
Missing selected evidence fails explicitly. Root/child directory descriptors pin
reads/publication; regular files open relative to those handles with no-follow.
Final symlinks, symlink directories, FIFOs and unsafe identities are refused.
A parent-swap regression verifies reads stay within the pinned directory.

Complete validation precedes directory creation. Only validated aggregate JSON
enters private staging; checked writes flush/fsync before atomic hard-link
publication. Existing identical content is idempotent; different evidence conflicts.
Concurrent imports revalidate the winner. Write/fsync/link/open failures, short
writes and keyboard interruption cannot publish partial evidence and clean staging.
Unsupported safe filesystem primitives fail closed. Trusted root ancestors,
operator permissions, hard-link support, SIGKILL leftovers and lack of parent
power-loss durability remain explicit limits. Concurrent imports at the directory
limit can temporarily exceed the cap; bounded subsequent reads fail explicitly.

## CLI behavior and explainability

The single `frequencies` family provides `example`, `import`, `list --query`,
`show`, `verify --sha256`, `compare` and `evaluate`. `--data-dir` precedes the
subcommand and otherwise follows existing XDG conventions. Examples print only;
no dataset is selected or imported automatically. Errors are fixed and argument
exception chains sanitized. Exit codes are 0 success, 1 invalid evidence/conflict/
incompatible comparison/evaluation, 2 I/O/integrity/unsafe registry or arguments.

Show/verify retain full provenance, licensing, measurement, exact proportions,
digest status and methodological/privacy warnings. List verifies before bounded
case-insensitive search across metadata and canonical IDs. Comparison/evaluation
include both source identities/digests and their full evidence. No Origin or
Transformation is invented or attached to generated candidates.

## Dataset comparison semantics

All twelve structures appear in fixed grammar order. Each source retains its
own denominator; exact right-minus-left rational differences exist only for rows
reported in both compatible sources. Missing evidence has no difference value.
Unit, grammar, extractor, Unicode or year-window mismatches yield explicit reasons
and no numerical differences; unsupported grammar versions fail import.

Declared populations are unknown, same scope or different scopes. Differing and
unknown sampling fields are enumerated, including methodology, period and coverage.
Same scope labels do not establish representative sampling. Different scopes can
be described side by side, with no transfer claim. Shared sample IDs/identical
content get overlap warnings; distinct IDs do not prove independence. Nothing is
pooled, universally ranked, called statistically significant or interpreted as
successful-authentication probability.

## Frequency-informed evaluation methodology and holdout isolation

The isolated `synthetic-slot-coverage-v1` experiment compares a fixed grammar-order
baseline with descending reported structural counts, ties by original encounter
index; missing rows follow all reported evidence, including explicit zeros.
It does not invoke generation, score-v1 or a new classifier.

The exact universe is twelve declared opaque slots, one per shape. A separately
specified immutable twelve-observation holdout, budgets 1/3/5/12, both orders,
fixture digest, reference identity/digest, exact hits and rational coverage are
emitted. Only declared synthetic references with distinct sample IDs and matching
observations/1900–2099/Unicode 15.1.0 contracts are accepted. The symbolic fixture
does not consult runtime Unicode data. No fixture/method is fitted or tuned from
reference evaluation outcomes; operators must not reuse results for holdout tuning.

Category/sample IDs cannot prove actual independence against dishonest relabeling.
One slot per shape cannot measure within-family candidate uncertainty. This is
structural synthetic coverage, not real-password recovery, a score-v1 comparison
or evidence warranting production ordering. A robust real-candidate experiment
is deferred pending independent authorized holdouts and justified methodology;
there is no hidden production integration to imply that work is complete.

## Web behavior

Read-only `/frequencies` provides source/structure search;
`/frequencies/id@version` shows exact fractions, verified digest, attribution,
methodology, license/redistribution, collection period, scope and limitations.
PT-BR/EN explicitly distinguish heuristic priority, observed sample frequency and
source-qualified documented defaults. Missing context is labeled unknown.

SSR reuses escaping, local assets, CSP, themes, responsive tables and no-store.
Invalid/corrupt/unsafe records and directory errors return fixed 422 responses
before general exception logging. There is no Web import, password upload,
comparison/evaluation endpoint, generation action or Job option. Translation
catalogs contain 574 matching keys (544 previous plus 30); one existing exact-count
audit assertion was updated for those additions, preserving its checks.

Firefox passes **24 combinations**: two pages, PT-BR/EN, dark/light and actual
375/768/1440 px content widths. Tests used near-maximum metadata strings and
checked no page overflow, clipped metadata, raw observation, upload or Job.
Four 375 px screenshots remain under temporary evidence. A discovered metadata
column clipping issue was corrected with scoped CSS and rechecked in all cases.
Installed SSR/locale/CSP/no-store/static assets also pass outside the checkout.

## Score-v1 invariance and legacy compatibility

Core, mutators, generation/requests, domain/intelligence, packs, observations,
ranking/score-v1/Top-K, API, Jobs, database and CI files are byte-identical to main.
No frequency selection or bonus enters normal requests; no request/snapshot field,
API endpoint, migration, dependency, score component or production engine was added.

Fresh-main versus final comparisons match all **16 application scenarios and two
CLI modes**, covering wordlist bytes/order, complete provenance/transformations,
scores/components/ranks, summaries/warnings, request JSON and evaluated/emitted
counts. ACME + WordPress with reference year 2026/partial leet still evaluates
**159,175**; Quick retains **100**. A new regression also compares complete results
before/after registry import/comparison/evaluation. Existing API/Job lifecycle,
restart/download and Block 11 tests all pass unchanged.

## Determinism and performance

Complete aggregate bytes/digests, comparisons and experimental ordering/evidence
match under PYTHONHASHSEED **1, 42, 777**. Counts, row ordering, tie handling and
coverage are deterministic. All 1,256 baseline node IDs remain; new node IDs are
at most 104 characters. Production syntax parses under Python 3.10 grammar.
Local runtime is Python 3.13.5; no new 3.10/3.11/3.12 interpreter/remote CI execution
is claimed. The supported matrix remains the subsequent operator PR's validation.

Local medians for 200 operations on the 1,629-byte synthetic fixture: load
**0.0784 ms** (39,929 peak traced bytes), compare **0.1610 ms** (9,494 bytes),
evaluate **0.1554 ms** (6,888 bytes). One initial import took **0.5835 ms**.
Five-run verified list medians were **0.2768 ms** at one dataset, **6.3901 ms**
at 64 and **12.6923 ms** at 120. Limits bound registry memory and scan work.
These small local measurements are not portable latency guarantees.

Initial nonalternating five-run generation medians were 1.1817 s main / 1.3054 s
final while other validation ran, illustrating measurement noise. A subsequent
alternating fresh-process five-pair check measured **1.1505 s main / 1.1038 s
final** wall medians and **1.1480 s / 1.0998 s** CPU medians, always 159,175
candidates. This establishes no speedup claim; no slowdown was reproduced.
Normal generation never imports `mimic.frequencies`, verified in every paired
process. Generation source is unchanged.

## Package installation

Offline `build --no-isolation` from a fresh temporary source snapshot produced
wheel and sdist; sixteen production/resource files match checkout bytes in both,
including all new modules, synthetic JSON/schema, template, locale and assets.
A fresh isolated venv installed the wheel with `--no-index --no-deps`; pip check
passes. Execution outside the checkout verifies installed module location,
example/import/idempotency/list/search/show/verify/compare/evaluate, invalid input,
expected-digest refusal, schema availability and byte-identical Quick Top-100.
Installed SSR uses already available optional Web dependencies without network
installation. The inherited setuptools license-table deprecation is unchanged.

## Tests

Baseline: **1,256 passed in 59.17 s**. Final full suite: **1,371 passed in 65.93 s**, with no failures, errors or skips,
after the last configured-directory sanitization regression. There are **115**
new cases; all 1,256 original node IDs are retained. No test was removed/skipped.
The only prior-test change updates the matching translation catalog count.

Coverage includes schema/partitions/rational counts, provenance/license declarations,
unknown fields, missing metadata, duplicate rows/keys, incompatible units/extraction,
malformed/deep/large/Unicode/hostile metadata, short reads/trailing bytes, explicit
suppression, input/registry confinement, integrity/digest pins, idempotency/conflicts,
concurrent/partial/interrupted publication, sample overlap warnings, deterministic
comparison/holdout isolation, no network calls, packaged schema, Web privacy and
escaping, localization, fixed errors and legacy result invariance.

```sh
PYTHONDONTWRITEBYTECODE=1 venv/bin/python -B -m pytest -q -p no:cacheprovider -ra --durations=10 --junitxml=/tmp/mimic-block12-tests.xml
```

TestClient checks use the existing necessary sandbox exception for its asyncio
portal, as in Gate 11. No logic was weakened. Build/browser/test evidence and
installed environments remain under /tmp; an untracked wordlist generated by an
existing CLI test was removed from the intended working tree.

## Remaining risks

Source claims and metadata sanitation require operator review. Checksums cannot
certify sources or resist rewriting both evidence and local digest without an
external pin. Sampling bias, duplicates, unknown overlap and complementary totals
limit privacy and cross-source conclusions. The synthetic slot experiment cannot
justify production candidate prioritization. POSIX safe filesystem support,
trusted root ancestors, entry caps and hard links matter. No SIGKILL cleanup,
parent-directory crash durability, cryptographic authenticity, perfect anonymity
or real-world statistical effectiveness is promised. Local validation does not
replace the supported runtime CI matrix or independent Gate 12 audit.

## Files changed and working tree status

Twenty-three intended changed/new files:

- `mimic/frequencies/{__init__,models,registry,comparison,evaluation,cli}.py`.
- `mimic/data/frequencies/{__init__.py,synthetic-a.json,synthetic-b.json,frequency-knowledge-v1.schema.json}`.
- `mimic/cli.py`, `mimic/web/{routes.py,i18n.py,static/app.css}`,
  `mimic/web/templates/{base.html,frequencies.html}`, `pyproject.toml`.
- `tests/test_frequencies.py`, `tests/test_web_frequencies.py`, and the localized
  catalog-count expectation in `tests/test_gate10_audit.py`.
- `docs/adr/0012-password-popularity-frequency.md`, `docs/BACKLOG.md`, this report.

All changes remain unstaged on `feat/password-popularity-frequency`; HEAD remains
the required main commit. Final `git diff --check`, status, diff-stat and changed-name checks pass;
untracked-file whitespace and UTF-8 checks also pass. No generation engine or automatic frequency prioritization;
no score-v1 change, hidden download, leaked corpus, raw-password storage,
undocumented statistical conclusion or unintended API/Job change. No commit,
push, merge or Block 13 work.

**READY FOR GATE 12**
