# MIMIC product backlog

Canonical product backlog and delivery direction, updated 2026-10-13. Blocks
7–10 are merged in `main` (Block 10: PR #13; CI on Python 3.10/3.11/3.12
passed). **Block 11 is implemented; Gate 11 recommends operator commit review.** Older audit
notes below record the pre-merge state at the time of their execution; this
table is the current source of truth for delivery status.

| Block | Epic | Scope |
| --- | --- | --- |
| 7 | Password Intelligence Foundation ✅ | Versioned primitives, contextual seeds, services, organization-only flow, causal provenance. |
| 8 | Scoring / Ranking / Budgets ✅ | Explainable prioritization and explicit generation budgets. |
| 8.4 | Partial-Leet Coverage Fix ✅ | Original candidate first, then up to max_subs replacements; causal provenance, ranking, caps and compatibility validated. |
| 8.5 | Web Internationalization + Theme Switcher ✅ | PT-BR/EN, dark/light and responsive local UX. |
| 9 | Dataset & Knowledge Packs ✅ | Local digest-pinned, attributable, versioned Seed/Ready corpora and CLI/Web management. |
| 10 | Service Intelligence + Default Credential Catalog ✅ | Seven service profiles, source-qualified default pairs, separate common values, local lookup/export, opt-in ready candidates. |
| 11 | Observed Password Pattern Learning (implemented; ready for operator commit review) | Bounded local authorized analysis, versioned aggregate artifacts, CLI analyze/show, read-only Web lookup and explicit structural filtering through the existing engine. |
| 12 | Password Popularity / Frequency | Versioned empirical pattern frequencies, with representativeness, licensing and transparent evidence. |
| 13 | Hashcat Convergence | Differentially verified, honest rule/base exports aligned with supported existing transformations. |
| 14 | Service Catalog Expansion | Grow reviewed technology/default-credential knowledge with sources, applicability and versions. |
| 15 | Offline Password Quality Audit | Local analysis of authorized password-quality samples, policy compliance, weak patterns and aggregated reuse. |
| 16 | Effectiveness Benchmark | Reproducible Recall@K, latency, memory, evaluated-candidate and pattern-coverage measurements. |
| 17 | Audit Reports & Explainability | Local HTML/PDF reports, redaction, provenance, methodology and honest limitations. |
| 18 | Audit Presets & Workflows | Reusable, transparent presets for organization, service, weak-password and offline-audit workflows. |
| 19 | Optional AI Context Assistant | Reviewed, opt-in context extraction; no remote dependency or autonomous execution. |
| 20 | Open Source / Documentation / Operator UX | Fix README; guides, static project site, contributor/security workflows and community onboarding. |
| 21 | Benchmarking / Release Hardening / Distribution | Packages, performance/security gates, releases and maintained compatibility contracts. |

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
- Follow-up Block 10 is implemented below, pending Gate 10 approval.

## Block 10 — Service Intelligence + Default Credential Catalog (implemented; Gate 10 approval pending)

- Frozen, packaged service knowledge and a shared local lookup/export catalog.
  Documented credential pairs, common independent values and generated hypotheses
  remain separate. Only Grafana admin/admin and RabbitMQ guest/guest are included
  as documented defaults, with official sources and installation restrictions.
  PostgreSQL/WordPress have explicit authentication notes and no universal pair.
- Existing five profiles retain their tokens, roles, order and knowledge-v1.
  Grafana/RabbitMQ append real contextual vocabulary to the existing bounded
  intelligence planning and single Generator. Service-only and organization +
  service flows retain causal service identity, caps, policy and budgets.
- Six common usernames are read-only references. Six independent weak passwords
  enter generation only through an explicit CLI/Web/request option as ready,
  noncombinable Seeds, with knowledge.common_password provenance. Disabled old
  requests and summaries retain their JSON shape; enabled Job snapshots pin the
  common-v1 collection. No new score weight, Cartesian product or mutation path.
