# 0006 — Explainable scoring, ranking and output budgets

Status: implemented, pending Gate 8.

## Context and decision

Password Intelligence can generate 152,263 accepted ACME + WordPress candidates.
Operators need an attributable priority order before introducing larger external
packs. Introduce a small stdlib ranking layer above Core. Keep ranking opt-in:
without a finite budget, existing streaming output, order, causal provenance and
source precedence remain unchanged. No dataset packs, default credentials,
frequency data, AI, remote queries or active attack execution enter this block.

A score is **heuristic priority**, not a probability or statistical confidence.
`score-v1` uses only recorded origins, transformations and the request's captured
`reference_year`. It never examines the final string for inferred context or
reads a live clock. Unknown origins receive no weight; unknown transformations
are recorded with a neutral contribution. No external scoring dependencies.

## Central score-v1 table

The authoritative constants live in `mimic/ranking/scoring.py`.

| Recorded signal | Weight | Category cap |
| --- | ---: | ---: |
| Ready candidate | +50 | 50 |
| Explicit/manual input (`manual`, `cli`, `explicit`) | +32 | 32 |
| Target/profile/context distinct semantic field | +30 | 60 |
| Organization distinct field | +22 | 44 |
| Service token/role distinct field | +14 | 28 |
| Corporate knowledge role | +10 | 10 |
| Common numeric primitive | +8 | 8 |
| Recent year relative to captured reference: 0 / −1 / −2 / −3 | +16 / +13 / +10 / +7 | 16 |
| External dataset | +4 | 4 |
| PT-BR generic (`dataset`, field prefix `ptbr.`) | +5 | 5 |

Values outside the four-year window receive no specific year bonus. Without a
reference year, no year bonus applies. Only `knowledge.recent_year` asserts this
meaning; a manually supplied number retains its actual explicit origin.

| Transformation | Contribution per recorded step |
| --- | ---: |
| `knowledge_template` | +4 |
| `case` original / title / lower / upper | 0 / −1 / −1 / −2 |
| Each real `leet` replacement | −2 |
| `affix` | 0 |
| `combine` | −4 |
| `reverse` | −12 |
| `organization_domain_label` | −1 |

These are the requested initial weights without numerical adjustments. The
adapter maps real source names; it does not invent provenance. Categories other
than target, organization and service contribute once, so repeated explicit
numbers/roles/dataset lines cannot inflate scores. Identical origins contribute
once. Multiple values in a semantic field contribute once: `target.name` and
`profile.nome` share the name field; context paths are stripped for field identity.
Service token and role are distinct fields per service ID, under a shared cap.
The first recorded recent-year origin contributes, under its cap, rather than
summing several year bonuses. This retains causal encounter precedence.

Every applied contribution is an immutable component with code, integer delta
and a description identifying the recorded cause. A capped distinct field keeps
a component explaining the cap, with its actual clipped delta (possibly zero).
Duplicate fields do not add components or modify the Candidate. All recorded
transformations keep their explanation, including neutral steps.

## Boundary and execution

`Candidate`, `Origin`, `Transformation`, `Generator` and `PasswordPolicy` remain
unchanged and unaware of score, rank or budget. Domain and intelligence do not
import ranking. `GenerationResult` wraps the original Candidate object with an
optional immutable score and rank; it never rewrites its causal history.

The pipeline remains generation → dedup → policy → optional score → Top-K.
First causal derivation wins **before** scoring. Ranking cannot recover alternate
causes or substitute a later higher-scored duplicate. That would need a separate
future design because it changes dedup and memory semantics.

`RankingOptions(enabled=False, budget=None)` preserves exhaustive behavior.
Enabled ranking requires a finite positive integer. Presets, centralized in
`ranking.models`, are Quick 100, Focused 1,000, Balanced 10,000, Large 100,000,
and Exhaustive (ranking disabled). Custom positive budgets are accepted; no
arbitrary ceiling is added. An exceptionally large custom K has an explicit
memory cost; ranked unlimited is rejected.

