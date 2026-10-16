# ADR 0013 — Observed-output Hashcat bundles

Date: 2026-10-15. Status: implemented; Gate 13 completed locally on 2026-10-16, ready for operator commit review.

## Problem and evidence

The historical exporter emits separate case, reverse, global replacement and
numeric-affix rule lines. Independent lines do not implement staged composition.
Hashcat `c` produces `Ab cd` from `Ab cD`; Python title produces `Ab Cd`.
Hashcat `sa@` replaces all four occurrences in aaaa, whereas MIMIC partial selects
zero, one or two positions. Full Leet combines replacements; legacy full exports
six separate rules. Supplementary Intelligence, structural organization seeds,
ready bypass, Policy, caps, global dedup and ranked selection are not translated
by the legacy rule writer. Keep its historical bytes; remove the false universal
parity claim from its documentation.

Official references: [rule semantics](https://hashcat.net/wiki/doku.php?id=rule_based_attack)
and [rule opcodes/operands](https://github.com/hashcat/hashcat/blob/master/docs/rules.txt).
The installed 6.2.6 binary, rather than current master alone, validates this profile.

## Decision

Add CLI-only `--hashcat-bundle NEW_DIRECTORY` with optional explicit
`--hashcat-verify` and `--hashcat-allow-partial`. No request/snapshot/database/Web/API
schema changes; no implicit external process on normal generation or export.

Freeze the request, use the existing GenerationService once, and stream actual
retained GenerationResults. Policy, intermediate frontiers, first-cause dedup,
Intelligence, presets, packs and ranking remain owned by the existing engine.
The exporter translates one actual final Affix into prepend/append UTF-8 bytes
only if its recorded input/operands reconstruct that exact output. Earlier Python
transformations are materialized in that input. Reverse and ready candidates are
literal identity points, without sending them through unrelated mutation rules.
A non-compilable Affix can also be an explicitly counted literal fallback.

Disk-backed SQLite stores (base, rule) pairs and the expected UTF-8 value set.
Bases with exactly identical observed rule sets share a segment. Every Cartesian
pair in such a segment therefore corresponds to a real accepted output; grouping
cannot invent the other combinations a global rule file would produce. Canonical
byte/rule/group ordering yields deterministic files, without preserving engine
encounter/output order. Exported bases use one-layer Hashcat autohex encoding to
preserve literal $HEX-looking strings and multibyte text.

This is partial compilation of actual execution, not a second mutation generator
or a generic symbolic compiler. It pays the MIMIC generation cost before writing
compact material. Pure all-literal output is `literal-identity-only`, explicitly
not advertised as useful convergence/compression. Even genuine Affix compilation
may produce a larger total bundle once manifest overhead is counted.

## Contract and constraints

Format: `mimic-hashcat-bundle-v1`. Linux, /proc FD anchoring and renameat2
RENAME_NOREPLACE are required for safe initial publication. No unsafe fallback.
Each segment's rules apply only to its own bases; no crossing or stacking.

Profile: local Hashcat 6.2.6 --stdout, UTF-8 values 1–128 bytes, default dictionary
autohex enabled. Reject C0/C1, Unicode line/paragraph separators and invalid Unicode.
New native rules are only identity, prepend and append, with hex byte operands and
at most 31 operations. The lower 128-byte envelope avoids Hashcat's observed
255-byte append suppression/256-byte identity boundary. Other kernels/encodings/
versions are not certified. Optional verification rejects versions outside 6.2.6.

Strict export fails if any selected value is unrepresentable. Partial mode omits
only those values and records exact counts/reasons against retained denominator.
Verified partial output remains partial for the request; it is never labelled
exact full-request parity. Default limits are 1,000,000 policy-accepted candidates
scanned, 1,024 rules per base, 64 segments. Exceeding them fails without publishing.
These are exporter bounds, not increases to Core caps or whole-request CPU/memory
bounds. Ranked export still scans the accepted stream until selection completes.

Manifest records resolved public options, plan counts/versions, captured year,
source-class counts, pack digests, a full request digest and retained provenance
digest, materialization, omissions, file digests/counts/sizes and compatibility.
Private names, paths, passwords, organization/pack labels are not copied literally
into it. Base/rule data is sensitive; digests/autohex do not anonymize or encrypt.
Full per-candidate provenance remains in the MIMIC model, not in .rule files.

Equivalence means the UTF-8 value set of this frozen retained execution. It does
not mean order, rank, score, encounter index, causal metadata, performance or
authentication effectiveness. Untested exports say not-externally-verified.
Explicit verification runs Hashcat --version and each paired --stdout invocation,
then compares missing, extra and duplicate values against a disk-backed reference.
Failures, unavailable backends and mismatches fail closed before publication.
Runtime stdout locks/cache files stay in private temporary directories; no hashes
or cracking sessions are started. PoCL verification defaults to two worker threads
unless the operator already configured its limit.

Gate 13 correction: empty exports cannot be externally verified; explicit verify
fails before publication rather than labelling a version-only call as passed.
Drain stdout/stderr through bounded pipes under the process deadline. Version
stdout is at most 32 bytes, each segment stdout at most its expected output count
times 129 bytes, stderr at most 64 KiB per process. Kill/reap on failure or
interruption. Read result lines with the same 128-byte value ceiling. This bounds
the verifier's own captures, not every backend cache or whole-request disk use.
Empty CLI bundle destinations are rejected before generation; they never select
the normal wordlist flow implicitly.

## Publication and complexity

Open the existing destination parent through O_NOFOLLOW directory descriptors,
reject pre-existing files/directories/symlinks, and stage privately on the same
filesystem. Files are 0600, directories 0700. Hash/fsync each file, fsync the stage,
and publish via anchored renameat2 RENAME_NOREPLACE, including a racing empty
existing directory. Normal exceptions, write/full-disk/fsync/verification/rename
failures leave no final partial bundle; private work is removed. This is atomic
visibility, not a promise of power-loss durability or immunity to arbitrary
same-user interference. Normal input paths keep existing source-reading semantics.

SQLite spool is disk O(N); auxiliary Python grouping memory is bounded by one
1,024-rule signature and at most 64 manifest segments plus a candidate/its metadata.
The SQLite cache is configured at 2 MiB and temporary sorts use disk. Core retains
its existing O(N) dedup and frontier/source costs. No whole wordlist is held in
Python merely to export; there is no claim of globally bounded engine memory.

## Alternatives and follow-up

A generic case/Leet/cartesian exporter is smaller but wrong under Unicode, title,
Policy or frontier truncation. A single all-expanded identity export has no useful
compilation and must be labelled literal. A new symbolic mutation engine would
risk semantic drift and violate the single-engine architecture. Arbitrary fixed
subsets/cap increases would hide missing coverage. Observed pairing is a small
first useful contract with measured size benefits for some numeric expansions.

Future native Case/positional Leet compilation requires separate differential
proof, without modifying existing mutators. No such expansion or Block 14 work
is included. See the [implementation report](../BLOCK13_IMPLEMENTATION_REPORT.md)
for actual counts, time, size, tests, old-byte comparisons and remaining limits.