- CLI offers services list/show and credentials list/export, with separate CSV
  schemas for documented pairs and common values. Export retains conditions,
  uses CSV/formula safeguards and preserves existing destination files.
- SSR /services provides search, technology details, sources and distinct badges;
  /generate?service=ID preselects the existing form without starting generation.
  PT-BR/EN metadata and notes, dark/light semantic tokens and mobile table overflow
  use existing locale, CSP, CSRF, HTMX and theme behavior. No frontend dependency.
- No new API endpoints, database/migration, active authentication, downloads,
  scraping, frequency scoring or second engine. README, Core, mutators,
  intelligence/domain planning and score-v1 remain unchanged.
- Baseline: **933 passed** at 3d75a239 in 46.59 seconds wall time. Final full
  suite: **994 passed** in 47.79 seconds wall time (47.18 pytest seconds), with
  all 933 original test nodes retained and 61 new cases; new IDs stay short.
  All 16 comparisons against the base preserve output bytes, order, provenance,
  scores/ranks and counts, including ACME + WordPress at 159175 evaluated.
  New generation paths match across hash seeds 1/42/777.
- Wheel/sdist include the catalog and Web assets. The wheel installed outside
  the checkout passes CLI/server smoke checks and pip check. Firefox validates
  96 page/locale/theme/width combinations at 375/768/1440px, search, preview,
  completed Job/download and keyboard focus; 168 badge contrast samples have
  a minimum ratio of 6.36:1. CI workflow/matrix remain unchanged; these are local
  validation results, not a remote CI run.
  See [ADR 0010](adr/0010-service-intelligence-default-credentials.md).
- **Implemented; pending approval at Gate 10. No commit, push or merge.**
- Gate 10 pre-commit audit (2026-10-09): initial **994 passed** in 72.99 seconds
  wall time; after 50 audit/regression cases, final **1044 passed** in 57.41
  seconds wall time (56.74 pytest seconds). All 933 base nodes remain present;
  the longest new test ID is 111 characters. Local timings vary with system load.
- Gate fixes: reject malformed HTTPS hosts/ports, empty userinfo, C1 controls,
  Unicode line separators, oversized metadata and invalid version syntax;
  CSV publication now stages, flushes/syncs and atomically refuses existing
  destinations, cleaning up on
  write/publication failure. Empty-state wording is explicitly scoped to this
  catalog. The ADR clarifies exact values, spreadsheet representation and the
  version-ID contract (no request content digest for these built-ins).
- Gate evidence: all 16 comparisons against the required base still match;
  seven new determinism scenarios compare full result metadata across seeds
  1/42/777. Fresh wheel/sdist and the outside-checkout installation pass CLI,
  Quick Top-100, server and pip check. Firefox reproduced the 96 layout cases
  and 168 badge contrast checks (minimum 6.36:1), including local-only resources
  and a completed Job. No remote CI result is claimed.
- **Next: Block 11 — Observed Password Pattern Learning. Not started.**

## Block 11 — Observed Password Pattern Learning (implemented; ready for operator commit review)

- Local, explicitly authorized streaming analysis with strict UTF-8, fixed or
  explicitly bounded years, twelve explainable structures, descriptive sample
  frequencies and a conservative five-occurrence display threshold.
- Versioned, strictly validated aggregate JSON; CLI `patterns analyze/show`,
  safe publication without overwrites, and PT-BR/EN read-only Web consultation.
  No password uploads, persistent observation Jobs, raw-value retention or remote
  processing. SPECIAL suffixes are analysis-only; unsupported shapes are counted.
- Opt-in structural filtering delegates to the existing GenerationService,
  preserving actual candidate provenance, caps, policy, score-v1 and Top-K.
  Blocks 12–21 remain planned; the original roadmap below is preserved.
- See [ADR 0011](adr/0011-observed-password-pattern-learning.md) and the
  [implementation report](BLOCK11_IMPLEMENTATION_REPORT.md) for contracts,
  compatibility evidence, privacy limitations and Gate 11 review readiness.