Top-K uses a min heap keyed by `(score, -encounter_index)` and retains at most K
results. All accepted candidates are scanned. Only the retained heap is sorted,
by score descending and encounter index ascending. Ties preserve source and
first-cause encounter precedence. Ranks are one-based; encounter indices are
zero-based diagnostics. Memory for ranking is O(K), time is O(N log K + K log K).
**Core's existing global value dedup still consumes O(N) memory**. This is not a
claim that the whole generator is bounded by K.

A budget limits final retained/written candidates, not candidate generation,
CPU work or scan duration. Generation pruning is future work. Ranking introduces
scoring/heap overhead and delays the first final output until scanning completes.
Exhaustive never constructs the heap or invokes the scorer and streams immediately.
Its `iter_candidates`/`iter_values` projections also avoid allocating result
envelopes; the explicitly rich `iter_results` API still returns unscored envelopes.

`iter_results`, `iter_candidates` and `iter_values` claim the same one-shot stream
immediately, even before iteration. The projections preserve ranked order when
explicitly enabled. `evaluated_count` counts policy-accepted evaluations; completed
exhaustive counts equal outputs, while ranked counts can exceed them.

A generic `iter_results(checkpoint=None)` callback runs before each accepted
candidate evaluation. It may raise to interrupt scanning. Application knows
nothing about jobs. JobManager supplies cancellation/progress callbacks and also
checks cancellation between final writes. Its count updates are batched; polling
may lag by a batch. Pending/running jobs retain existing restart recovery (failed,
no resume). Atomic `.part` → final output publication remains conditional on
completion, with cancellation/failure cleanup and sanitized errors.

## Persistence and presentation

SQLite migration v1 → v2 adds nullable `jobs.evaluated_count` and preview `rank`,
`score`, `score_version`, `score_components`. Existing rows, relationships, values,
origins and transformations survive. Initialization is idempotent. Historical
unknown counts/scores remain NULL instead of invented values.

Jobs persist explanations as JSON alongside causal provenance. UI/API display
stored score versions and components without recalculating historical scores,
so a future score-v2 does not rewrite history. New exhaustive preview scores and
ranks remain NULL. Only the first 200 final outputs are previewed, after ranking.
Wordlist downloads contain values only, in final output order. Full metadata
export is deferred.

CLI `--budget PRESET|N` and the compact Web Output priority selector share the
central presets. Absent budget defaults to Exhaustive, including old API JSON
requests. Configuration preview resolves options and score model without executing
candidate generation or scoring. Ranked debug output goes to stderr; explanations
and evaluated/retained counts are visible in job details.

## Validation and consequences

Tests cover exact scores/components, caps, relative priorities, year capture,
real leet histories, immutable envelopes, heap versus sorted reference, bounded
retention, deterministic ties, shared one-shot claims, policy before score,
unranked scorer bypass, cooperative cancellation/failure and subsequent worker
health, persistence, a real v1 database migration, Web/API and CLI contracts.
Manual smoke checks compare unranked bytes with the merged Block 7 base, inspect
ACME + WordPress top results, measure timing/memory, vary hash seeds and exercise
an installed wheel outside the checkout.

Weights remain initial heuristics requiring operator calibration. First-cause
selection can give an otherwise identical value a lower score than an alternate
cause would; this is intentional compatibility. Larger K retains richer causal
objects and components, increasing memory. Frequency, observed patterns and AI
can only be added in later explicit blocks with attributable sources and versioned
score changes. No framework or speculative extension mechanism is introduced.

## Gate 8 partial-leet investigation

The pre-Block-8 code and tests already define partial leet as 1..max_subs real
replacements when eligible positions exist, with no zero-substitution output.
Because Generator composes stages rather than unioning their frontiers, eligible
raw/case variants do not reach Affix unmodified. With ACME + WordPress, the
highest surviving default candidate is therefore a one-substitution hypothesis
(`@CMEeditor2026`, score 54), not a ranking preference over an equivalent surviving
simple hypothesis. Ready candidates and words without eligible positions retain
their existing behavior. Preserving simple hypotheses in partial mode is a
HIGH-PRIORITY FOLLOW-UP coverage debt, recorded in the backlog. Gate 8 deliberately
keeps the historical mutator and Core unchanged; resolving it needs an explicit
compatibility decision and new count/order/provenance/cap expectations.
