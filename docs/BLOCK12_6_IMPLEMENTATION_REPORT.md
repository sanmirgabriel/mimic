# MIMIC — Block 12.6 implementation report

Date: 2026-10-15. Required base and current HEAD:
`a0a10f19019957ec7509644a583e6f8d097d3cfd`.
Branch: `feat/corporate-br-diversity`. No commit, push or merge.

Gate follow-up: see [Gate 12.6 audit](GATE12_6_AUDIT.md). The implementation
measurements below describe the handoff; the Gate adds strict selection/envelope
validation, controlled corrupt-preview errors and CLI/Web prefix disclosure,
without changing preset resolution, family classification, selection or score-v1.

## Outcome

Implemented transparent, opt-in `corporate-br-v1` source resolution and separate,
experimental `diverse-v1` selection through the existing engine. Unchanged score-v1
remains the default. Existing catalogs, mutators, core generation and source
precedence are reused. Blocks 13–21 retain their original roadmap.

**Coverage:** the combined preset includes mutable generic PT-BR and contextual
corporate candidates in one exhaustive stream. It does not construct invented
aliases. In the main synthetic Acme fixture, three of four diagnostic targets
are present exhaustively, but none is retained at 100/1,000/10,000 under either
selector. Corporate-only generation lacks the generic PT-BR targets.

**Distribution:** baseline Top-100/1,000/10,000 has one family, 100% organization+
role. Experimental selection has nine families, with largest-family shares of
92%, 99.2%, 99.92%. It displaces eight original entries per budget. It does not
substantially eliminate similar variants inside the dominant family.

**Recommendation:** the source preset is useful for explicit combined coverage,
with significant additional scan cost. diverse-v1 is suitable for structural
experiments with documented trade-offs. These small fixtures do not establish
general effectiveness or justify replacing default score-v1 selection.

## Audit of existing resources and architecture

Inspected catalog/builtins/organization/planning, datasets, application requests
and generation, all ranking modules, CLI, Web, API, Jobs, persistence and previous
Gate/ADR documentation before implementation. A fresh archive of the required
base is used for compatibility comparison. Initial suite: **1,550 passed, 98.93s**.

- `stream_ptbr` already streams football teams, reset words, common terms and
  cities as mutable seeds. Reset words include `Senha`, `Mudar`, `Trocar`,
  `Bemvindo`, `Acesso`, `Usuario`; common terms include `Brasil` and `Trabalho`.
  The preset selects the existing entire small PT-BR set, not just reset words.
- `common-v1` already provides six independent, ready values: admin, password,
  changeme, welcome, 123456, mudar. They bypass every mutator and Combine. No
  duplicate vocabulary or empirical frequency weights were introduced.
- Existing knowledge-v1 common numbers are 123, 321, 1234, 4321, 12345, 123456,
  000, 0000, 111, 1111. Existing four-year knowledge uses captured reference
  year and three previous years, with distinct numeric Origins.
- Organization-name-v1 already handles names, supplied aliases, components,
  bounded casing and initials. Domain labels and company facts keep their real
  sources. The preset enables that existing plan without generating facts.
- Knowledge templates already build organization+role/service and service+role.
  Both directions, subsequent case/Leet/Affix and real numeric causes survive.
- Existing contextual inputs precede ready sources; ready sources/packs precede
  common ready values, knowledge, external seeds/packs and PT-BR. First surviving
  derivation wins at stage/global dedup. `mudar` therefore has its ready common
  cause while `Mudar@123` has its actual PT-BR+common-number cause.
- Engine frontiers remain capped after each stage at the original default
  5,000. Affix may stop before later years are even constructed. Global dedup
  retains values across the stream. Quick/Focused scan every policy-accepted
  candidate; budgets bound retention, not generation CPU or global dedup.

No corpus, network/LLM dependency, generation pipeline, mutator, score table or
empirical password-popularity claim was added. Structural seeds still use the
existing bounded planning and engine. See [ADR 0012.6](adr/0012-6-corporate-br-family-diversity.md).

## Resolved preset and precedence

Canonical ID: `corporate-br-v1`; CLI/API input alias: `corporate-br`.

| Existing option | Preset default |
| --- | --- |
| organization_variants | true |
| intelligence.enabled | true |
| intelligence.common_numbers | true |
| intelligence.recent_years | true; captured reference year + 3 previous |
| intelligence.corporate_roles | true; contextual applicability remains existing behavior |
| sources.include_ptbr | true; mutable |
| sources.include_common_passwords | true; common-v1, ready/noncombinable |
| Service selections | Exactly the supplied list, empty by default |
| Mutations / Policy / caps / ranking budget | Existing options/defaults |

