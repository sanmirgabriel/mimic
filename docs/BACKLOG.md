# MIMIC product backlog

Canonical product epics. Block 7 is merged. Block 8 is implemented in the working tree,
under Gate 8 audit and awaiting operator review.

| Block | Epic | Scope |
| --- | --- | --- |
| 7 | Password Intelligence Foundation ✅ | Versioned primitives, contextual seeds, services, organization-only flow, causal provenance. |
| 8 | Scoring / Ranking / Budgets | Explainable prioritization and explicit generation budgets. |
| 8.5 | Web Internationalization (PT-BR / EN) | Immediate next product milestone: PT-BR default/selectable and English selectable; UI labels/messages only, with no duplicated business logic. |
| 9 | Dataset & Knowledge Packs | External, streaming, license-aware packs and dataset management. |
| 10 | Service Intelligence + Default Credential Catalog | Broader technology context; separately modeled credential pairs. |
| 11 | Observed Password Pattern Learning | Authorized observations and attributable learned patterns. |
| 12 | Password Popularity / Frequency | Frequency knowledge with transparent sources and licensing. |
| 13 | Hashcat Convergence | Consistent material and rule export through the existing engine. |
| 14 | AI Context Assistant | Assisted context extraction through the application service. |
| 15 | Documentation / Operator UX | Documentation overhaul and operator workflow improvements. |
| 16 | Benchmarking / Release Hardening | Reproducible benchmarks, packaging and release gates. |

## High-priority follow-up after Block 8

- **HIGH-PRIORITY FOLLOW-UP — preserve the zero-substitution hypothesis in partial leet.**
  Historical `LeetMutator(mode="partial")` emits only 1..max_subs substitutions
  for eligible words. The staged pipeline therefore omits their unmodified
  and unmodified-plus-affix hypotheses (except independent branches or other
  sources). Gate 8 preserves this byte-compatible behavior. In the next cycle,
  explicitly decide whether partial should include zero substitutions; validate
  case/affix combinations, caps, provenance and changed counts/order before
  accepting that compatibility change. This coverage debt is independent of
  scoring weights and must not be fixed by tuning them.

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
