# MIMIC product backlog

Canonical product epics. Block 7 is implemented and audited in the working tree,
awaiting operator review.

| Block | Epic | Scope |
| --- | --- | --- |
| 7 | Password Intelligence Foundation | Versioned primitives, contextual seeds, services, organization-only flow, causal provenance. |
| 8 | Dataset & Knowledge Packs | External, streaming, license-aware packs and dataset management. |
| 9 | Service Intelligence + Default Credential Catalog | Broader technology context; separately modeled credential pairs. |
| 10 | Scoring / Ranking / Budgets | Explainable prioritization and explicit generation budgets. |
| 11 | Observed Password Pattern Learning | Authorized observations and attributable learned patterns. |
| 12 | Password Popularity / Frequency | Frequency knowledge with transparent sources and licensing. |
| 13 | Hashcat Convergence | Consistent material and rule export through the existing engine. |
| 14 | AI Context Assistant | Assisted context extraction through the application service. |
| 15 | Documentation / Operator UX | Documentation overhaul and operator workflow improvements. |
| 16 | Benchmarking / Release Hardening | Reproducible benchmarks, packaging and release gates. |

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
