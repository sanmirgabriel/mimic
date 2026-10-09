# MIMIC product backlog

Canonical product epics. Blocks 7, 8, 8.4 and 8.5 are merged. Block 9 is implemented
and Gate 9 audited in the working tree, pending approval before completion/commit.
Block 10 is the next major product milestone.

| Block | Epic | Scope |
| --- | --- | --- |
| 7 | Password Intelligence Foundation ✅ | Versioned primitives, contextual seeds, services, organization-only flow, causal provenance. |
| 8 | Scoring / Ranking / Budgets ✅ | Explainable prioritization and explicit generation budgets. |
| 8.4 | Partial-Leet Coverage Fix ✅ | Original candidate first, then up to max_subs replacements; causal provenance, ranking, caps and compatibility validated. |
| 8.5 | Web Internationalization + Theme Switcher ✅ | PT-BR default and selectable EN; compact language/theme controls, dark/light palettes and local preferences; presentation only. |
| 9 | Dataset & Knowledge Packs (approval pending) | Local versioned UTF-8 packs, digest-pinned snapshots, attribution, streaming Seed/Ready sources and CLI/Web management; Gate 9 audited. |
| 10 | Service Intelligence + Default Credential Catalog | Next major block: broader technology context; separately modeled credential pairs. |
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
- Source-management follow-up: implemented Block 9 below, awaiting approval.

## Block 9 — Dataset & Knowledge Packs (implemented; approval pending)

- One local registry stores JSON manifests and managed corpora under
  `DataPaths.packs`, respecting custom data directories. Import validates UTF-8,
  counts physical lines and hashes/copies in 64 KiB chunks, then publishes a
  complete version atomically. Identical imports are idempotent; conflicting
  content or immutable metadata is rejected. No download, update, remove or new SQLite table.
- `seed` sources use normal mutations; `ready` sources bypass them. Both are
  noncombinable. Provenance keeps canonical dataset/ready_candidate sources
  and records `pack:id@version:physical-line`, without operator paths.
  Existing source precedence and first causal derivation wins are preserved.
- Ordered references capture expected SHA and immutable manifest metadata in
  GenerationRequest/Job snapshots. Preview reads manifests only; execution
  verifies every selected corpus before emitting candidates, holds confined
  regular-file descriptors and checks integrity again while streaming.
  Missing/altered sources fail explicitly; cancellation and atomic job output
  remain intact. CLI pack output files are also staged before publication.
- CLI delivers `packs list/show/import/verify` and repeatable `generate --pack`,
  with `--data-dir`. Web offers import, details, integrity verification and
  compact selection in the existing generation form. PT-BR/EN catalogs now
  contain 440 matching keys; existing theme/locale behavior is unchanged.
  Unknown licenses display a redistribution warning; declarations are not
  legal audits. The original Brazilian fixture is opt-in test/demo data.
- Implementation baseline: **758 passed** on `0949c21`; pre-Gate suite: **836 passed**, including
  78 new pack/Web cases. Integrity, traversal, symlinks, interrupted imports,
  write/permission failures, concurrent imports, snapshots, precedence and
  cancellation are covered. Hash seeds 1/42/777 produce identical evidence.
- Ten legacy scenarios match Block 8.5 in bytes, order, causal metadata and
  scores; ACME + WordPress still evaluates 159,175 candidates without packs.
  Separate legacy/modern CLI comparisons also match. Ready/Seed smoke corpora
  use 10,000 physical lines, evaluating 10,000/30,000 candidates with a top-100
  budget; incremental verification peaks around 204 KiB. Existing Core dedup
  remains O(N), with no additional corpus cache in the pack layer.
- Wheel/sdist/install resources match byte-for-byte. Installed CLI and HTTP
  validate bidirectional CLI/Web pack access, preview, completion, provenance
  and download. Firefox passes 72 cases across PT-BR/EN, dark/light and
  375/768/1,440px, plus long-metadata wrapping at 375px and native verification.
- Core, mutators, Intelligence, score-v1, API endpoints, schema, dependencies,
  locale/theme scripts and README remain unchanged. No commit, push or merge.
  See [ADR 0009](adr/0009-dataset-knowledge-packs.md) for source order, local
  SecLists import, license metadata, integrity boundaries and limitations.
- Gate 9: **836 passed before corrections; 933 passed after corrections**,
  including 97 additional audit cases (175 pack/Web/Gate cases total). Fixes
  reject every immutable metadata conflict, require all manifest fields,
  serialize `physical_line_count`, reject invalid Unicode/URL controls and
  clean empty staging on descriptor-open failure. Deterministic tests cover
  concurrent conflicting imports, buffered/in-place/replaced-file semantics,
  stdout/file publication, verifier cancellation, pending snapshots, the Job
  failure matrix, two isolated CLI/Web/API data directories and lazy preview.
- Gate 9 installed-wheel Firefox validation passes 97 cases in PT-BR/EN,
  dark/light and 375/768/1,440px, including native upload/verify and long names.
  Wheel/sdist resources match; `pip check` passes. Ten legacy scenarios still
  match exactly. Ready/Seed 10k runs evaluate 10k/30k and retain 100, using about
  29/33 MiB process RSS and 205 KiB verification peak. No-pack median runtime
  is 2.46s base versus 2.44s current; RSS is 44.4 versus 49.5 MiB, predominantly
  fixed hashing/import initialization. A 16 MiB single line reaches 87 MiB RSS;
  the ADR proposes a future import-time line ceiling after compatibility review.
- Gate recommendation: ready for commit review. Product completion remains
  pending approval; no commit, push or merge has been performed.
- **Next major block: Block 10 — Service Intelligence + Default Credential Catalog.**

## Future enhancements

- **Ranking diversity / family-aware candidate selection:** consider diversity
  between related candidate families in a future ranking block, with explicit
  semantics, provenance and deterministic validation. Not implemented in 8.5 or 9.

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
