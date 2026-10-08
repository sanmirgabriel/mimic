# MIMIC product backlog

Canonical product epics. Blocks 7, 8 and 8.4 are merged. Block 8.5 is implemented
and validated in the working tree. Block 9 is the next major product milestone.

| Block | Epic | Scope |
| --- | --- | --- |
| 7 | Password Intelligence Foundation ✅ | Versioned primitives, contextual seeds, services, organization-only flow, causal provenance. |
| 8 | Scoring / Ranking / Budgets ✅ | Explainable prioritization and explicit generation budgets. |
| 8.4 | Partial-Leet Coverage Fix ✅ | Original candidate first, then up to max_subs replacements; causal provenance, ranking, caps and compatibility validated. |
| 8.5 | Web Internationalization + Theme Switcher ✅ | PT-BR default and selectable EN; compact language/theme controls, dark/light palettes and local preferences; presentation only. |
| 9 | Dataset & Knowledge Packs | Next major block: external, streaming, license-aware packs and dataset management. |
| 10 | Service Intelligence + Default Credential Catalog | Broader technology context; separately modeled credential pairs. |
| 11 | Observed Password Pattern Learning | Authorized observations and attributable learned patterns. |
| 12 | Password Popularity / Frequency | Frequency knowledge with transparent sources and licensing. |
| 13 | Hashcat Convergence | Consistent material and rule export through the existing engine. |
| 14 | AI Context Assistant | Assisted context extraction through the application service. |
| 15 | Documentation / Operator UX | Documentation overhaul and operator workflow improvements. |
| 16 | Benchmarking / Release Hardening | Reproducible benchmarks, packaging and release gates. |

## Block 8.4 — Partial-Leet Coverage Fix (completed)

- Partial now emits the unchanged Candidate before 1..max_subs substitutions.
  Zero substitutions adds no leet transformation and reaches Affix and score-v1.
- ACME + WordPress (reference year 2026, default cap 5,000): 152,263 → 159,175
  accepted candidates; Affix truncations 28 → 29. Partial output intentionally
  changes; none/full retain their previous output and causal metadata.
- Direct, Generator, exhaustive/ranked, legacy/modern CLI, persistence and
  hash-seed checks cover the new contract. See
  [ADR 0007](adr/0007-partial-leet-coverage.md).
- Presentation follow-up: completed Block 8.5 below.

## Block 8.5 — Web Internationalization + Theme Switcher (completed)

- PT-BR is the default; EN is selectable with a compact header control.
  Both read-only catalogs contain 392 matching keys with compatible placeholders.
  Request-local helpers cover SSR pages, macros, validation, confirmations,
  score labels, provenance and HTMX fragments without shared locale state.
- An allowlisted, CSRF-protected preference endpoint stores a one-year
  HttpOnly/SameSite cookie and redirects only to safe local paths and queries.
  Polling reloads on a cross-tab locale mismatch before swapping fragments.
- Dark remains the default. A real light palette, accessible adjacent toggle
  and blocking local initialization script persist the independent theme in
  localStorage without relaxing CSP. Responsive controls and form headings
  remain readable on mobile.
- Implementation baseline: 636 tests; pre-Gate suite: **718 passed**. Gate 8.5
  final suite: **758 passed**, including 82 i18n/theme and 40 Gate audit cases.
  Existing English assertions use explicit EN clients; the singular linked-count
  assertion was updated for corrected grammar, without weakening its check.
  Firefox validated 160 page/locale/theme/viewport cases at 320, 375, 768 and
  1,440px, plus 32 options/advanced-focus screenshots. All sampled visible
  first-load frames used the saved light theme. The English dark generation
  screen matches the base screenshot outside the header with zero changed pixels.
- Gate fixes localize the job breadcrumb, improve PT-BR wording and linked-count
  plurals, make catalogs read-only, log safe translation fallbacks and improve
  dark primary-button hover contrast. Concurrent clients, hostile redirects,
  escaping, localized errors and API/corpus independence are covered. Active
  cross-tab polling survived both language switches without loops, cancellation
  or duplicate jobs; test-only checkpoint pauses kept the observation window open.
- Wheel and sdist assets match the checkout. The installed-wheel HTTP smoke
  covers preference persistence, preview, job submission, polling, provenance
  and download. PT-BR/EN ACME + WordPress jobs evaluate 159,175 candidates and
  retain 100 with identical wordlist bytes, scores and canonical provenance.
- Core, API JSON, CLI, ranking, schema, dependencies and README are unchanged.
  See [ADR 0008](adr/0008-web-internationalization.md).
- **Next major block: Block 9 — Dataset & Knowledge Packs.**

## Future enhancements

- **Ranking diversity / family-aware candidate selection:** consider diversity
  between related candidate families in a future ranking block, with explicit
  semantics, provenance and deterministic validation. Not implemented in 8.5.

## Permanent constraints

- **One engine:** knowledge supplies structured seeds/numbers to the existing pipeline.
- **Provenance first:** retain actual operands, origins and causal transformations.
- **Determinism:** preserve encounter order and freeze dynamic configuration in requests.
- **Streaming:** keep corpora lazy; previews must not generate candidates.
- **External corpora stay external:** no bundled large wordlists or implicit downloads.
- **License-aware:** retain corpus licensing and source attribution.
- **Avoid combinatorial explosion:** small primitives/templates and per-word caps.
- **Local-first:** data and generation stay in the operator's workspace.
- **No active attack execution:** no remote authentication, spraying or brute force.
