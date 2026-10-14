# GATE 12.5 — Organization Name Intelligence Audit

Date: 2026-10-14. Independent local adversarial review and recommendation for
operator diff/commit review. No commit, push, merge, remote CI approval or release
certification. Block 13 and score-v1 changes were not started.

## 1. Baseline and working tree

Branch `feat/organization-name-intelligence`; unchanged HEAD and required base
`6398108f8699cd24068d06d39cf964671bab8354`. Required ancestry is confirmed. Local
history records Block 12's PR #15 merge and Blocks 7–11/follow-ups. Initial tree
contained exactly 14 intended changed/new files, all unstaged. Every file was
copied and SHA-256 recorded under `/tmp/gate12_5/initial` before correction. No
operator work was discarded. Initial prescribed complete suite passed **1,486
tests in 109.15 s**, before any production correction.

The implementation report and ADR were treated as assertions to check against
code and fresh measurements. Their original evidence is preserved; the report
now links this Gate prominently. The complete Blocks 13–21 roadmap is preserved.

## 2. Architecture review

Inspected organization planner, application/request/domain planning, Core
Candidate/Origin/Transformation/Seed/Generator/Policy, mutators, ranking and Top-K,
CLI, Web form/summary/locales/security, API schemas and JobManager persistence,
cancellation/recovery/download contracts. The implementation contributes lexical
Candidates to normal mutable, noncombinable Seeds. It does not implement another
engine, numeric mutator, statistical ranking or recursive rule learning.

Knowledge receives original terms, not new structural forms: the new forms are
not multiplied into organization/service/role templates. With this fixture,
knowledge remains 18 seeds; the new planner supplies eleven additional seeds.

## 3. Tokenization correctness

Independent fixtures confirm single names, two/three/four, five/eight and nine
components; repeated spaces, tabs, NBSP/em-space/narrow NBSP, hyphen/underscore/
slash/en dash/em dash. Empty/blank/CamelCase/concatenated names receive no invented
internal split. Empty components are absent. Original accepted spelling stays
in Origins. Profile/record input boundaries can already strip surrounding space;
this is distinct from the new scanner, which retains its supplied source value.

The scanner uses Python `str.isspace()`: newline, carriage return, vertical tab,
form feed and U+001C are recognized delimiters too. This precise behavior is
verified, not presented as rejection of all control characters. NUL/U+0001/DEL,
zero-width space/joiner/BOM, unsupported punctuation and emoji cause original-only
fallback rather than selective deletion. Dots/commas/apostrophes are not stripped.
No NLP, stop words, accent removal or permutation.

## 4. Unicode and component casing

Independent reconstruction from recorded components/rule/index confirms actual
values for `ßtraße İris 123`, including `SSİ1` and `ßi̇1`. First-codepoint uppercase
and remaining-codepoint lowercase are applied per component. Dotted I, sharp S,
composed/decomposed accents and mixed case retain source codepoints; no normalization.
Single lexical brands use their historical Case/Reverse branch without new steps.

A 130-codepoint name (`İ` repeated 128 times, space, `a`) has a 257-codepoint lower
join. The join was already refused correctly, but its limited-name count was zero
and its warning absent. The correction reports this name once, including multiple
oversized forms or an overlapping many-component fallback. Valid seed values,
ordering and metadata are unchanged.

## 5. Component and acronym generation

Exact independently checked additional seed set:

```text
acme, Acme, hamburgueria, Hamburgueria, acmehamburgueria,
AcmeHamburgueria, Acmehamburgueria, acmeHamburgueria,
ACMEHamburgueria, AH, ah
```

Individual forms, whole original/lower/all-initial-title joins, single-component
initial-title joins and bounded first-uppercase form have explicit rules. Acronyms
have their own `rule=acronym`; numeric initials assert no linguistic interpretation.
Duplicate values retain first causal rule/index: repeated `a a` gives component
index 0 for `a`. Five/eight components omit title masks/pair products; above eight
only whole-name fallback joins remain. Deterministic encounter order is preserved.

## 6. Bounds and expansion limits