Explicit fields win, including False. No preset means historical behavior.
API/from_dict merges defaults only into missing fields; direct Python construction
resolves missing whole option objects and treats supplied objects as complete
explicit choices. Snapshots store the canonical ID, all resolved options and
captured year. Explicit False for common ready values and organization variants
is retained with a preset, preventing accidental reactivation on restoration.
No global configuration changes or version inference from package installation.

Example CLI:

```bash
mimic generate --organization 'Acme Corp Brasil' --preset corporate-br \
  --reference-year 2026 --budget exhaustive --output wordlist.txt

mimic generate --organization 'Acme Corp Brasil' --preset corporate-br \
  --reference-year 2026 --budget quick --selector diverse-v1 --output quick.txt
```

`--no-ptbr`, `--no-include-common-passwords`, `--no-intelligence`,
`--no-common-numbers`, `--no-recent-years`, `--no-corporate-roles`,
`--no-organization-variants` override sources independently. Normal CLI logging
shows the resolved source flags and selected services. Quiet continues to suppress
logs. Debug adds literal-free selection family/version/reason alongside the
existing causal trace; plain output remains one value per line.

Minimal API request configuration, nested in the existing `/api/jobs` request:

```json
{
  "preset": "corporate-br-v1",
  "organization": {"name": "Acme Corp Brasil"},
  "intelligence": {"reference_year": 2026},
  "ranking": {"enabled": true, "budget": 100, "selector": "diverse-v1"}
}
```

The returned Job request exposes the resolved sources, Intelligence switches,
organization_variants, common-v1, reference year and candidate-family-v1. For
example `"sources": {"include_ptbr": false}` explicitly opts out of mutable
PT-BR. `selector` is independent of the source preset; absent means original
Top-K. `diverse-v1` with exhaustive is a validation error.

Web separates “Candidate sources” and “Selection strategy”. Selecting Corporate
BR checks its seven source controls, leaving services alone. Editing a source
switches precedence to explicit controls. Without JS, default/custom configuration
and preview provide the same resolution. Preview shows actual resolved sources;
no dataset is read or candidates generated for that preview. All new copy has
PT-BR/EN translations; dark/light, responsive CSS, CSRF and CSP are preserved.

## Taxonomy, determinism and selection proof

`candidate-family-v1` contains exactly 12 fixed identifiers:

`ready`, `organization-role`, `organization-service`, `service-role`, `combined`,
`organization-year`, `organization-number`, `organization-other`, `ptbr-year`,
`ptbr-number`, `ptbr-other`, `other`.

Precedence is ready without mutations, known template types in the listed order,
Combine, organization, PT-BR, fallback. Within organization/PT-BR, a recorded
Affix and a knowledge recent_year wins over common_number; otherwise other.
Profile/context company facts count as organization causes. No final password
text, literal number, private name, source path or opaque ID enters a family ID.
Unknown metadata remains selectable under a stable category. Multiple origin or
step orderings give the same precedence. Origins describe recorded causes, not
external verification of source truth.

The experimental selector scores exactly the same accepted stream. It keeps a
global Top-K heap and one winner per observed family, using score descending,
encounter ascending everywhere. Winners reserve minimal representation; remaining
places use global heap priority. If K<F, the K best winners are used; if N<K,
all N candidates are retained. Final output is sorted by unchanged score/encounter.
No bonus or percentage quota is introduced. Full equal family rotation was rejected
because it could replace most original priority with weaker entries.

Retention has K+F entries, F<=12. Temporary merges/sorts store O(K+F) references,
not N candidates. Excluding at most F winners from a K heap leaves enough entries
for K-F fill slots. At most F-1 baseline entries are displaced when K>=F: global
best is also one family winner. CPU is O(N log(K+1) + K log(K+1)) for fixed F; metadata
inspection adds fixed-family classification work. Tests compare an independent
full-sort oracle over ties, empty/short/long streams and K<F. Independent stream
tracemalloc checks at 2,000 and 20,000 entries, K=25, stay below a fixed 500 KB
ceiling. This is **auxiliary selector** memory: Core global dedup is still O(N),
and input metadata size is not universally bounded.

Every experimental GenerationResult records selector, family, family version,
and family-representative/score-fill reason. Original Candidate, Origins,
Transformations and CandidateScore/components remain unchanged. Output rank is
rank in the retained set, not global rank. Different K lists need not be nested;
the first 100 lines of a 1,000-line diverse output need not contain its reserved
low-scoring families. Run the actual intended budget.

