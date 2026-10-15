# MIMIC — Gate 12.6: Corporate BR coverage and family diversity audit

Date: 2026-10-15. Decision: **READY FOR COMMIT**.

## 1. Baseline and working tree

Required base, HEAD and branch independently confirmed:
`a0a10f19019957ec7509644a583e6f8d097d3cfd`,
`feat/corporate-br-diversity`. HEAD is the merge of PR #16, with parent
`6e34f4d` (organization intelligence), following PR #15 merge `6398108`.
Base is an ancestor of HEAD, and equals HEAD. No commit, push or merge performed.

Initial working tree: 26 changed/untracked files, including the three pre-existing
operator scripts `mimic_lab_web.py`, `mimic_offline_lab.py` and
`mimic_offline_lab_corrigido.py`. All 26 were copied and SHA-256 recorded before
corrections under `/tmp/mimic126-gate/initial` and `initial-sha256.json`.
No operator script was executed, deleted, edited or staged. Their final hashes
match the initial hashes. All implementation work is preserved.

Before any production correction: **1,645 passed in 102.76s**. Fresh archive of
the exact base was created for comparisons; the implementation report was treated
as a set of claims to reproduce, not sufficient evidence.

## 2. Effective architecture

Read actual preset/request/preparation code, family classifier, both selectors,
score-v1, Intelligence, domain planning, Core/mutators, CLI, Web, API, Jobs,
repository/schema, benchmarks, ADR and prior Gates.

Sources resolve to existing options; planning creates existing Seed/Candidate
operands; Core performs mutations/caps/dedup/Policy; score-v1 computes the same
original priority; selection retains a bounded set; Jobs persist plain downloads
and bounded explanations. No alternate generator, new scoring policy, corpus,
remote model, online authentication or Block 13 work was introduced.

CLI/Web adapt operator choices using their existing conventions. API resolves
individual missing fields; direct Python objects represent whole explicit option
objects. This difference is deliberate and tested. The Gate adds validation at
the new metadata boundary and controlled errors at its read adapters, rather
than changing generation or selection.

## 3. Preset and precedence

`corporate-br` canonicalizes to `corporate-br-v1`. Defaults enable organization
variants, Intelligence, common numbers, four recent years, applicable corporate
roles, mutable PT-BR and common-v1 ready values. Services remain exactly supplied.
Mutations, Policy, caps and output budget are not changed by the preset.

No preset is inferred for old JSON. Unknown IDs/versions are rejected. Explicit
False/True overrides win over missing defaults. Direct construction with omitted
objects activates preset defaults; supplied SourceOptions/IntelligenceOptions
are complete explicit objects. from_dict merges missing fields within sections.
Tests distinguish these two contracts and prove input mappings are not mutated.

## 4. Overrides, serialization and clock

All seven False/True switches are independently exercised through repeated JSON
roundtrips. Seven real Jobs additionally submit each False override, mutate the
caller afterward, move the application clock to 2099, finish, restart and download
again. Requests retain year 2026 and every False; outputs/previews remain stable.

Common-password False and organization-variants False are explicitly serialized
when a preset exists, preventing reactivation on restoration. Other booleans are
already explicit in their sections. Defaults do not depend on installed version.
A new request may capture the local year; a captured snapshot does not recapture it.
This Gate does not claim all arbitrary historical malformed payloads are valid.

## 5. PT-BR, contextual and ready sources

Catalog files and existing numeric/Intelligence resources are unchanged from base.
The PT-BR sets contain football, reset words, common terms and cities. Ready
common-v1 values remain independent weak values, not documented credential pairs.
No empirical frequency is inferred from inclusion in a catalog.

Main preset generation attributes Mudar@123 to dataset PT-BR plus knowledge common
number, with real Affix steps. Bare mudar has knowledge.common_password and no
transformations. A repeated ready/dataset fixture independently demonstrates
first cause: an explicit ready Mudar@123 wins without false mutations; an earlier
external Mudar seed wins over later PT-BR for Mudar123. Removing those explicit
sources restores the true builtin causes. No second corpus cross product exists.

## 6. Adversarial taxonomy

An independent labelled matrix covers all 12 fixed families: ready,
organization-role, organization-service, service-role, combined,
organization-year/number/other, ptbr-year/number/other and other. Its expected
labels are constructed in tests, not obtained by asking the classifier.