Verified first eight distinct explicit names; 256 codepoints per inspected name
and additional seed value; 24 seeds per name and 192 per request. Many aliases,
Unicode expansion and duplicate inputs cannot exceed these value/count ceilings.
A 100,000-character name is rejected before Unicode classification; names after
the eighth are not lexically classified. Guards operate before constructing
additional Candidates. Small possible case-expanded strings are computed and then
checked; accepted input hashing/outer source adaptation still perform work.

These are **lexical seed ceilings**, not final-password ceilings: historical Case
can expand Unicode later, and Affix adds characters. A separate Policy.max_len
fixture constrains final values. Limits also do not bound original input lists,
the whole API request or arbitrary supplied Origin/organization label/ID metadata.
A 2,058-character opaque ID remains unchanged in provenance while seeds stay
bounded. Saved record IDs are UUIDs; direct application/API metadata remains an
operator declaration. No silent identity truncation or whole-request memory bound
is claimed. The helper's membership set/outer planning still scale with input names.

## 7. Generator integration

Exactly one planner invocation per prepare; eleven new mutable/noncombinable
source Seeds, using the existing stages. They are not Combine partners. No new
service/role template contains an organization_name step, and no output is fed
back into name expansion. Case/Leet/Affix/Reverse, policy, first-value dedup, ranking,
frontier caps and Job execution are unchanged. The standard cap remains 5,000.

## 8. Deferred numbers/source precedence

Fixtures cover Ready file/Pack, Seed Pack, external dataset, explicit `123`, common
numbers/recent years, role knowledge and intelligence disabled. Explicit-number
forms retain their explicit numeric Origin and precede Ready. A Ready year form
wins ahead of deferred knowledge affixes; ready values have no mutation steps.
Bare structural seeds are earlier explicit inputs, so can win equal bare Ready
values under the established source order; Ready does not have unconditional
priority over all earlier contextual mutations.

Instrumenting real `_compose` shows one pass per structural seed without deferred
sources. Ready plus knowledge numbers causes the intended two passes: explicit
numbers first, full numbers after Ready. Intelligence-off Ready performs one pass.
Dataset/Seed Pack later values do not overwrite earlier contextual causes. No
accidental recursive replay or multiplication into knowledge templates was found.

## 9. Causal provenance

Reconstructed each value from recorded original components, rule, selected index
and casing; checked true subsequent Affix token/input/placement and Origins.
Organization names/aliases retain their supplied organization identity; inherited
Target organization follows the same contract. Profile/context do not acquire a
foreign organization's ID. With the same name in profile, context, organization
and alias, the profile's first real cause wins and its identity field stays empty.
`organization-name-v1` identifies the algorithm. Zero substitutions do not invent
Leet steps. Declared Origins/IDs are not proof of external source authenticity.

## 10. Nine-example exhaustive coverage

Numbered acceptance values:

| ID | Value |
| --- | --- |
| A | `Acme2026@` |
| B | `acme2026@` |
| C | `acmehamburgueria2026@` |
| D | `Acmehamburgueria2026@` |
| E | `acmeHamburgueria2026@` |
| F | `AcmeHamburgueria2026@` |
| G | `Acme123@` |
| H | `acmehamburgueria123!` |
| I | `Acmehamburgueria2025@` |

With year 2026, common numbers/recent years/roles, `@!#$`, all nine appear in
complete exhaustive output under none/partial at caps 256/5,000. None of these
final affixed strings is itself a lexical seed; their six distinct structural
stems are seeds. This distinction is recorded explicitly in instrumentation.
Application, actual CLI, Web, API and persisted/restored Jobs agree.

## 11. Stage truncation analysis

Fresh instrumentation records actual Affix construction, post-frontier raw
outputs, policy decisions, retained values and ranks for all 54 OFF/ON ×
none/partial/full × 50/256/5,000 × exhaustive/Quick/Focused combinations.
For OFF, none of A–I is constructed or emitted in any configuration.
For ON with permissive policy:

| Leet | Cap | Constructed / survive frontier / accepted | Exhaustive A–I | Quick A–I | Focused A–I | Evaluated / exhaustive count |
| --- | ---: | --- | --- | --- | --- | ---: |
| none | 50 | G,H | G,H | none | G,H | 1,530 |
| none | 256 | A–I | A–I | none | none | 7,238 |
| none | 5,000 | A–I | A–I | none | none | 14,608 |
| partial | 50 | G,H | G,H | none | G,H | 1,530 |
| partial | 256 | A–I | A–I | none | none | 7,533 |
| partial | 5,000 | A–I | A–I | none | none | 115,687 |
| full | 50 | none | none | none | none | 1,380 |
| full | 256 | none | none | none | none | 6,588 |
| full | 5,000 | none | none | none | none | 12,244 |

A missing value has no policy decision, not a fabricated policy rejection.
None of the constructed A–I is discarded by a later stage in these runs.
At cap 50, Affix stops during earlier common numbers before requesting year
outputs; it does not construct all theoretical affixes and discard them afterward.
Full Leet removes eligible plain forms before Affix. Policy.max_len=10 separately
accepts A/B/G and rejects the six longer examples, independent of rank pruning.
Large number/separator lists can impose further losses; no universal coverage claim.

## 12. Quick Top-100 and Focused Top-1,000 analysis

Default partial/cap 5,000 evaluates 115,687 in each budget. Quick retains 100;
Focused retains 1,000. Neither contains A–I. The absence is a ranking outcome
within unchanged score-v1, not a Block 12.5 regression. Reduced cap 50 has a
different retained universe, where Focused includes G/H; it must not be confused
with the default result or described as a coverage improvement from truncation.

## 13. Candidate ranks and competing score families

Two streaming passes compute exact global positions by score descending/encounter
ascending. Diagnostic retention is limited to nine targets and a 1,000-result
heap, plus small counters; no whole sorted candidate list is stored. Core's
inherited global dedup still consumes O(N) memory per pass. Actual Quick matches
the first 100 results of the Focused heap, including full score/metadata/ranks.

| Value | Score | Encounter index | Global rank |
| --- | ---: | ---: | ---: |
| `Acme2026@` | 37 | 6,721 | 59,818 |
| `acme2026@` | 38 | 5,145 | 59,706 |
| `acmehamburgueria2026@` | 38 | 13,620 | 59,734 |
| `Acmehamburgueria2026@` | 38 | 22,956 | 59,762 |
| `acmeHamburgueria2026@` | 38 | 26,109 | 59,776 |
| `AcmeHamburgueria2026@` | 38 | 18,621 | 59,748 |
| `Acme123@` | 29 | 6,581 | 66,920 |
| `acmehamburgueria123!` | 30 | 13,483 | 65,621 |
| `Acmehamburgueria2025@` | 35 | 22,970 | 60,656 |

Their components are organization +22, common number +8 or recent 2026 +16/
2025 +13, neutral organization_name/Affix, and genuine Case original 0 or title
−1. A/G inherit an earlier `acme` component's Case title cause; others here retain
independent seed Case original. No Leet penalty is present in these nine.

Competing organization+role+2026 templates score **22+10+4+16=52**. One real
substitution scores 50. Quick has 56 forward/44 reverse organization-role values,
100 zero-Leet results, eight distinct Affix input stems, scores all 52. Focused
has 518 forward/482 reverse, 168 zero-Leet and 832 one-Leet, 72 distinct Affix
input stems, scores 50–52. Both are 100% concentrated in the coarse organization+
role family. Separator/numeric and mutation siblings occupy many slots; no empirical
success probability is implied.

## 14. Request serialization

True persists explicitly; False/absent permanently means off and False is omitted
from canonical JSON. Verified roundtrip and serialization/validation rejection
of strings `true`/`false`, 0/1, null, lists/dicts and foreign objects. No truthy/falsy
coercion survives Job roundtrip. Old JSON shape/summary remain equal to the exact
base. No package-version detection or migration changes historical meaning.

## 15. CLI modern/legacy contract

Ten actual installed entrypoint commands cover modern/legacy help, malformed
arguments (2), invalid generation cap (1), modern default/opt-out, legacy default/
explicit activation and modern knowledge generation (0). With Intelligence off
and directly supplied 123/2026/2025, enabled output bytes equal Application Service
and contain A–I; off output stays historical. Modern default works without reading
implicit stdin. Boolean options match existing argparse style.