## Initial concentration diagnosis and frozen evaluation

Before implementing the selector, the unmodified corporate-only fixture evaluated
127,241 candidates, wall 2.548s, process peak RSS 76,972 KiB while retaining 10,000
full explanations. All three prefixes were organization-role: forward/reverse
counts 51/49 at 100, 524/476 at 1,000, 5,100/4,900 at 10,000. That diagnostic run
has a different retention budget from the Quick cost runs below.

The minimum-representation policy was recorded before evaluating holdouts. Two
separate fictitious organization contexts were then frozen: Lumen Sistemas Norte
(alias LSN) and Vela Rede Sul (alias VRS), each with 20 synthetic targets spanning
corporate names/abbreviations, role/year, generic PT-BR, numbers, ready values and
unsupported structures. Acme/Mudar are separate diagnostics. No weights, quotas,
thresholds or literal exceptions were tuned after evaluation. Both selectors use
the identical full generation and the same K; accepted-stream digests agree with
exhaustive. Tests additionally compare complete Candidate metadata equality.

Reproduce from a development checkout:

```bash
venv/bin/python -m tests.block12_6_benchmark --output /tmp/block126.json
venv/bin/python -m tests.block12_6_benchmark --stages --output /tmp/block126-stages.json
```

Helpers are under tests; raw synthetic outputs, JSON, browser profiles and timing
artifacts are under `/tmp/mimic126`, outside the production package. No real
passwords, operator wordlists or downloaded corpus were read.

## Candidate coverage and Recall@K

Both selectors have identical candidate coverage: Lumen **16/20** accepted targets
in **301,481** candidates; Vela **16/20** in **286,514**. The four missing targets
per fixture remain missing; negative examples include a future 2031 target,
unprovided tokens and unsupported multi-separator structures.

| Fixture | K | score-v1 recall | diverse-v1 recall | Baseline entries displaced | Holdout targets lost |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lumen | 100 | 1/20 = 5% | 3/20 = 15% | 8 | 0 |
| Lumen | 1,000 | 4/20 = 20% | 6/20 = 30% | 8 | 0 |
| Lumen | 10,000 | 4/20 = 20% | 6/20 = 30% | 8 | 0 |
| Vela | 100 | 1/20 = 5% | 3/20 = 15% | 8 | 0 |
| Vela | 1,000 | 4/20 = 20% | 6/20 = 30% | 8 | 0 |
| Vela | 10,000 | 4/20 = 20% | 6/20 = 30% | 8 | 0 |
| Combined synthetic denominator | 100 | 2/40 = 5% | 6/40 = 15% | 16 across two lists | 0/40 |
| Combined synthetic denominator | 1,000 / 10,000 | 8/40 = 20% | 12/40 = 30% | 16 across two lists | 0/40 |

The gains in both fixtures are `Flamengo123` and `Flamengo2026`. Those shared
PT-BR targets are repeated across organizations: 40 context-target pairs are not
40 independent real-world observations. There are only 34 unique literal targets
across the two fixtures. Overall candidate coverage is 32/40 context-target pairs; retained covered-only recall is 2/32 -> 6/32 at 100, 8/32 -> 12/32 at
1,000/10,000. Neither denominator is a success probability.

Contextual ranks remain useful diagnostics: each raw organization+admin+2026
is global rank 1; alias+admin+2026 is 205; admin+alias+2026 is 222. LSNsuporte2026!
is 381 and VRShelpdesk2026! is 313. Abbreviated organization/year targets rank
117,210. Exact target encounter/global/retained ranks and absences are in the
benchmark JSON. In diverse output the two added generic targets occupy positions
97/98, 997/998, 9,997/9,998 respectively; high-scoring contextual targets keep
their positions in these fixtures.

Eight genuine baseline entries are lost in every case despite zero losses on
these hand-sized holdouts. Relative retained-list losses are 8%, 0.8%, 0.08%.
A holdout concentrated near the original cutoff can lose recall; there is no
monotonic-recall guarantee. Exhaustive universe coverage is unchanged between
selectors. Loss and displacement are intrinsic to filling the same fixed budget.

## Family and sibling distributions; score components

All three combined contexts have the same coarse counts:

| K | Default represented families | Experimental represented families | Experimental org-role count/share | Each other family |
| --- | ---: | ---: | --- | ---: |
| 100 | 1 | 9 | 92 / 92% | 1 |
| 1,000 | 1 | 9 | 992 / 99.2% | 1 |
| 10,000 | 1 | 9 | 9,992 / 99.92% | 1 |

Other represented families are organization-year/number/other, ptbr-year/number/
other, ready and other. Organization-service/service-role/combined do not appear
because these fixtures select neither services nor Combine; there is no artificial
service activation or empty-family quota.

Best-family scores/components in all three fixtures:

| Family | Representative score | Original contributing deltas |
| --- | ---: | --- |
| organization-role | 52 | organization 22 + role 10 + template 4 + current year 16 |
| organization-year | 38 | organization 22 + current year 16 |
| organization-number | 30 | organization 22 + common number 8 |
| other (role/year) | 26 | corporate role 10 + current year 16 |
| organization-other | 22 | organization 22 |
| ptbr-year | 21 | PT-BR 5 + current year 16 |
| ptbr-number | 13 | PT-BR 5 + common number 8 |
| ptbr-other | 5 | PT-BR 5 |
| ready | 0 | knowledge.common_password has no score-v1 origin weight |

Neutral Case-original/Affix/organization_name steps remain recorded. Case/Leet
penalties for other candidates are unchanged. Merely cataloging ready values
cannot create empirical priority or prevalence. Component sums/counts, per-family
minimum/maximum/means are preserved in evaluation JSON.

Acme organization-role scores range 52 at K=100, 50–52 at 1,000, 44–52 at 10,000.
Synthetic sibling concentration groups the actual template direction, Case modes,
bounded Leet-step count and Affix placement/separator position, excluding literal
stems/tokens/separators. Largest sibling-shape share in Acme is 15% -> 15%,
12.4% -> 12.2%, 6.9% -> 6.9%. Lumen: 15% -> 15%, 6.5% -> 6.5%,
8.16% -> 8.14%. Vela: 15% -> 15%, 7.9% -> 7.7%, 6.51% -> 6.49%.
These broad shapes can merge distinct words. Minimum coarse representation does
not solve fine variant concentration; no entropy/probability interpretation.

## Known diagnostic targets and stage losses

Acme default partial, separators `@!#_.`, cap 5,000, year 2026, combined sources:

| Target | Exhaustive | Zero-based encounter | Global score rank | score | Either selector at 100/1,000/10,000 |
| --- | --- | ---: | ---: | ---: | --- |
| AcmeCorpBrasil123@ | yes | 14,065 | 67,365 | 30 | absent |
| ACMECorp2026! | no | — | — | — | absent |
| Mudar@123 | yes | 169,501 | 141,545 | 13 | absent |
| Senha2026! | yes | 165,372 | 105,701 | 21 | absent |

Encounter order is not global score rank. The operator's earlier position 30,956
came from a different configuration and is not reused as a rank measurement.
`ACMECorp` is not an invented partial acronym: supplying it explicitly as an alias
covers `ACMECorp2026!` in the tested none/`@!` configuration. This regression is
separate from the holdout evaluation.

Stage instrumentation follows actual _compose seeds, Affix construction, raw
post-frontier output, real Policy decisions and final exhaustive acceptance.
With `@!` and permissive Policy:

| Leet | Cap | Seeds for AcmeCorpBrasil/Mudar/Senha | Constructed, surviving, accepted diagnostic targets |
| --- | ---: | --- | --- |
| none / partial | 50 | all present | AcmeCorpBrasil123@, Mudar@123 |
| none / partial | 256 / 5,000 | all present | AcmeCorpBrasil123@, Mudar@123, Senha2026! |
| full | 50 / 256 / 5,000 | all present | none of these three |

ACMECorp is absent as a seed in all rows. At cap 50, Senha2026! is never
constructed because earlier affixes exhaust the frontier. Full Leet eliminates
eligible original strings before their plain affixes are constructed. Neither
case is mislabeled as a Policy rejection. With max_len=12, the constructed long
AcmeCorpBrasil123@ is actually rejected; the two shorter accepted forms remain.
The 18-row reproduction includes both permissive and constrained Policy. No
observed target was constructed and then lost at the later frontier in these
fixtures; that outcome must not be fabricated. Caps and separator/number choices
still limit other possible candidates. No universal coverage claim.

## Cost, work and memory

Same Acme context and year in all source comparisons; PT-BR-only source mode
keeps explicit organization seeds/variants and numeric primitives but disables
corporate-role templates. “Corporate” enables existing corporate Intelligence
without PT-BR/ready common values. “Combined” is the preset. Shared explicit
context means counts are not additive; first-cause dedup also changes them.