Checked template forward/reverse, known-template precedence, permutations of
multiple origins, multiple Affix, year versus common number, profile/target/context
company facts, ready with/without mutations, Case/Leet/Reverse/Combine, absent
metadata, unknown steps and duplicates. Candidate/Transformation constructors
reject structurally invalid types; well-formed unknown metadata has stable fallback.

Classification uses recorded causes, never final-password regex. Replacing final
text with diagnostic passwords or a private path/domain does not change its
family. IDs remain among 12 literals. Ordering of equivalent origins/steps does
not change declared family precedence. This is a coarse causal taxonomy, not a
complete parse of nested grammar or proof of external provenance authenticity.

## 7. Algorithm and independent oracle

The unchanged selector keeps global K and best per family. Tests materialize
small streams only and compute reference output by sorting labelled entries,
partitioning winners, taking representatives, then filling from the sorted
remainder. The oracle calls neither the selector nor the classifier.

Five seeds × stream sizes 0/1/12/144/1,001 × multiple Ks cover empty, singleton,
N<K, N=K, K=1, K<F, K=F, K>F, one per family, all one family, ties, negatives,
representatives inside/outside Top-K and rare families late in the stream.
Candidates/scores retain object identity; every candidate is scored once; reasons,
ranks, existence, count and uniqueness agree with the oracle.

Encounters are generated by enumerate, so two separate stream positions cannot
have equal encounter indices. Equal scores use encounter order. The selector
expects Core's value-deduplicated accepted stream; it does not duplicate Core's
O(N) dedup for arbitrary external duplicate iterables. A real Generator fixture
verifies duplicate values are removed with first causal attribution before selection.

## 8. Proof, streaming and memory

For F observed families, at most 12, reserve min(K,F) winners. If K>=F, removing
at most F reserved encounters from the global K heap leaves at least K-F fill
entries. If N<K, all encounters are already in the heap. If K<F, the highest
priority K distinct winners are retained. Thus result count is min(N,K), and
membership/reasons/order follow the documented policy.

For K>=F, the global best is also its family's best and belongs to both sets.
Therefore at most F-1 winners can require displacing original Top-K entries.
The tests explicitly check this bound. There is no percentage quota or score bonus.

Heap K plus winner references F and O(K+F) merge/sort references give O(K+F)
auxiliary retention; no all-N candidate sort is used in production. Metadata
inspection costs depend on the recorded histories. Core's global seed/value dedup
remains O(N), and the sizes of individual inputs/metadata are not globally bounded.

Independent tracemalloc comparisons at N=2,000/20,000 and K=1/25/250 show no
N-proportional selector growth (fixed 200 KB growth allowance). Injected scan
failures close generator finally blocks and release weak references to all
candidates. Existing checkpoint interruption, real Job cancellation/recovery and
partial-output deletion remain covered by the full suite. No speculative stream
or heap rewrite was justified.

## 9. Score-v1 invariance

Score tables, weights, component construction and original Top-K source match
base byte-for-byte. New Selection validation does not add a component or modify
a score. Representative and fill ordering use original score/encounter.

Known best scores remain 52 (organization+role+template+year), 38 (organization+
year), 30 (organization+common number), 26 (role+year), 22 (organization), 21
(PT-BR+year), 13 (PT-BR+number), 5 (PT-BR) and 0 (common ready without a score-v1
weight). Presence in a catalog does not manufacture empirical priority.

## 10. Candidate and provenance invariance

Independent streamed hashing of complete Candidate JSON, including every Origin
and Transformation, agrees for baseline/diverse at K=100/1,000/10,000 over all
229,548 accepted Acme candidates. Digest:
`113d6feabf8f21158956b835f69d4031d2d4333d828ad92dd63158da76682c93`.
Existing tests also compare entire accepted Candidate sequences directly.

Rank means selected output position. Actual diverse Top-100 differs from the
first 100 of diverse Top-1,000; low-score representatives remain near the end of
the larger output. Documentation already explained this; Gate adds the missing
limitation directly to CLI help and localized Web help. No representative was
moved artificially to the front.

## 11. Family and sibling concentration

Acme, original partial/default separators/cap 5,000, year 2026, combined sources:

| K | Baseline families / org-role | Diverse families / org-role | Baseline entries displaced |
| --- | --- | --- | ---: |
| 100 | 1 / 100% | 9 / 92% | 8 |
| 1,000 | 1 / 100% | 9 / 99.2% | 8 |
| 10,000 | 1 / 100% | 9 / 99.92% | 8 |