## 16. Web controls and preview

Modern GET shows checked localized control and `organization_variants_form=1`.
Marked unchecked POST is off; unmarked historical POST stays off even if it sends
an on value. Preview/errors preserve the resolved choice. Saved/inherited
organization and company facts share application semantics. Guards forbid actual
candidate generation/verified corpus opening during preview; nonexistent external
corpus paths remain lazy. Context input and selected pack metadata retain their
existing preparation needs. No new page/form/endpoint or alternative generation.

## 17. API and historical Jobs

Old, explicit False and True payloads submit/complete/download through the existing
API. Invalid booleans return 422. Candidate preview retains actual provenance;
there is no new API preparation endpoint. Job snapshots freeze original name,
aliases, ID and domains immediately; caller edits afterward cannot change output.
True survives restore/replay/restart. Old absent snapshots remain off. Tests cancel
an enabled running Job without final output, recover old pending/new running Jobs
as failed under existing restart semantics, and remove partial output. SQLite
user_version stays 2; no schema/manager source change.

## 18. Legacy byte compatibility

Fresh archive of exact required main versus final tree independently reproduces
twenty application scenarios and two CLI modes. Disabled bytes/order, complete
Origins/Transformations, scores/components/ranks/encounter indices, summaries,
warnings, requests and evaluated/emitted counters match exactly. Cases include
organization/profile/context/compound, target dates, none/partial/full, Combine,
services/common values, Ready/dataset/PT-BR, Seed/Ready packs and ranking/budgets.
ACME + WordPress/year 2026 remains **159,175 evaluated**, **100 Quick retained**.
Core/mutators/ranking/API/Jobs/persistence/packs/observations/frequencies/catalog/
dependency/version/CI source remains byte-identical to base.

## 19. Score-v1 invariance

No scoring table, component semantics, ranking heap, encounter tie or budget code
changed. Unknown organization_name transformations retain the existing neutral
contribution. Genuine independent Case original causes can differ from an earlier
Case title cause in new enabled generation, as documented; this is not a scoring
bonus or byte-compatibility claim. The Gate correction changes no Candidate or
score. Structural coverage is separate from prioritization and probability.

## 20. Determinism

Thirty-six representative scenarios across Unicode/overflow/many aliases/profile+
Ready, none/partial/full and exhaustive/Quick/Focused reproduce complete bytes,
metadata hashes, scores/ranks/indices, requests, summaries/warnings and counters
under PYTHONHASHSEED **1/42/777**. Fixed captured reference year avoids live clock
use on restoration. Ordered dictionaries set output order; sets serve membership.
The scanner and Case use interpreter Unicode tables: equivalence across different
Unicode database versions is not certified by hash-seed checks.

An isolated reconstruction of the preserved initial files agrees with final code
on all 36 enabled scenarios' Candidate bytes/metadata/counts/requests. Only overflow
fixtures change limited-name count from zero to one and append the fixed warning.

## 21. Performance and memory

Three alternating fresh-process Quick runs per OFF/ON case, native wall/CPU/RSS,
partial, `@!#$`, cap 5,000. Complex fixture: `Acme Serviços de Rede`, aliases
`ACME hamburgueria`/`AcmeTech`, domain `acme.test`, keyword `operations`, WordPress.

| Scenario | Seeds OFF → ON | Evaluated OFF → ON | Median wall OFF → ON | Median CPU OFF → ON | Median process peak RSS OFF → ON |
| --- | ---: | ---: | ---: | ---: | ---: |
| Simple | 19 → 30 | 86,248 → 115,687 | 1.2528 → 1.7317 s | 1.2524 → 1.7316 s | 40,592 → 40,516 KiB |
| Complex | 104 → 133 | 447,553 → 529,101 | 8.4786 → 8.8484 s | 8.4611 → 8.8466 s | 77,540 → 83,476 KiB |

