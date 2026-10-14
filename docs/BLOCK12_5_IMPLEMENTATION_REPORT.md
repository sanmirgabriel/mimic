# MIMIC — Block 12.5: Organization Name Intelligence

Date: 2026-10-14. Local implementation for Gate review. No commit, push or merge.

Gate 12.5 follow-up (2026-10-14): this report preserves implementation-time
evidence. The [independent Gate audit](GATE12_5_AUDIT.md) reproduces coverage,
historical compatibility and exact global ranks; corrects a missing Unicode
output-limit warning without changing candidate bytes/causes; and passes 1,550
tests. Its current recommendation is ready for operator commit review. No agent
commit, push, merge, score-v1 change or Block 13 work was performed.

## 1. Baseline

Required base and unchanged HEAD: `6398108f8699cd24068d06d39cf964671bab8354`.
Initial checkout was clean on `feat/password-popularity-frequency`, at
`333d8604e93377e610d9ecf3fab934f92e35e458`; the requested merge object was not yet
local. Read-only GitHub inspection confirmed [PR #15](https://github.com/sanmirgabriel/mimic/pull/15)
merged at 2026-10-14 12:13:06 America/Recife. Fetching main and creating
`feat/organization-name-intelligence` resolved the exact required base without
changing local work. Required ancestry is confirmed. No local edits were present.

Blocks 7–12 are represented by merged PRs #7–#15, including the partial-leet,
i18n and CI-performance follow-ups. PR #15 [CI run 38586439925](https://github.com/sanmirgabriel/mimic/actions/runs/38586439925)
completed successfully for Python 3.10, 3.11 and 3.12 on the PR head. No individual
combined-status entries were returned for the merge SHA; this is not evidence of
a separate merge/new-feature matrix execution. Baseline local suite:
**1,414 passed in 60.89 s**. Local runtime is Python 3.13.5, pytest 9.1.1,
Unicode 15.1.0. No new remote CI was triggered or approved.

## 2. Architecture reviewed

Reviewed application generation/requests; domain models/planning/context; profile
mapping; IntelligencePlan and its numeric/role/service inputs; Core Candidate,
Seed and Generator; Case/Combine/Affix/Leet; policy; ranking/scoring/Top-K; CLI;
Web form/summary/security/locales; API transport and Job snapshot/restart contracts.
Existing ADRs and canonical BACKLOG guided the source precedence and off defaults.

The smallest integration is a new `mimic.intelligence.organization` lexical
planner called by GenerationService. Domain planning receives its immutable
Candidates as mutable, noncombinable Seeds. Core, mutators, score-v1, API endpoints,
Jobs, database, packs, observations and frequencies are unchanged.

## 3. Original demonstrated problem

With one `Organization.name='acme hamburgueria'`, historical Case preserves the
space and neither individual components, joined component casing nor `AH` is
created. The disabled/base fixture generates none of the nine requested affixed
examples. This is a structural-seed coverage gap before ranking, rather than a
score-v1 defect. Original organization input and causal precedence remain present.

## 4. Tokenization strategy

One linear Unicode scan splits whitespace, `-`, `_`, `/`, en dash and em dash.
Letters, numbers and combining marks are accepted within a component. Multiple
spaces/delimiters do not create empty operands. Other punctuation falls back to
original-only behavior: no stripping commas, dots, apostrophes, emoji or markup.
No stop words, articles, prepositions or brand words are removed. Accents and
original codepoints remain in provenance; Unicode normalization is not applied.
CamelCase/concatenated brands are not internally segmented. Domains/first DNS
labels, keywords and locations retain their existing separate behavior.

## 5. Capitalization rules

Apply original/lower/initial-title per lexical component, with initial-title
meaning uppercase first codepoint plus lowercase remaining codepoints. Join
original components, all lowercase and all initial-title; for two to four words,
also title each component individually over lowercase peers. First component
uppercase plus initial-titled peers is bounded to a first component of <=8 chars.
Thus all four requested mixed-case joins and `ACMEHamburgueria` are distinct seeds.
These are linear rules, not 2^N character/subset choices. Single lexical names use
the unchanged historical Case/Reverse behavior.

## 6. Components and acronyms

Two to four words expose original/lower/initial-title component forms. Five to
eight expose original/initial-title component forms and three whole-name joins.
Two to eight produce upper/lower initials with `rule=acronym`, distinct from
`rule=component`/`rule=concatenate`. No ordered pair product or permutation.
For the fixture, eleven additional seeds are:

```text
acme, Acme, hamburgueria, Hamburgueria, acmehamburgueria,
AcmeHamburgueria, Acmehamburgueria, acmeHamburgueria,
ACMEHamburgueria, AH, ah
```

The engine supplies other Case forms such as `ACME`; it may truncate them under
small frontier caps. Digits as explicit components/initials imply no linguistic
claim. The original full name is supplied by historical planning.

## 7. Integration with Generator

New seeds follow original company/context/organization inputs and precede ready
sources/knowledge. They use the same Case → configured Leet → Affix stages,
Reverse branch, policy and global dedup. They are not Combine partners or additional
organization/service/role template operands. Knowledge common numbers/recent years
retain original attribution/order. No code independently generates `name+year+@`.

When ready sources defer supplementary numbers, structural seeds initially run
with explicit numbers only. Existing deferred-context replay includes them after
ready sources with the complete number list. An acceptance regression confirms a
ready `acmeHamburgueria2026@` wins over a later knowledge-number derivation.

## 8. Provenance

Each changed structural seed derives from its real Candidate, retaining Origins.
`organization_name` records original input, exact JSON component array, rule,
component index when selected, per-component case and `organization-name-v1`.
Actual organization name/ID is retained for organization-derived name/alias forms;
profile/context forms retain their own company input, without a foreign identity.
Only genuine later Case/Leet/Affix/Reverse operations are appended. Zero-leet
examples carry no invented substitution. Existing first causal derivation wins;
an earlier explicit component can legitimately supersede the organization cause.

## 9. Limits and explosion control

First eight distinct explicit names, each <=256 codepoints; <=24 additional
seeds per name, <=192 per request. Emitted values also have a 256-codepoint ceiling.
More than eight components use only three whole-name joins; oversized names use
original-only planning. Existing original inputs are not discarded. Additional
seed count, limited-name count and a fixed warning are available in cheap preview.

The existing per-stage cap remains **5,000**. Each structural case has a separate
seed whose original form enters Affix first. Additional seed work is linear;
Leet/frontier, common numbers, years, separator count and aliases still multiply
work inside the bounded existing pipeline. Deferred replay can run the additional
seeds twice, under the same per-pass caps. No new global cap is claimed. The
existing O(N) global dedup set remains the main variable memory cost. Original
input lists retain historical limits; expansion ceilings do not restrict them.

## 10. Mandatory example coverage

Synthetic name, year 2026, common numbers/recent years/corporate roles, separators
`@!#$`: each example below is generated through the complete exhaustive pipeline
with none and partial leet, both at caps 256 and 5,000.

```text
Acme2026@
acme2026@
acmehamburgueria2026@
Acmehamburgueria2026@
acmeHamburgueria2026@
AcmeHamburgueria2026@
Acme123@
acmehamburgueria123!
Acmehamburgueria2025@
```

Application, modern CLI, Web, API and saved/replayed Job acceptance checks cover
this context. Legacy CLI and explicit modern opt-out retain the original behavior.
Organization.name/aliases, profile empresa, context empresa and inherited target
organization all reach the shared planner with their actual Origins.

## 11. Stage truncation

The external coverage matrix records 54 enabled/disabled × none/partial/full ×
cap 50/256/5,000 × exhaustive/quick/focused scenarios. At default partial, Affix
caps truncate substitution tails, but every independent priority structural seed
starts with its desired plain form. Case and Leet frontiers keep their existing
ordering/caps; full leet intentionally substitutes eligible plain characters.

At cap 50, ten common numbers precede recent-year numbers: the two requested
`123` examples survive, the seven requested year examples do not. At 256 and
5,000, all nine generate with none/partial. Full leet generates none of these
plain examples. Larger numeric/separator sets and policy can also reduce coverage.
No global Generator change or silently increased cap compensates for truncation.

## 12. Top-100 and Top-1,000

At caps 256/5,000, Quick retains 100 and Focused retains 1,000 after scanning
exactly the exhaustive policy-accepted count. **None of these nine examples is
retained** in this organization-origin fixture under either budget. Existing
organization+role templates have higher score-v1 priorities. This does not negate
their generated coverage and does not establish a universal result for other
source/configuration combinations. No family diversity or score adjustment was
introduced to force them into Top-K.

| Leet/cap | Historical exhaustive | Enabled exhaustive | Quick/Focused retained |
| --- | ---: | ---: | ---: |
| none / 5,000 | 11,642 | 14,608 | 100 / 1,000 |
| partial / 5,000 | 86,248 | 115,687 | 100 / 1,000 |
| none / 256 | 4,883 | 7,238 | 100 / 1,000 |
| partial / 256 | 4,883 | 7,533 | 100 / 1,000 |

Counts describe this synthetic fixture only. Structural coverage is not recovery,
real-password Recall@K or probability of successful authentication.

## 13. CLI, Web and API contract

Strict boolean `GenerationRequest.organization_variants`, default False. Missing
or false means historical/off; enabled True is serialized explicitly. False is
omitted from canonical JSON, encoding the opt-out with the permanent off default.
Malformed truthy/falsy values are rejected during serialization as well as request
validation, preventing Job roundtrip from accidentally coercing them.

Modern `generate` enables the switch; `--no-organization-variants` disables it.
Legacy invocation defaults off; `--organization-variants` explicitly enables it.
It works independently of the existing Password Intelligence switch.

Web has one checked localized control inside its existing form and hidden
`organization_variants_form=1`. Marked POST interprets checkbox presence; unmarked
old POST is off. GET, preview, unchecked/error and saved-organization flows are
verified. Preview counts in-memory seeds without candidate generation/corpus reads.

API transports frozen application JSON: new clients explicitly send
`"organization_variants": true`; old omitted/false requests stay off. Automatically
inferring on from organization presence would violate the indistinguishable old
payload contract. No extra marker, endpoint or migration is needed. All adapters
feed the same boolean/service behavior; their modern UI defaults are explicit.
See [ADR 0012.5](adr/0012-5-organization-name-intelligence.md) for the API example.

## 14. Historical compatibility

Fresh archive of the exact required base versus final checkout: twenty application
scenarios and two CLI modes match wordlist bytes/order, complete Origins and
Transformations, score components, ranks/encounter indices, summaries, warnings,
canonical request JSON and evaluated/emitted counts with expansion disabled.
Scenarios include compound company/profile/context/ranked, target dates, organization,
none/full/partial leet, Combine, dataset/ready/PT-BR, services/common values and
Seed/Ready packs. ACME + WordPress/year 2026 remains **159,175 evaluated**, with
**100** retained in Quick. Modern CLI comparison uses the explicit opt-out.

New enabled compound behavior intentionally changes outputs/causes and can change
scores/rank ties through genuine `case=original` seeds. `organization_name` uses
score-v1's existing neutral unknown-transformation contract; no weights/table or
ranking source changes. Original seven services/default credentials, Block 11,
Block 12 and Packs source remain byte-identical to the base.

## 15. Old requests and Jobs

Absent field remains off permanently. Old request canonical JSON/summary shape
is unchanged. True freezes in JobManager's existing JSON snapshot alongside
organization facts; caller edits after submit do not alter the Job. Tests save,
restore and re-submit old/new snapshots and compare exact downloads. Completed
outputs remain available after restart. Existing incomplete Job recovery behavior
and SQLite user_version 2 are unchanged. No runtime package-version inference.

## 16. Determinism

`PYTHONHASHSEED=1/42/777` agree on complete output/result metadata hashes, requests,
summary/warnings, counters, score components, ranks and encounter ordering across
none/partial/full and exhaustive/Quick/Focused with accented Unicode, CamelCase
and duplicate aliases. Ordered dictionaries retain first causal values; sets are
used only for membership. No clock, external term source or random selection is
introduced; the existing explicitly captured reference year governs numeric inputs.

## 17. Performance

Three fresh-process native runs per case, default cap, partial leet, `@!#$`,
Quick Top-100, Linux/Python 3.13.5. Counts exclude streaming files; seeds include
original organization facts, knowledge inputs and additional structural inputs.
Complex fixture is `Acme Serviços de Rede`, aliases `ACME hamburgueria`/`AcmeTech`,
domain `acme.test`, keyword `operations`, and WordPress.

| Scenario | Seeds off → on | Evaluated off → on | Median wall off → on | Median process peak RSS off → on |
| --- | ---: | ---: | ---: | ---: |
| Simple | 19 → 30 | 86,248 → 115,687 | 1.4072 → 1.8910 s | 40,696 → 40,620 KiB |
| Complex | 104 → 133 | 447,553 → 529,101 | 7.9474 → 9.9938 s | 77,760 → 83,448 KiB |

Knowledge seeds remain 18 and 99 respectively; expansion adds 11 and 29. Both
retain 100. More coverage increases CPU/scan cost; small RSS variation is noise.
No portable performance or speedup claim. Process peak RSS measures whole-process
memory, including the inherited global dedup. Exploratory instrumented measurements
were retained separately and do not replace these final native measurements.
No speculative optimization or dependency change.

## 18. Security

Only fictitious organization inputs and synthetic/local fixtures were used. No
network lookup, invented statistical evidence, credential pair or active attack
path. Tokenization is linear without regex backtracking; added value lengths and
counts are explicit. Existing CSP/CSRF, HTML escaping, API browser-origin policy
and private Job lifecycle are preserved. New limit warnings are fixed text without
input values. Existing Core truncation logs and explicit debug conventions still
include seed data; this block does not promise redaction or memory erasure.

## 19. Packaging

Fresh temporary source snapshot builds wheel and sdist offline with --no-isolation.
A fresh isolated venv installs the wheel with --no-index/--no-deps; pip check
passes. **99 packaged production/resource files** match checkout, wheel, sdist
and installation bytes, including new planner, templates and translations.
Module locations resolve within the installation while commands run outside
checkout. Installed CLI on/off acceptance, PT-BR/EN SSR/CSP/static assets, API
submission, explicit persisted switch and Job download pass. Optional Web
libraries already available locally were used; no network installation occurred.
The inherited setuptools license-table deprecation is unchanged.

Installed Firefox **140.12.0esr** passes **36** initial/preview/error × PT-BR/EN ×
dark/light × actual 375/768/1440 content-width cases. No horizontal page overflow;
local resources only. Native Space toggles the control; a native form submit
creates a completed Job and verifies download coverage. Sampled control text
contrast is at least **14.38:1**. Four 375px full-page screenshots are retained
under /tmp; the PT-BR/light screenshot was visually inspected. No CSS/JS redesign.
The existing form's header policy is retained; no new no-store claim is made.

## 20. Tests

Baseline: **1,414 passed in 60.89 s**. Final complete suite: **1,486 passed in
98.99 s**, zero failures/errors/skips. All 1,414 baseline nodes retained;
72 new cases, maximum new node ID length 121. Existing tests/assertions are retained;
one Gate 10 assertion updates the catalog total from 574 to 584 for ten new
PT-BR/EN keys. Existing full placeholder/i18n/theme/security tests pass.

```sh
PYTHONDONTWRITEBYTECODE=1 venv/bin/python -B -m pytest -q -p no:cacheprovider -ra --durations=25
```

The final run additionally writes JUnit under /tmp. TestClient requires the same
local asyncio-portal sandbox exception as previous Gates. Changed/new Python
syntax parses under 3.10 grammar; Python 3.10/3.11/3.12 interpreters were unavailable
locally, so supported-runtime execution for this feature remains subsequent CI.
Historical comparison, coverage matrix, browser, build and performance evidence
are temporary `/tmp/block12_5` artifacts, outside the intended change set.

## 21. Remaining risks

Additional independent seeds increase work and global dedup memory. First eight
names can omit later aliases; unsupported punctuation receives original-only
behavior. Unicode case operations can expand codepoints or affect display; source
spelling remains preserved and output ceiling is enforced. Full leet and tiny
caps lose plain forms; large numeric/separator choices or restrictive policy can
lose additional coverage. Top-K offers no guarantee for specific corporate forms.
API clients must explicitly select True; omitted payloads stay historical. These
are transparent limitations, not empirical frequency or effectiveness claims.
Gate review and new-feature supported-matrix CI remain outstanding.

## 22. Modified files

- `mimic/intelligence/organization.py` (new bounded lexical planner).
- `mimic/application/generation.py` and `requests.py` (adaptation, switch, preview).
- `mimic/domain/planning.py` (normal/deferred additional seed integration).
- `mimic/cli.py` (modern default and explicit activation/opt-out).
- `mimic/web/routes.py`, `i18n.py`, `templates/generate.html`, `templates/summary.html`.
- `tests/test_organization_names.py` (72 new cases) and `test_gate10_audit.py`
  (exact translation-count update only).
- `docs/adr/0012-5-organization-name-intelligence.md`, `docs/BACKLOG.md`, this report.

Protected Core/mutators/ranking/intelligence template catalog/API/Jobs/persistence/
observations/frequencies/packs/dependencies/version/CI source is unchanged. No
parallel backlog, external corpus or runtime artifact is introduced.

## 23. Final working tree

Branch `feat/organization-name-intelligence`; unchanged required HEAD
`6398108f8699cd24068d06d39cf964671bab8354`. Fourteen changed/new intended files
remain unstaged: ten modified, four new. Whitespace/UTF-8/local-link, intended new
files, final status/stat/name, ancestry, protected-source and retained-node checks
pass. The existing CLI suite's transient untracked wordlist is removed if present;
no operator file existed there at baseline. Original Blocks 13–21 roadmap is
preserved. No commit, push, merge or Block 13 implementation.

**READY FOR GATE 12.5**