The other eight families have one representative each. Absent services/Combine
are not selected or assigned empty-family quotas. Baseline/diverse full accepted
streams and original scores agree. Coarse count improvements do not imply balanced
output or better probability of recovery.

Sibling shapes reproduce 15% -> 15%, 12.4% -> 12.2%, 6.9% -> 6.9% largest shares
for Acme. Per-family score ranges/means/component sums and the Lumen/Vela shapes
also reproduce exactly. The broad diagnostic shape can merge distinct literal
stems; it is not a second selector or evidence of eliminated variant concentration.

## 12. Diagnostic targets

All exact reported Acme generation/rank results reproduced:

| Target | Exhaustive | Encounter (zero-based) | Global score rank / score | Both selectors at 100/1,000/10,000 |
| --- | --- | ---: | --- | --- |
| AcmeCorpBrasil123@ | yes | 14,065 | 67,365 / 30 | absent |
| ACMECorp2026! | no | — | — | absent |
| Mudar@123 | yes | 169,501 | 141,545 / 13 | absent |
| Senha2026! | yes | 165,372 | 105,701 / 21 | absent |

These final affixed values are constructed candidates, not the lexical input
seeds themselves. Relevant stems are observed separately. ACMECorp is not an
available stem in the main fixture; adding that explicit alias separately covers
ACMECorp2026! with none/@!. Its unprovided absence is not a defect. The operator's
earlier 30,956 generation position is neither reused nor misreported as score rank.

## 13. Stage truncation

Independent hooks observe seed input, actual Affix construction, post-frontier
raw values, actual Policy calls and exhaustive membership for **36** combinations:
none/partial/full × cap 50/256/5,000 × @!/default separators × permissive/max_len=12.

For both separator sets, none/partial at cap 50 construct/retain AcmeCorpBrasil123@
and Mudar@123, but stop before constructing Senha2026!. At caps 256/5,000, all
three appear with permissive Policy. Full Leet removes eligible originals before
these plain Affix values are built; missing targets have no Policy decision.
max_len=12 actually rejects the long constructed corporate form while accepting
the two shorter forms when constructed. No sampled target is falsely claimed to
be lost after construction if it was never requested from Affix.

Standard-separator accepted counts for caps 50/256/5,000: none 2,817/13,971/35,909;
partial 3,035/14,334/229,548; full 2,717/13,477/30,414. Reduced separators reproduce
the implementation report's 18-row matrix. Caps are unchanged and losses are real.

## 14. Synthetic holdout evaluation

Reexecuted the supplied benchmark, checked every target encounter/global rank,
retained rank, family distribution, component aggregate, accepted digest and
sibling concentration against the earlier raw evidence. Structural results agree:

| Fixture | Accepted universe | Candidate coverage | Recall@100 baseline -> diverse | Recall@1,000/10,000 baseline -> diverse |
| --- | ---: | --- | --- | --- |
| Lumen | 301,481 | 16/20 | 1/20 -> 3/20 | 4/20 -> 6/20 |
| Vela | 286,514 | 16/20 | 1/20 -> 3/20 | 4/20 -> 6/20 |
| Combined context-target pairs | — | 32/40 | 2/40 -> 6/40 | 8/40 -> 12/40 |

Each budget displaces eight baseline entries per context. None of the 40 targets
is lost. Gains are exactly Flamengo123 and Flamengo2026 in both contexts. All
missing targets remain in denominators; covered-only recall is separately labelled.
No online attempts or human-prevalence inference was made.

## 15. Holdout overlap, freezing and construction bias

20 pairs per fixture, 40 total, **34 unique literal values**; six literals overlap.
Shared generic gains are correlated across contexts. Most candidate targets were
chosen to resemble available grammar; negatives were deliberately unsupported.
This is a regression fixture with construction bias, not a representative sample.

A local policy-before-evaluation file predates the recorded initial benchmark,
and its policy agrees with unchanged source. Stored benchmark fixture values
match current tests. However, local mtimes and mutable /tmp evidence are not
independent immutable preregistration, and no separately sealed pre-evaluation
holdout manifest exists. The Gate can confirm no policy/literal tuning during
this audit; it cannot certify a historically blind study from those files alone.
The experimental recommendation must not rely on such a stronger claim.

## 16. Independent recall-loss counterexamples