Quick emits 100; knowledge seeds remain 18/99. Instrumented composition passes
remain 19/104 original plus exactly 11/29 structural passes when on. Affix cap
warnings grow 15→22 and 93→111; no default Case/Leet truncation was observed in
these two fixtures. No exponential expansion, wrong Combine use or unintended
replay was reproduced. Existing source/seed and global value dedup retain inputs
and O(N) values; additional coverage costs CPU and memory.

One fresh Focused run per case emits 1,000 with identical evaluation counts;
wall simple OFF/ON 1.3950/1.9469 s, complex 8.2062/9.5933 s. These are individual
runs, not medians. New measurements reproduce increased work, while wall variation
explains differences from implementation-time 1.41→1.89 / 7.95→9.99 s. No speedup,
portable guarantee or speculative optimization. No superlinear blow-up is evidenced
by these limited measurements; Quick still scans the complete accepted stream.

## 22. Browser/i18n/accessibility

Installed Firefox **140.12.0esr** passes all **36** initial/preview/error × PT-BR/EN
× dark/light × actual 375/768/1440 content-width cases. Checked/unchecked states,
native Space toggle, localized help, no horizontal overflow, and same-origin page
resources are verified. Native submit creates a completed Job containing A–I.
Both locales show the corrected Unicode warning. Sampled control/help contrast
is at least **6.15:1**. Four 375px screenshots were retained; PT-BR/light full-page
image was visually inspected. All **584** locale keys and placeholder sets match.
No CSS/JS/interface redesign or blanket accessibility certification.

## 23. Security

Only fictitious/local synthetic material was used. Real generation with sockets
and DNS resolution replaced by failures makes no network calls. No authentication,
scraping, downloaded corpus, statistical credential claim or new file permission
path. Hostile saved names remain escaped text in preview; no executable image/
handler is inserted. Existing CSRF, CSP, browser-origin API policy and private Job
publication/recovery remain unchanged.

New warning text is fixed and does not echo the rejected large form. Accepted
names, metadata/opaque IDs and Origins intentionally appear in snapshots/provenance.
Historical truncation/debug logs can contain input seed values; no perfect redaction,
DLP classification, authenticated source truth or whole-request DoS protection is
claimed. Unsupported characters fall back to original input, not universal rejection.

## 24. Wheel/sdist and installed checks

Offline build from temporary source snapshot produces wheel/sdist; fresh isolated
venv installs --no-index/--no-deps and passes pip check. **99** production/resource
files match checkout, wheel, sdist and installation, including corrected planner,
templates/locales/static assets. All actual module paths resolve inside installation;
CLI/server/checks run outside checkout. Application, CLI on/off, Web, API, candidate
preview, persisted snapshot and completed download across restart pass. Existing
optional Web dependencies were available locally; no network installation. No
temporary Gate evidence/external corpus entered package resources. The inherited
setuptools license-table deprecation is unchanged.

## 25. CI compatibility

Local Python **3.13.5**, pytest **9.1.1**, Unicode **15.1.0**. Changed/new Python
parses under 3.10 grammar; >=3.10 requirement and Ubuntu 3.10/3.11/3.12 workflow
remain unchanged. Those interpreters were unavailable locally. The implementation
records successful PR #15 CI for the base; this Gate makes no claim of new remote
CI or actual new-feature supported-matrix execution. Manual PR/CI remains subsequent.

## 26. Demonstrated defects

| Finding | Severity/scope | Reproduced failure |
| --- | --- | --- |
| Missing Unicode output-limit disclosure | Low; additional-seed preview transparency | A valid-length dotted-I name lost an oversized case form but reported zero limited names and no warning; several omitted forms had the same issue |

The 256 seed ceiling itself was enforced. No high-severity escape, incorrect
ordinary Candidate, false causal source, old snapshot regression, scoring change,
recursive generator or uncorrected declared-contract defect was demonstrated.
Known metadata/global-dedup/runtime scope limitations are recorded separately.

## 27. Fixes and regression tests

Two tests fail before the fix; a third fallback/overflow overlap case already
passes and ensures the correction does not double-count a name. After the minimal
planner change, all three pass. Per-name flag combines component fallback,
oversized output and variant-count limitation, incrementing once. No cap, token,
case rule, value order, algorithm version or metadata of emitted Candidates changes.

