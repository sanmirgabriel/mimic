# MIMIC product backlog

Canonical product epics. Blocks 7 and 8 are merged. Block 8.4 is implemented
and validated in the working tree. Block 8.5 remains the next product milestone.

| Block | Epic | Scope |
| --- | --- | --- |
| 7 | Password Intelligence Foundation ✅ | Versioned primitives, contextual seeds, services, organization-only flow, causal provenance. |
| 8 | Scoring / Ranking / Budgets ✅ | Explainable prioritization and explicit generation budgets. |
| 8.4 | Partial-Leet Coverage Fix ✅ | Original candidate first, then up to max_subs replacements; causal provenance, ranking, caps and compatibility validated. |
| 8.5 | Web Internationalization (PT-BR / EN) | Immediate next product milestone: PT-BR default/selectable and English selectable; UI labels/messages only, with no duplicated business logic. |
| 9 | Dataset & Knowledge Packs | External, streaming, license-aware packs and dataset management. |
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
- **Next milestone: Block 8.5 — Web Internationalization (PT-BR / EN).**

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