A 100-slot baseline stream has one organization family, scores 0 through -99;
a rare other-family candidate arrives last with -100. Diverse reserves it and
removes original cutoff target 99: Recall@100 for {99} is 1/1 -> 0/1. For
{99,never-generated}, recall is 1/2 -> 0/2. For {0}, recall stays 1/1; for an
absent-only target it stays 0/1 despite an extra represented family.

Tests also reproduce a real non-nested 100/1,000 prefix and show a family absent
from baseline entering the retained set. These examples preserve policy exactly;
no cutoff-aware or password-specific adjustment was introduced.

## 17. Cost, seeds, CPU and memory

Independent three-process medians per source/selector, K=100, same Acme context,
partial/default separators/year 2026/cap 5,000. Capture counts warnings and mutable
composition calls; no selector stores the whole stream.

| Sources | Mutable composition passes | Accepted / retained | Affix truncation warnings | Baseline wall / CPU / peak KiB | Diverse wall / CPU / peak KiB |
| --- | ---: | --- | ---: | --- | --- |
| Corporate | 33 | 127,241 / 100 | 24 | 2.112 / 2.105 / 46,776 | 2.158 / 2.156 / 46,780 |
| PT-BR + numeric primitives | 39 | 145,849 / 100 | 28 | 2.187 / 2.183 / 47,512 | 2.483 / 2.463 / 47,520 |
| Combined | 72 | 229,548 / 100 | 43 | 3.395 / 3.391 / 57,748 | 4.149 / 4.140 / 57,764 |

All have one organization input and 14 structural variants. Corporate/combined
have 18 knowledge seeds; PT-BR mode has zero role/template seeds and the same
numeric primitives/context. PT-BR contributes 24 builtin seeds. Combined also
has six immutable common values, excluded from mutable-pass counts.

Important inherited mechanism: common ready values activate deferred contextual
numeric expansion to preserve source precedence. Thus combined performs 15
explicit-only contextual passes, 15 contextual replays, 18 knowledge passes and
24 PT-BR passes = 72. Corporate performs 15+18=33; PT-BR performs 15+24=39.
This existing bounded replay is unchanged, not an indiscriminate new corpus or
alias multiplication. All six variants trigger the existing global dedup warning
once above 100,000 entries; no cap was raised.

The **80.4% accepted-work increase** reproduces exactly. The original raw medians
support the reported +74.0% CPU/+25.6% RSS/+11.3% selector CPU arithmetic. Fresh
Gate observations give **+61.1% CPU/+23.5% RSS** combined/corporate and **+22.1% CPU**
for diverse on combined. Absolute peaks include extra audit imports; timing,
frequency and contention vary. Exact runtime percentages are not reproducible
constants, and this Gate does not claim the older timings were matched. Both
sets show significant extra scan cost; no speculative optimization was attempted.

The benchmark's 24 source/Leet/number/separator cells also reproduce their accepted
counts; lower full-Leet or constrained-input counts do not imply better coverage.

## 18. CLI, Web and API

Actual modern/legacy CLI comparisons reproduce default outputs and debug stderr.
Existing and new tests cover presets/selector, all source switches, invalid IDs,
invalid/exhaustive budgets, help, normal resolved-source logs, quiet plain output
and literal-free selection debug fields. Existing causal debug still contains
operator data; no general redaction claim.

Web preview resolves defaults and custom overrides without generating candidates
or reading dataset streams. Tests block generation and dataset opening; checked/
unchecked values and selected preset/custom/selector survive controlled errors.
No-JS explicit configuration is tested both by HTTP forms and real Firefox.
API old requests, partial resolution, unknown versions, metadata serializability,
submission and restarts are covered. No authentication route was added.

## 19. Job persistence and legacy decoding

Valid legacy component lists and absent selection remain byte-compatible. New
experimental envelopes expose unchanged score components and separate Selection.
New validation rejects missing/extra keys, non-string/unknown family/reason/version,
wrong component container/types, bool deltas, malformed JSON and unsupported
scalar cell types with a fixed error. Both writer and reader validate envelopes.

API candidate reads and Web Job reads return controlled 409 for corrupt/unsupported
explanations without echoing saved private values. Completed wordlist download
uses the unchanged completion/output path and remains available independently.
Large valid 100,000-character component descriptions remain intact; invalid giant
family IDs are rejected. This is not a whole-database size or integrity guarantee.