Added **64** Gate cases for those regressions and independent scanner/Unicode,
causal reconstruction, bounds, source precedence/replay, noncombinable seeds,
strict boolean serialization, lazy preview, frozen clock/Jobs, cancellation/recovery,
API/Web security/preview and all-locale placeholder contracts. Focused implementation+
Gate suite: **136 passed in 41.50 s**. Final prescribed complete suite:
**1,550 passed in 106.28 s**, JUnit zero failures/errors/skips. All 1,486 initial
nodes retained; maximum new node ID length **111**. No existing assertion weakened
or test removed. TestClient uses the established local asyncio-portal sandbox
exception. Reproduction/browser/build/benchmark/hash evidence remains under /tmp.

## 28. Remaining limitations

Top-K offers no particular-candidate coverage. Full Leet, small caps, larger number/
separator lists and Policy can lose forms. Only first eight names expand; many
aliases/original sources still cost work. Seed ceilings do not bound final mutated
length, all supplied metadata or whole-request memory. Core dedup is O(N), budgets
limit retention rather than scan CPU, and source values/debug are not redacted.
Unsupported punctuation/zero-width input falls back; some control whitespace splits.
Unicode database differences may change classification/case across interpreters.
API callers must send True explicitly; old payloads remain off. Supported-runtime
CI, operator review and external source authenticity remain outside this local Gate.

## 29. Future prioritization recommendation

The default retained set is objectively concentrated: coarse organization-role
share is 100% for both budgets, despite structurally distinct company-only forms
in exhaustive output. Product copy must not promise quick recovery of A–I.

Recommend a subsequent, explicitly versioned and opt-in ranking/selection study,
not a score-v1 patch. Define family IDs from actual causal template/rule, affix
shape/token provenance and substitution count, independent of literal organizations
or manually selected examples. Measure distinct families@K, largest-family share,
concentration/entropy at both coarse and fine levels, plus score loss and retained
coverage tradeoffs. Broad organization-role labels alone hide many sibling variants.

Preserve original scores/components and first-cause evidence; any future diversity
selection must record its family, selection reason, version and deterministic tie
rule alongside original priority. Compare unchanged score-v1 against candidate
strategies on frozen, independently constructed synthetic or explicitly authorized
holdouts, separating tuning from evaluation, controlling overlap/populations and
reporting per-family Recall@100/1,000 with denominators. Do not tune to these nine
hand-picked literals, infer empirical weights from this fixture or claim success
probabilities. Existing future-ranking backlog direction is preserved; no such
strategy or Block 16 benchmark system is implemented by this Gate.

## 30. Diff summary

Gate changes only the existing new organization planner's disclosure accounting,
factual notes in ADR/implementation report/BACKLOG, and adds this report plus
`tests/test_gate12_5_audit.py`. All 14 initial intended files are preserved, including
the original 72 implementation tests. Core, mutators, ranking, original intelligence
planning/catalog, API/Jobs/persistence, observations/frequencies/packs, schema,
dependency/version/CI source are unchanged. No second engine, ranking hack or
parallel roadmap. Final tracked/untracked whitespace/UTF-8/local links are checked.

## 31. Working tree final

Branch and required HEAD unchanged. **16** changed/new intended files remain
unstaged: the original 14 plus Gate report/test module. Initial files are preserved
under temporary evidence; final status/stat/name and all new files are inspected.
No sensitive corpus, build artifact, browser profile or temporary measurement is
part of the intended diff. Blocks 13–21 roadmap is unchanged. No commit, push,
merge or Block 13 work.

## 32. Recommendation

The demonstrated disclosure defect is corrected with failing-before/passing-after
evidence. Lexical coverage, causal integration, source precedence, historical
snapshots/bytes, score-v1 invariance, determinism, local performance, installed
artifacts and Web behavior are verified. Top-K concentration and scope limitations
are explicit. Ready for operator diff/commit review, then the normal manual PR
and supported-runtime CI matrix.

**READY FOR COMMIT**
