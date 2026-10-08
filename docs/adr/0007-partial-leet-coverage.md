# ADR 0007: Preserve zero substitutions in partial leet

Status: Accepted (Block 8.4)

## Context

Historical partial leet emitted only 1..max_subs replacements for eligible
words. The composed Case → Leet → Affix pipeline consequently lost both the
unmodified hypothesis and its affixes. Score-v1 already penalized each real
replacement by two points, but often had no equivalent zero-leet cause to rank.
ADR 0006 records why Block 8 retained that historical output.

## Decision

Partial emits the input Candidate itself first, followed by the existing ordered
combinations of 1..min(max_subs, eligible_positions) replacements. Its local
dedup starts with the original value. Zero replacements adds no Transformation:
value, origins and prior transformations remain exactly those of the input.
Words without eligible positions still yield that Candidate exactly once.
None/full semantics and Unicode codepoint indexing remain unchanged.

No constructor validation is added. Zero and negative max_subs were accepted
previously and produced no output for eligible words; they now preserve only the
original. Existing min/range behavior for non-integers remains: None/strings
raise TypeError for eligible words; floats can raise or be clamped to an integer
eligible count, and booleans retain integer-like behavior. Invalid configurations
may now yield the original before the same lazy iteration error.

## Consequences and validation

Partial output deliberately breaks historical byte compatibility for exhaustive,
ranked and legacy CLI flows. None/full snapshots and before/after stream hashes
(values and full Candidate metadata) remain identical. Score-v1, Top-K, budgets,
ServiceProfiles, Affix order, Generator dedup/caps and DB user_version 2 are unchanged.

With intelligence enabled, reference year 2026 and default separators/cap 5,000:

| Context | Partial before | Partial after | Affix truncations before → after |
| --- | ---: | ---: | ---: |
| Organization ACME | 82,447 | 86,013 | 14 → 15 |
| ACME + WordPress | 152,263 | 159,175 | 28 → 29 |
| Target Pedro (profile.nome=Pedro) | 22,913 | 26,479 | 2 → 3 |

Original-first ordering changes which substitutions reach Affix before its cap;
the new stream need not contain every former partial result. In ACME + WordPress,
zero/one/two-leet counts change from 753/64,359/87,151 to 17,005/61,347/80,823.
The fixed cap remains intentional, rather than increasing it to compensate.

Quick still scans the whole stream and retains 100. Its observed top 100 now have
zero substitutions; equivalent original-case contextual candidates score
56/54/52 for zero/one/two replacements, solely through the existing leet penalty.
Direct ordering/provenance, repeated positions, Unicode, cap priority, Generator
integration, legacy/modern CLI, exhaustive/ranked jobs and three hash seeds are
covered by tests. No ranking preference for a chosen literal is introduced.