Three fresh processes per configuration, alternating baseline/experimental,
Quick K=100, partial/default separators/cap 5,000. Medians, seconds and process
peak KiB; accepted-stream hashing and retained diagnostics are included equally:

| Sources | Accepted / retained | score-v1 wall / CPU / RSS | diverse-v1 wall / CPU / RSS |
| --- | --- | --- | --- |
| Corporate | 127,241 / 100 | 1.962 / 1.959 / 42,136 | 2.130 / 2.127 / 42,268 |
| PT-BR with numeric primitives | 145,849 / 100 | 2.191 / 2.189 / 42,848 | 2.469 / 2.469 / 42,936 |
| Combined | 229,548 / 100 | 3.409 / 3.409 / 52,912 | 3.809 / 3.793 / 52,936 |

Combined vs corporate: **+80.4% accepted scan work, +74.0% median CPU, +25.6%
process peak RSS**. Experimental selection on combined: **+11.3% CPU**, with
24 KiB median process peak difference; this does not measure allocator-exact
auxiliary bytes. Individual wall runs vary; these are local measurements, not
portable guarantees. Additional CPU is deliberate source coverage and family
classification, not an increased cap or unchecked cross product.

Other source/mutation combinations, each independently measured with both
selectors (single fresh-process runs, K=100; exact timing/RSS in JSON):

| Leet / separators / common numbers | Corporate evaluated | PT-BR evaluated | Combined evaluated |
| --- | ---: | ---: | ---: |
| none / @! / on | 9,412 | 10,094 | 17,009 |
| partial / @!#_. / on | 127,241 | 145,849 | 229,548 |
| full / @! / on | 7,717 | 8,851 | 14,412 |
| none / empty / off (recent years stay on) | 780 | 838 | 1,409 |

Both selectors evaluate the same count in every cell. Reduced counts under full
or fewer numeric inputs are not evidence of better coverage; some plain targets
are lost. At Acme K=1,000, both selectors still evaluate 229,548; process peaks
are 56,320/56,484 KiB. At K=10,000 they evaluate 229,548 with peaks 88,136/88,388.
Per-K instrumented wall observations vary, so Quick repeated medians are the
primary overhead comparison. Exhaustive, Top-K diagnostic metadata and Core
O(N) dedup must not be confused with the auxiliary heap bound.

## Compatibility, Jobs and security

- Fresh required-base archive versus final code: **20** complete application
  cases agree in serialized result digest, output count/order, evaluated count,
  Origins/Transformations, score/components/ranks/encounters, request JSON,
  summary and warnings. Cases include organization variants on/off, none/partial/
  full, exhaustive/Quick/Focused, services, ready/dataset/PT-BR and profile dates/
  Combine. **Four** actual CLI comparisons agree on stdout bytes and full debug
  stderr for modern/legacy and exhaustive/Quick. These are representative checks,
  not a mathematical proof over every possible historical input.
- `score_candidate`, original Top-K, Core, mutators, existing Intelligence,
  domain sources/planning, API schemas and SQLite schema are byte-unchanged
  from the exact base. Existing score and source precedence contracts remain.
- Historical requests/results/summaries omit new keys. Activated snapshots pin
  selector and family version only for diverse-v1 and preset version only for a
  preset. No database migration; SQLite user_version stays 2.
- Job preview stores separate selection metadata in an envelope in the existing
  score_components JSON cell. API decodes original component lists unchanged,
  exposing a separate selection object. Old cells remain lists. New cells are now type/version validated by the Gate, with controlled 409
  errors for corrupt explanations. New cells require the new reader; backward reading new experimental Jobs with old code is outside
  the contract. Preview remains bounded at 200; downloads remain plain values.
- Tests cover old snapshots, new false overrides, completion, frozen snapshots,
  score explanations, download bytes across restart, interrupted ranked scans,
  pending/running recovery, cancellation and removal of partial output. The
  existing checkpoint/publication path is reused, including for diverse-v1.
- Invalid preset/selector/version inputs and exhaustive+diverse are rejected;
  CSRF/CSP remain active. Escaping/origin protections continue through the full
  historic suite. New family IDs are fixed and contain no private literals.
  A real preset/diverse generation with socket creation and DNS replaced by
  failures succeeds offline. No online authentication or account messages.
- Existing debug traces, candidate provenance, input values and Job snapshots
  still intentionally contain supplied data. Fixed family IDs are not a general
  redaction/DLP layer. Whole-request memory/size and O(N) dedup limitations remain.