- Gate 11 independent pre-commit audit (2026-10-13): **1,216 passed initially;
  1,256 passed after 40 audit cases**. Corrections pin Web directory/file reads,
  sanitize directory failures, consume short-read JSON streams through EOF within
  the artifact limit, and remove private argparse exception context. No additional
  structures, generation engine or frequency scoring were introduced.
- All 16 application/two CLI comparisons against the required base still match;
  24 Firefox locale/theme/viewport cases, empty/suppressed/invalid states, keyboard
  and contrast checks pass. Wheel/sdist and outside-checkout CLI/SSR pass.
  Suppression inference and platform/runtime limits are explicitly documented in
  [the Gate report](GATE11_AUDIT.md). Recommendation: **ready for operator commit
  review**; no commit, push or merge performed; Block 12 remains unstarted.

## Product vision and delivery roadmap (Blocks 11–21)

**Vision:** MIMIC is an open-source, local-first *Password Security Intelligence & Audit Platform* for authorized assessments. It should help an operator answer: **what is worth evaluating, why was it selected, and what evidence supports the decision?**

Five connected product pillars:

1. **Knowledge Base** — curated services, documented initial credentials with applicability/source/version, independent common weak values, and versioned external knowledge packs.
2. **Password Intelligence** — target-, organization- and service-aware candidate generation, bounded mutations, explainable provenance, priorities and budgets.
3. **Offline Password Audit** — local, explicitly authorized analysis of password-quality samples, policies, duplicates and aggregate patterns; no remote guessing.
4. **Research & Benchmarking** — observable pattern structures, empirically qualified frequencies and reproducible coverage/Recall@K measurements.
5. **Pentest Operator Workflow** — presets, interoperable outputs, reports, reproducible jobs and simple PT-BR/EN UX.

The product is **usable now** as a local candidate generator and passive service-credential reference (through merged Block 10). It is **not yet** a comprehensive catalog or an offline password-quality analyzer; those are planned below. There is no built-in password spraying, brute forcing, credential stuffing, online validation, cracking or autonomous targeting.

### Phase 1 — Learn and measure (11–13)

**Block 11 — Observed Password Pattern Learning (NEXT)**

- Analyze only operator-supplied, authorized, local observations; support synthetic fixtures for tests. Separate **learning pattern structures** from retaining or exporting raw secrets.
- Infer a deliberately small, deterministic grammar such as `WORD + SEPARATOR + YEAR`, `WORD + DIGITS`, `ACRONYM + YEAR` with counts, source label, sample size and extraction rules. No predictive-success claims, no opaque ML, no auto-scraping.
- Introduce a minimal application-level analyzer with bounded input, streaming and explicit error reporting; never put raw observations into Job snapshots, debug logs, exceptions, reports, filenames or analytics by default.
- Permit optional, constrained reuse only through the **existing** generation service/mutators for shapes actually representable; unsupported shapes must be reported, not simulated by a second engine. Do not change `score-v1` silently.
- **Gate 11:** privacy and non-persistence tests; parsing/matching ambiguity; duplicates and deterministic counts; malformed, huge and Unicode inputs; representative PT-BR patterns; PYTHONHASHSEED consistency; old outputs byte-identical; no material hot-path regression; wheel/sdist/CLI smoke. Begin measuring quality on synthetic or explicitly authorized holdout data, without exposing plaintext.

**Block 12 — Password Popularity / Frequency**

- Add versioned, provenance-rich aggregate frequency datasets and metadata (sample size, origin, collection period, representativeness, geography/sector if supportable, license, limitations).
- Keep empirical frequency separate from existing heuristic `score-v1`; do not imply global or Brazilian-wide probabilities or backfill invented statistics.
- Compare alternatives in a transparent evaluation workflow before considering opt-in influence on prioritization.
- **Gate 12:** source/licensing audit, aggregate privacy review, bias/holdout checks, deterministic ranking, compatibility and evidence reproducibility.

