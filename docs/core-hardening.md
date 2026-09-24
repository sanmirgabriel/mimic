# Block 2 — Core hardening contracts

Implemented: validation, Unicode-safe leet indexing, Unicode policy classes,
calendar validation, empty input filtering, conservative input dedup, bounded
year ranges, seedless rule export and YAML CI coverage. No scoring, ranking,
datasets, application service, API or UI is introduced here.

## Profile input

Both `TargetProfile.from_dict` and direct construction validate the five scalar
fields as `str | None` and `apelidos` as `list[str]`. Integers, booleans and other
types are rejected with field-specific `ValueError`; no coercion takes place.
Only external whitespace is stripped. Empty scalars become `None`; empty
nicknames are removed. Accents, case, internal spaces and Unicode normalization
are not changed. Origins created by `build_plan` refer to these validated,
normalized profile values. The dataclass remains mutable; this is construction
validation, not assignment interception.

Malformed YAML is converted to `ValueError` for the existing CLI error path.
Empty YAML remains an empty profile; false/list top-level YAML is rejected as
a non-mapping. PyYAML remains the optional `profile` extra; CI now installs
`.[dev,profile]`. Remote CI results are not implied by local test results.

## Unicode

Leet examines each original codepoint separately. A lowercase expansion such
as `İ -> i + combining dot` is not a map key and is left untouched; later
eligible characters retain their original indices. No transliteration or
casefolding is performed. The map and ASCII output order are unchanged.
Transformation positions still index the original input of that operation.

PasswordPolicy uses `str.isupper`, `islower`, `isdigit`, and `not isalnum` per
codepoint. Accented letters are letters, not specials. Arabic-Indic digits and
other Python digit characters (including superscript digits) satisfy digit.
Whitespace, including spaces and tabs, **continues to count as special**.
Combining marks are also non-alphanumeric codepoints; no Unicode normalization
or grapheme-cluster interpretation is performed. Length is still `len(str)`.

## Calendar and configuration

DateMutator validates real Gregorian dates with `datetime.date`. Yearless
dates are checked against the leap year 2000 solely for validation, so `29/02`
is accepted and `31/04` is rejected. No sentinel year is emitted or added to
provenance. Dates with a supplied year use that year, including its leap-year
rules. Token formats, first-format dedup and ordering remain unchanged.

Generator requires an integer `max_candidates_per_word >= 1`. Policy lengths
must be integers >= 0, and min <= max when max is nonzero. Zero max still means
unlimited. Booleans/floats are not accepted as integer configuration. Invalid
types raise `TypeError`; invalid numeric ranges raise `ValueError` before
generation. CLI catches these configuration errors and returns 1 without
opening the output file. Greedy cap selection is unchanged.

`--year-range` accepts ascending inclusive integer intervals of at most **200
tokens**; the limit is checked before constructing the list. Equal endpoints
are valid. No new calendar-year restriction is imposed on these generic affix
tokens. Reversed or oversized intervals and malformed endpoints raise
`ValueError` and produce CLI exit code 1.

## Empty inputs and dedup

`mimic.core.seeds` centralizes Generator/Combine boundary handling. It discards
empty or whitespace-only seeds. Nonempty explicit API values are not stripped
or rewritten, avoiding an unrecorded change to Candidate.value or its origins.
File/CLI and profile inputs keep their own input-format strip rules.

Input dedup compares the **complete causal candidate**: value, origins and
transformations. This is a conservative equivalence test for deterministic
Candidate transformations, not an attempt to identify all equivalent values.
Same value with different origins/history is retained, because a custom
structured mutator may inspect that metadata. Exact repeated derivations are
skipped in first-encounter order; a set is used only for membership.

Base seeds retain their Combine eligibility independently of duplicate isolated
seeds. Combine filters/deduplicates its partners without collapsing different
causes or case variants. Expanded seeds are also deduplicated before stages.
Global output dedup remains value-based, before policy, with the first causal
derivation winning. Alternative causes are not merged.

Custom stateful mutators must not rely on repeated calls for identical input
derivations. Call counts for duplicates intentionally decrease. This optimization
does not claim to preserve side effects of such repeated calls. Input dedup
retains causal keys in memory, including expanded seeds; it is not a bounded
memory strategy and does not solve Combine's quadratic growth.

## Rule export and output

`--export-rules` no longer requires names/profile and does not implicitly read
stdin. Optional explicitly supplied files are still read and validated. With
no numeric tokens, basic identity/case/reverse/leet rules are exported according
to the unchanged exporter. Generation-only policy/cap options remain unused in
rule-export mode. The exporter implementation itself is unchanged.

Sink implementation is unchanged. Direct tests verify incremental iterator
consumption, stdout ownership, UTF-8, counts, empty files, file closure and
propagation of write failures. Output files still use ordinary non-atomic writes.

## Follow-ups (not implemented)

- ProfilePlan's textual and structured fields remain separate mutable snapshots,
  as documented by ADR 0001. No source-of-truth API redesign was performed.
- Combine remains quadratic; no dataset guard, budget or fairness algorithm.
- Global dedup is unbounded and does not periodically flush.
- Hashcat still has an independent transformation implementation.
- Core settings and TargetProfile remain mutable after construction.

The preexisting README edit is preserved. Only tracked `.pyc` artifacts were
removed, as requested by Block 2; no broad cache cleanup was performed.