## Tests, browser and installed artifacts

Final complete suite: **1,645 passed in 118.66s**, zero failures/errors/skips.
All **1,550 baseline test node IDs remain**; 95 new regressions cover resolution,
explicit False replay, taxonomy precedence, text independence, oracle selection,
score/Candidate identity, displacement, memory, short/empty streams, bounds,
coverage losses, CLI/Web/API, security, Jobs and determinism. No assertion was
removed. Two old exact locale-cardinality assertions were advanced from 584 to
602 for the 18 new messages; exact cardinality/key/placeholder parity remains.

All 95 new tests pass separately with PYTHONHASHSEED **1, 42, 777**. Thirty
representative scenario digests also agree across those seeds, including request,
summary, full result bytes/metadata/scores/selection, evaluated count, none/
partial/full, preset off/on, services, exhaustive and both selectors at 100/1,000.
Captured year 2026 avoids clock-dependent replay. Original tests are retained;
no tests for other roadmap blocks are removed or weakened.

Firefox **140.12.0esr** via local Marionette: **36** initial/preview/error cases,
PT-BR/EN × dark/light × actual 375/768/1440 content widths. No horizontal overflow
or external script/stylesheet resource was found. Native control edits apply
preset defaults and switch to explicit precedence; preview resolves sources;
invalid exhaustive+diverse remains an error. Native submit completes a 100-result
Job with persisted family explanations. Four mobile screenshots were saved and
the PT-BR/light image was visually inspected. A fresh browser profile avoids stale
cached app.js between implementation passes. No blanket accessibility certification.

Wheel and sdist build offline using the existing build dependencies. All **102**
production/resource files match checkout, wheel, sdist and external wheel install.
The external venv imports mimic solely from its installation, passes pip check,
and exercises actual CLI, application, Web preview, API submission, Jobs,
selection metadata, downloads and restart. Dependencies are copied from the
existing local environment; there is no network dependency installation. The
sdist is also installed offline without build isolation and receives the same
external smoke validation. Test benchmark helpers/raw artifacts and the three
pre-existing user lab scripts do not enter wheel/sdist production resources.

Local execution uses Python **3.13.5**. Production Python also parses with 3.10
grammar; supported-runtime 3.10/3.11/3.12 CI execution is not claimed locally.
Dependencies, package version and workflow remain unchanged. The inherited
setuptools license-table deprecation remains. TestClient requires the existing
local sandbox exception for asyncio/thread portals; no product security setting
was relaxed.

## Changed code and evidence

New production modules: application/presets.py, ranking/families.py and
ranking/diverse.py. Changes: application requests/summary/dispatch; ranking option/
result metadata; CLI controls/trace; minimal Job/preview serialization; Web source/
selection controls, local JS, localized copy and summaries. Documentation adds
this report and ADR, source/selection usage in README, and current status in
BACKLOG (12.5 merged PR #16, 12.6 current). New test/benchmark modules live under
tests. The existing three untracked operator lab scripts were left untouched.

Temporary evidence: `/tmp/mimic126/baseline.xml`, `final.xml`, `initial.json`,
`benchmark.json`, `stages-reproduced.json`, `repeated-cost.json`,
`legacy-base.json`, `legacy-final.json`, `cli-legacy.json`, `hash1.json`,
`hash42.json`, `hash777.json`, per-seed test logs, `browser.json`, four screenshots,
external installation smoke results and distribution build logs. Raw evidence is
local and temporary; the reusable fixtures/benchmark code and quantitative tables
are in the repository. No sensitive/operator corpus is included.

## Remaining risks and release decision

The source preset reduces preparation work and improves exhaustive source coverage
at a significant CPU/RSS cost. It preserves explicit configuration and causal
explanations. There is no cap increase or attempt to hide that cost.

Minimum representation has a bounded, explainable trade-off and demonstrates
more coarse families. It remains dominated by organization-role at larger K,
fails to retrieve the known diagnostic literals, shares generic holdouts across
contexts, and can lose cutoff-near targets. It is not a proven effectiveness
improvement or a recovery probability model. Keep diverse-v1 experimental and
opt-in; retain default score-v1. Broader independent evaluation belongs to the
existing future benchmark roadmap, not a new engine/application in this block.

All requested local checks are completed; operator diff/Gate review and supported
runtime CI remain subsequent. No commit, push, merge or Block 13 work occurred.

**READY FOR GATE 12.6**