No SQLite migration; user_version stays 2. Real Jobs and full-suite tests cover
cancel/recovery/partial deletion, frozen flags/year, old snapshots, completion,
new metadata and restart. Code from before this feature is only required to
read historical Jobs, not future experimental envelopes. Corrupt legacy origins/
transformations or arbitrary other DB damage are outside this narrow correction.

## 20. Security and privacy

Hostile organization HTML, duplicate aliases, long dotted-I Unicode aliases,
malformed request sections, private family strings and corrupt saved metadata
are exercised. HTML remains escaped; Firefox confirms no injected image/handler
or execution. CSP, CSRF and browser-origin policies are preserved. Actual new
preset/diverse generation under failing socket/DNS stubs succeeds offline.

New selection errors are fixed text. No remote corpus or authentication attempt,
new file-permission path or operator-lab execution. Origins/snapshots and historic
causal logs can contain supplied private data; fixed family IDs do not anonymize
them. Huge input/metadata and Core dedup remain existing resource limits.

## 21. Determinism and versions

30 scenario digests agree under PYTHONHASHSEED 1/42/777: request, summary, warnings,
Candidate/Origins/Transformations, score, selection family/reason/version/ranks,
output wordlist bytes and evaluated counts. Cases include services, preset on/off,
none/partial/full, exhaustive and both selectors at 100/1,000.

The Gate regression suite also passes under all three seeds. Jobs retain captured
year after moving clock to 2099 and keep output bytes across restart. Unknown
preset/family/selector versions are rejected at their applicable transport/model
boundaries; optional absence in old results is preserved. Benchmark structural
results are deterministic; CPU/RSS/time are descriptive observations, not hashes
expected to be identical across runs.

## 22. Browser and i18n

Firefox 140.12.0esr with fresh temporary profile reproduces **36** initial/preview/
error × PT-BR/EN × dark/light × actual 375/768/1440px content-width cases. Controls
are distinguishable, resolved sources visible, errors preserve state and there
is no horizontal overflow or remote script/stylesheet resource.

Native keyboard Space toggles a source and switches to custom precedence. Native
submit completes a 100-result Job whose persisted metadata appears in the page.
Additional Firefox checks cover hostile saved organization escaping and explicit
False in a preview with page JavaScript actually disabled. Four mobile screenshots
are retained and PT-BR/light is visually inspected. This is basic keyboard/layout
verification, not a full accessibility certification. All **602** translation keys
and placeholder sets match. Help text was extended without changing key counts.

## 23. Wheel and sdist

Fresh offline builds succeed. Both wheel and sdist are installed outside checkout,
using dependencies copied from the existing local environment, without network
installation. The actual installed mimic entrypoint, preset/selector imports,
Web preview, API submission, Jobs, restart, metadata and downloads pass. Every
loaded mimic module resolves inside the external venv; pip check passes.

All **102** production/resource files agree among checkout, wheel, sdist and
external installation, including static JS/templates/translations. Benchmark
helpers and operator lab scripts are absent from both distributions. Tests may
appear as source-distribution test resources, not runtime modules.

Production and new Gate Python parse under 3.10 grammar. Local execution is
Python 3.13.5; actual 3.10/3.11/3.12 runtime certification requires future PR CI.
Package/dependency/schema/workflow versions are unchanged. Inherited setuptools
license-table deprecation remains.

## 24. Historical regression against exact base

**23** application cases compare complete result digest/order, Origins,
Transformations, score/components, rank/encounter, counts, summary, warnings and
request JSON against a fresh required-base archive. Coverage includes organization
variants off/on, profile/date/Combine, ready/dataset/PT-BR, Seed/Ready packs,
services, all Leet modes, Affix, contextual explicit years and budget presets.

**Four** actual CLI modern/legacy × exhaustive/Quick cases agree on stdout bytes
and full debug stderr. **Three** real persisted Job cases agree in request,
preview, counts and download digest, and survive restart. ACME+WordPress 2026
retains **159,175 evaluated / 100 Quick outputs**. These are strong representative
comparisons, not a universal proof over every possible historical request.

Score-v1, original Top-K, Core, mutators, Intelligence, domain plans/sources and
SQLite schema are unchanged from base. Gate API source changes only the new
corrupt-explanation read path; valid historical behavior agrees with base.

## 25. Defects demonstrated