**Block 13 — Hashcat Convergence**

- Align existing Hashcat `.rule` export with candidate generation where the Hashcat rule language can express an equivalent transformation; report unsupported behavior clearly.
- Provide paired base material and rules with provenance/format documentation, not a new cracking engine.
- **Gate 13:** differential comparison of generated candidates vs. rules over supported cases, output escaping, performance and backward compatibility.

### Phase 2 — Knowledge base and offline quality (14–16)

**Block 14 — Service Catalog Expansion**

- Grow beyond seven initial technologies/two documented pairs, curated by category: observability/admin panels, databases, web/CMS, message brokers, networking/identity and relevant distributions/deployment variants.
- Each documented initial pair needs trustworthy evidence, installation/release applicability, restrictions and revision history; no invented universal defaults. Clearly distinguish usernames/conventions, documented pairs, generic weak values and heuristics.
- Prefer small reviewed additions with source/version tests and community review rather than a giant unverified corpus. Packs handle external corpora.
- **Gate 14:** credible source audit, schema/dedup, search usability, safe display/CSV, PT-BR/EN accuracy, wheel packaging and determinism.

**Block 15 — Offline Password Quality Audit**

- Locally assess explicitly provided authorized material for length/complexity-policy conformity, predictability and organization-specific patterns, weak-list overlap, and exact reuse where the supplied material permits it.
- Separate policy compliance from actual password strength. Use aggregate results by default; never persist plaintext by default or imply reliable crackability from arbitrary entropy formulas.
- Consider a sensitive-data import path isolated from routine Job storage and logs, with file size limits, clear lifecycle and safe cleanup.
- **Gate 15:** data-exposure and retention tests, malformed/Unicode/large inputs, policy correctness, known-fixture findings, clear limitations and no remote actions.

**Block 16 — Effectiveness Benchmark**

- Make candidate effectiveness measurable: Recall@100, @1,000, @10,000, rank distributions, coverage by pattern family, generation latency, memory, evaluated count and artifact size.
- Establish independent authorized/synthetic evaluation sets with train/holdout discipline. Do not publish sensitive corpora or boast unsupported success rates.
- Compare baselines and regressions repeatably; record configuration/catalog/package versions and machine conditions.
- **Gate 16:** reproducible methodology, no test-set leakage, interpretable metrics and CI-friendly smoke benchmarks. Start basic benchmark capture already in Block 11.

### Phase 3 — Professional operator UX (17–19)

**Block 17 — Audit Reports & Explainability**

- Provide local HTML/PDF reports about scope/context, sources, policies, observed aggregate weaknesses, candidate-generation settings, score/provenance and evaluation limitations.
- Redact raw passwords and sensitive target data by default; any inclusion must be deliberate and explicit. Report results are not evidence of successful authentication.
- **Gate 17:** report provenance and consistency, redaction/escaping, PT-BR/EN, reproducible export and secure temp handling.

**Block 18 — Audit Presets & Workflows**

- Add transparent, editable presets for Corporate Context, Service Assessment, Weak Password Review and Offline Audit Preparation.
- Presets configure **existing** features; never start remote auth or unreviewed generation automatically. Preview consequences and budgets before execution.
- **Gate 18:** preset roundtrip, old defaults unchanged, no second engine, mobile/keyboard UX and deterministic outputs.

**Block 19 — Optional AI Context Assistant**

- Assist with extracting technology/context and proposing structured inputs, always reviewed and validated by the application service before use.
- Core product remains offline and functional without AI. External providers and any transmission of private data must be separate explicit opt-ins; prefer local models when feasible.
- **Gate 19:** fail-closed validation, privacy consent, no autonomous execution, auditable suggestions, zero dependency of core tests on remote services.

### Phase 4 — Community and release maturity (20–21)

**Block 20 — Open Source / Documentation / Operator UX**

