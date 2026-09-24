# ADR 0001 — Causal candidates in the streaming pipeline

Status: implemented in Block 1.

## Context

String-only generation discarded seed identity and transformation history.
Substring matching could not explain reverse, distinguish coincidental tokens,
or identify both operands of a combination. Scoring will need actual causes,
not guesses reconstructed from a final password.

## Decision

`mimic.core.candidate` defines frozen `Origin`, `Transformation`, and `Candidate`
dataclasses. Origins carry generic source/field/value strings. Core does not
import or inspect `TargetProfile`. The profile loader and CLI create origins;
plain strings passed to the Python API receive `api.seed` / `api.numbers`
origins. Callers may explicitly supply an originless Candidate; the engine
does not fabricate missing context for it.

Candidate collections are tuples. Transformation parameters are unique string
key/value pairs, sorted by key and stored as tuples. `dataclasses.asdict` plus
`json.dumps` serializes these models without custom encoders. Equality and
serialized ordering are stable; Python's numeric string hash is not promised
to be stable across processes.

Built-in mutators implement `mutate_candidate(Candidate)`. Their inherited
`mutate(str)` projects values from that same implementation. Generator accepts
strings or Candidates, exposes `generate_candidates()`, and preserves
`generate() -> Iterator[str]` as the value projection.

External subclasses implementing only `Mutator.mutate` still work. Their
adapter records an explicit `legacy` operation with implementation name and
actual input/output. Internal operations or additional hidden sources are
unknown; implement `mutate_candidate` to provide detailed provenance.

## Transformation vocabulary in this block

- `case`: mode `original`, `lower`, `upper`, or `title`. Original is an explicit
  case branch, including when it wins dedup against a later identical branch.
- `leet`: one record per actual substitution, with mode, original character,
  replacement and zero-based codepoint position in that operation's input.
  Identity paths in leet add no operation.
- `date`: original input and selected format: `ddmm`, `mmdd`, `dmm`, `mdd`,
  `yyyy`, `yy`, `ddmmyyyy`. Duplicate tokens keep their first format.
- `affix`: input, token, token placement (`prefix`/`suffix`), separator and
  separator position (`none`, `between`, `after`, `before`). For example,
  `word + token + @` is suffix/after; `@ + word + token` is suffix/before.
  The unchanged word retains its metadata without adding an affix operation.
- `combine`: actual left/right inputs in output order, lower normalization,
  left form (`full`/`initial`), right form (`full`) and separator.
- `reverse`: explicit reversal of its input seed, independent of stages.

Affix and Combine join **actual operands**, retaining ordered unique origins
and both histories. Histories are flattened as input/left history, token/right
history, then the joining operation. `input_steps`/`token_steps` or
`left_steps`/`right_steps` preserve the operand history boundaries. This is an
ordered causal description, not a claim that date operations ran on the word.
Identical origins within the same derivation are recorded once; operations
are never removed from operand histories.

## Dedup: first causal derivation wins

Both per-stage and global dedup remain keyed by candidate **value**. The first
encountered derivation is canonical. Later histories are discarded, not merged
into already emitted objects. Equal values from a name and a pet, for example,
do not acquire a fictional joint origin.

This preserves streaming, deterministic encounter order and the existing cap
and policy semantics. Cap remains greedy per stage/seed; global dedup precedes
policy and still retains rejected values. Streaming does not imply constant
memory: frontiers hold richer objects and global value dedup remains unbounded.

## Profile and CLI compatibility

`build_plan` now populates `base_candidates`, `isolated_candidates`, and
`number_candidates`. Existing string lists/maps remain compatibility snapshots
for old callers, including positional construction of `ProfilePlan`. They are
not live synchronized views: use the candidate lists for causal generation,
and do not edit one representation expecting another to change.

Pass the same structured seeds to Generator and Combine, and structured
number tokens to Affix, to preserve their specific source attribution.
Converting a Candidate back to a string before passing it loses that context.

CLI debug renders origins and transformations directly, including reverse,
both Combine operands, and CLI-only sources. It does not call
`explain_candidate`. The old helper and maps are retained as deprecated,
heuristic compatibility APIs for external string-only consumers and their
existing tests; they are not authoritative provenance. Debug wording therefore
changes deliberately, while candidate values, order and stdout format remain.

Hashcat still consumes the original textual numbers and is unchanged. Its
independent transformation implementation is outside this decision.

## Verification and follow-ups

Tests cover causal propagation, immutability, value projection, first-wins
dedup, debug without heuristics, external mutator compatibility, and serialized
provenance under distinct process hash seeds. Twelve ordered-output digests
captured from pre-change HEAD `6044df7` cover leet modes, cap, Combine, reverse,
policy, duplicate inputs and isolated seeds.

Implemented: structured generation and causal debug. No score, ranking,
dataset integration, API or UI is introduced here; no experimental mode is
added. Future scoring can consume origins and transformations without coupling
core to profile fields. Ranked dedup may make a different explicit choice
about competing derivations.

FOLLOW-UP (not implemented): Block 2 validation, Unicode/date hardening,
global memory limits, and the existing unrelated inaccurate comments.
README is deliberately untouched to preserve the operator's existing edits.

## Gate 1.1 audit

ProfilePlan snapshots are real duplicated state. Replacing its public mutable
dataclass fields with detached properties would break positional/keyword
construction, assignment, in-place list updates and aliasing. A writable proxy
would also need rules for replacing causal origins after textual edits. The
audit deliberately retains this compatibility API rather than silently making
list edits ineffective. New consumers should use structured fields; a future
single-source-of-truth migration needs an explicit public API decision.

Combine has no internal consumers inspecting or editing `all_names`. Its
structured operands are now private `_partners`; `all_names` restores lowercase
textual introspection as a detached list. It is not a writable configuration
view: reconstruct the mutator to change partners. This restores reading, not
the old undocumented ability to mutate/assign that attribute.

Dispatch is explicit: subclass `Mutator` for a legacy `mutate` implementation,
or `StructuredMutator` for `mutate_candidate` only. A direct subclass of
`Mutator` implementing only the structured method remains abstract. When both
methods are overridden, direct calls select the named method; Generator always
uses the structured one. Authors must keep the methods consistent. Neither
base can be instantiated without its required implementation. Exceptions pass
through unchanged; no bidirectional reflective dispatch was introduced.

Model constructors now reject wrong scalar/member types that could otherwise
hide mutable objects inside frozen dataclasses. This validation is limited to
the newly introduced provenance model, not profile or policy hardening.