| Finding | Severity and affected contract | Before-fix reproduction |
| --- | --- | --- |
| Selection accepts unknown/private IDs and versions | Medium, new metadata/version/privacy contract | 9 direct invalid records accepted; malformed/falsy result selection could disappear or raise uncontrolled type errors |
| Experimental envelope assumes keys/types | Medium, corrupt/unsupported Job explanation handling | Missing keys raise KeyError; unknown selector/reason is exposed as if valid; malformed saved cells break read pages |
| Malformed option sections escape application error contract | Low, inherited from_dict exception inconsistency exposed by preset input | mutations/policy/limits null/list/bool/number/string raise AttributeError instead of InvalidGenerationRequest; API already mapped this to 422 |
| Prefix limitation absent from CLI/Web help | Low, operator transparency | Help lacked warning that a 1,000-result prefix can differ from a 100-result run despite existing ADR/report disclosure |

No selector-policy, scoring, causal-generation or historical-byte defect was
found. Known effectiveness limitations are not relabelled as implementation bugs.

## 26. Corrections and tests

Initial independent tests: **40 failed, 58 passed**, saved before corrections.
Added strict Selection transport/model validation; validated only the new envelope
with fixed error; translated corrupt explanation reads to HTTP 409; normalized
AttributeError to application request error; extended CLI/Web prefix help.
No new policy, quota, score, literal special case, cap or schema migration.

Final Gate module has **122** adversarial cases, preserving all initial assertions
and adding Job/HTTP/browser-adjacent/security tests. The required complete command:

```bash
PYTHONDONTWRITEBYTECODE=1 venv/bin/python -B -m pytest \
  -q -p no:cacheprovider -ra --durations=25
```

**1,767 passed in 111.74s**, with JUnit zero failures/errors/skips. All 1,645
implementation node IDs remain, including the 1,550 pre-implementation nodes.
No tests were removed or weakened.

## 27. Remaining risks

O(N) Core dedup, unbounded individual metadata, coarse families, score-first
non-nested output, significant scan CPU, and eight displaced high-priority entries
remain. A valid envelope is structurally/version validated, not cryptographically
authenticated or rescored; its contents remain recorded evidence. Local DB input
is not a trusted source-of-truth certificate. Arbitrary DB corruption is not fully
recovered. Clock/Unicode/interpreter differences outside captured options are not
certified by hash-seed checks. Supported-runtime CI is still subsequent.

## 28. Experimental selector recommendation

Keep opt-in diverse-v1 unchanged. It reliably represents observed coarse families
with a small proved displacement bound, but larger budgets remain overwhelmingly
organization-role. Diagnostic literals remain absent; sibling concentration barely
changes; holdout gains are correlated and constructed. It can reduce Recall at
the original cutoff. No broad effectiveness improvement, prevalence estimate or
authentication probability has been established. Corporate BR is a useful explicit
source workflow with measurable cost, not an implicit default for old requests.

## 29. Diff summary

Gate production corrections affect only application requests, ranking metadata,
repository envelope validation, API/Web corruption handling, CLI help and Web copy.
The preset resolver, family classifier and diverse algorithm are SHA-unchanged
from implementation entry. Core/mutators/score-v1/original Top-K remain untouched.
Added tests/test_gate12_6_audit.py and this report. ADR/implementation report/BACKLOG
receive factual Gate notes. Existing implementation changes remain in the diff.
Blocks 13–21 table scopes are preserved exactly.

## 30. Final working tree and evidence

Final status contains 17 modified tracked files and 12 untracked files, including
the three unchanged operator scripts; 26 files belong to the intended diff.
All work remains unstaged on the required branch/HEAD. No commit, push, merge,
operator-lab mutation or new roadmap implementation. Final status/stat/name lists
and new untracked files are inspected; git diff --check passes.

Evidence is under `/tmp/mimic126-gate`: initial SHA/snapshot/status, initial/final
JUnit, failing-before tests, benchmark reproduction, independent metadata/stage/
cost JSON, fresh base archive, legacy application/CLI/Job comparisons, three seed
digests and test logs, Firefox script/results/screenshots, distributions and
external install/smoke logs. Raw evidence stays outside production resources.

## 31. Decision

Concrete validation/transparency defects are corrected with failing-before and
passing-after evidence. The experimental policy is unchanged and its limits are
explicit. Compatibility, local browser/i18n/security, offline installs, snapshots,
Jobs, performance scope and deterministic output are verified. Ready for operator
diff/commit review, followed by normal manual PR and supported-runtime CI.

**READY FOR COMMIT**