- Fix the presently stale README (which describes already-merged Web/API/ranking as future); create accurate Quickstart, CLI/API/Web use guides, operator workflows, screenshots, examples and boundaries.
- Prepare `CONTRIBUTING.md`, `SECURITY.md`, code of conduct, issue/PR templates, changelog and a source-review rubric for catalog contributions; distinguish MIT code licensing from independent datasets/attribution.
- Ship a **static** project/documentation website and, if useful, an explicitly non-sensitive catalogue demo. No public execution of the Python backend and no collection of passwords.
- **Gate 20:** clean-room installation on supported platforms, first-use UX, docs accuracy, contributor flow and sensible issue/security disclosure process.

**Block 21 — Benchmarking / Release Hardening / Distribution**

- Package reproducible, tested versions; wheel/sdist, release automation, compatibility/security regression checks, changelog and GitHub Releases.
- Assess PyPI package name and publishing permissions before promising `pipx install mimic`; consider `pipx`, install-from-GitHub and optional standalone packages.
- Establish release/upgrade compatibility, source hashes and security-response/maintenance process. Build toward `v1.0.0` based on validated stability and user feedback, not simply completion of features.
- **Gate 21:** installed-artifact smoke across Python matrix, performance baselines, docs/packaging integrity and rollback/release checks.

### Release milestones (cross-cutting, not extra Blocks)

- **A — Public experimental release:** after focused installation/security/README review, publish a `v0.1.0`-style release **before** all future blocks are finished. No claim of product stability beyond validated contracts.
- **B — Intelligence preview:** after Blocks 11–13, demonstrate deterministic learning/evidence/Hashcat interoperability with reproducible tests.
- **C — Audit platform preview:** after Blocks 14–18, curated service depth, offline audit, effectiveness metrics, reporting and presets.
- **D — Stable release candidate:** after user testing and release hardening, consider `v1.0.0` when the stability bar is actually met.

### Open source, hosting and sustainability

- **Distribution model:** keep source code and core local-first functionality available for free under the repository license. Everyone runs the engine and audits on their own machine. Review dataset licenses independently; no automatic redistribution of third-party leaks.
- **Public presence:** GitHub source/releases/issues/discussions; optional static documentation/landing site on GitHub Pages or Cloudflare Pages. No server-side processing required to present the project/catalog.
- **Cost baseline:** repository + static hosting can start at free tiers; an optional domain is the main initial recurring purchase. Review plan limits and prices before commitments; developer time and maintenance are real costs.
- **Support model:** optional GitHub Sponsors/donations and paid enterprise support, training or custom integrations, without removing the free local core. Don't expect donations to fund essential infrastructure early on.
- **Hosted SaaS:** defer until there is real demand and a separate threat-model/design covering account security, isolation, abuse prevention, CPU/memory budgets, logging, retention, compliance and billing. **Never expose the present loopback-only application directly as a public multi-tenant backend.**
- **Community source contributions:** require documentation/evidence, version/applicability, redistribution rights and CI validation for new default-credential records or packs; maintainers review changes before accepting them.

### Permanent architecture / quality bar for Blocks 11–21

- Local-first and deterministic; source/version/digest pinning where supported; provenance retained and explainable.
- One existing generation engine; no independent password generator, cracking engine, remote login tester, spraying tool or scanning stack hidden in the knowledge layer.
- Bounded streaming and budgets, minimal abstractions, quick UI and measurable performance; avoid overengineering.
- Private or user-provided password observations are sensitive: no remote transmission, raw logging or persistence by default; explicitly authorized analysis only.
- Clear difference between documented defaults, common weak values, heuristic candidates, observed structures and empirically supported frequencies.
- No changes to legacy outputs or score-v1 without explicit versioned contract, migration rationale and regression proof.
- Delivery discipline: implement on feature branch → tests → Gate audit → review diff → operator's **manual commit** → PR/CI → manual merge. AI agents never commit, push or merge.

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
