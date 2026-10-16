# MIMIC — Block 13: Hashcat Convergence implementation report

Date: 2026-10-15. Base/HEAD: `6350d7c18053dbf3c915ca8cf71f0a3d12bd42ea`.
Branch: `feat/hashcat-convergence`. No commit, push, merge or Block 14 work.

## 1. Baseline and working tree

HEAD equals the required base and is its own ancestor. PR #17 is merged with
head `a423ecf91bd47ef1d4bce90dccd00b930819ebf4`; the three initial untracked
operator lab scripts were hashed and left untouched. No prior tracked changes
needed preservation. Initial status/hashes are in `/tmp/mimic13`.

Before editing: **1,767 passed in 107.97s**. GitHub connector inspection confirmed
[PR #17](https://github.com/sanmirgabriel/mimic/pull/17) merged and its head's
[CI run 38785479075](https://github.com/sanmirgabriel/mimic/actions/runs/38785479075)
completed successfully for Python 3.10/3.11/3.12. No workflow run or combined
status was returned for the merge SHA; main's independent CI success is therefore
**not verified**, not inferred from the PR result. No known CI failure is hidden.

## 2. Previous architecture

Inspected legacy rules/CLI, Generator/Candidate/Seed, domain/application planning,
requests, all five relevant mutators, presets/Intelligence/packs, historical tests,
README, backlog and ADRs. Source precedence, first-cause dedup, per-stage caps,
Policy, ranking and ready bypass remain in the single existing engine.

The legacy `--export-rules` branch executes before application preparation. It
uses CLI numbers/year range, profile/inline date-derived numbers, separators and
Leet choice. It emits no paired bases and does not apply organization variants,
Intelligence's supplementary numbers/services, presets, context/datasets/packs,
Policy, caps, Combine or ranked selection. It never provided a whole-request
translation. Normal generation already composes Case -> Leet -> Affix, with an
independent seed Reverse branch. No old README claim was treated as evidence.

## 3. Demonstrated legacy divergences

Actual Hashcat 6.2.6 --stdout measurements:

- `c` maps `Ab cD` to `Ab cd`; Python title maps it to `Ab Cd`.
- `sa@` maps aaaa to @@@@. MIMIC partial retains original and changes one/two
  positions; four replacements are not that partial operation.
- Legacy full exports each substitution separately; MIMIC full combines all
  eligible positions, including uppercase letters through its lowercase map.
- Case/Leet/Affix on separate rule lines omit composed candidates. Legacy Affix
  lacks the before-word separator form and cannot enforce intermediate caps or
  post-generation Policy. Lower/upper and reversal also differ for Unicode bytes.

Legacy output bytes are intentionally preserved. Only the false universal-parity
claim in its docstring/README was corrected. The new export is explicit and separate.

## 4. Equivalence matrix and evidence

Official semantics: [Hashcat rule reference](https://hashcat.net/wiki/doku.php?id=rule_based_attack),
[opcode/operand definitions](https://github.com/hashcat/hashcat/blob/master/docs/rules.txt).
Current master may differ from 6.2.6; local binary results govern this profile.

| Transformation/constraint | Semantic classification | New bundle behavior and evidence |
| --- | --- | --- |
| Identity | Exact for valid profile bytes | `:` with one-layer autohex bases; real literal $HEX-looking strings tested |
| Lower/upper | Native ASCII can match; Unicode is not universally equivalent | Materialize actual Python results; ASCII/Unicode differential tests |
| Title | `c` is not Python title for compounds | Materialize actual title; spaces, punctuation, digits, apostrophe tested |
| Reverse | ASCII byte reversal can match a seed; Unicode differs | Materialize actual independent reverse; no Leet/Affix replay on it |
| Leet none | Exact no-op | Actual Case frontier inputs plus observed Affix |
| Leet partial | Global `sXY` is unsafe; positional compilation requires separate bounds | Materialize zero/one/two positional results; repeated aaaa and mixed case tested |
| Leet full | Single legacy replacement lines are incomplete | Materialize all actual simultaneous substitutions |
| Affix | Exact after input materialization within profile limits | Compile recorded prefix/suffix/between/after/before via hex-byte `^`/`$`; reconstruct one emitted value before using metadata |
| Combine | Exact only after structural input materialization here | Existing engine materializes two-name structures; pack/Combine differential test |
| Organization names | Exact after existing structural materialization | Compound company/explicit alias/organization-name-v1 tested |
| Ready | Must bypass mutation | Literal identity points; ReadyOnly123 is not invented |
| Policy | No generic safe translation attempted | Use actual accepted outputs; constrained length/digit cases tested |
| Caps | Valid rule alone does not prove survival | Use observed post-frontier outputs; caps 1/2/10/50/256 tested |
| Dedup | Hashcat rules do not carry first cause | Pair only actual unique engine outputs; value multiplicity checked, provenance not transferred |

Only Affix is compiled into new non-identity rules. This is useful partial
compilation of the real execution, not a claim to symbolically express every
mutator. Exact value-set reproduction can include materialized transformations.
No Python Hashcat interpreter is used as external certification.

## 5. Decisions and bundle semantics

[ADR 0013](adr/0013-hashcat-convergence.md) defines `mimic-hashcat-bundle-v1`.
One frozen request is prepared/executed once by GenerationService. Each retained
Candidate becomes a recorded (base, rule) pair. Earlier Python transformations
are materialized in the final Affix input; unmatched/non-compilable metadata is
not trusted to construct a different candidate. Ready/Reverse/bare outputs are
literal identity points. A rule above 31 operations falls back to a counted literal.

A private SQLite spool groups bases with **exactly the same observed rule set**.
Every Cartesian pair within a group already occurred in the accepted reference,
so applying each rule file only to its paired bases cannot silently add Policy-
rejected or cap-truncated combinations. Global rules across all bases would not
have that property. Examples use two or three segments, not one segment per word.

The declared relation is UTF-8 value-set equality for the **retained request
output**. Finite budgets export the actual selected set, while still paying the
existing full accepted-stream scan. Order, rank, score, encounter, first cause,
throughput and effectiveness are explicitly not equivalent properties.

## 6. Filesystem security and publication

Existing parents are traversed through O_NOFOLLOW directory FDs. Missing parents,
symlink components, existing targets (including broken links), and parent-traversal
paths fail. Staging and runtime data use private temporary directories on that
same bound filesystem. Files are 0600; published directory is 0700.

Each artifact is hashed/fsynced; the staging directory is fsynced. Linux renameat2
RENAME_NOREPLACE atomically publishes all files without replacing even a racing
empty directory. There is no unsafe os.rename overwrite fallback. Unsupported
platforms/publication primitives fail in a controlled way. Normal error cleanup
removes staging/spool/runtime files and leaves no partial final bundle.

Tests inject write, fsync, ENOSPC, rename and race failures, and use special shell-
looking path names. All subprocess commands use argument lists, never shell=True.
Atomic visibility does not promise power-loss durability, arbitrary same-user
isolation or new restrictions on historically configured input-source paths.

## 7. CLI and contracts

```bash
mimic generate --organization 'Acme Corp Brasil' --reference-year 2026 \
  --leet none --hashcat-bundle /tmp/acme-hashcat

mimic generate -n 'Synthetic Aa' --no-intelligence --leet partial \
  --year-range 2025:2026 --hashcat-bundle /tmp/synthetic-hashcat --hashcat-verify
```

`--hashcat-bundle` is incompatible with `--output` and `--export-rules`.
`--hashcat-verify` and `--hashcat-allow-partial` require a bundle. Generation normal
and unverified export never launch Hashcat. Verification is explicit --version
plus --stdout, with no hash file, authentication or cracking session.

Exit codes: 0 complete or explicitly permitted partial export; 1 invalid source/
request; 2 argument parsing or I/O/publication failure (argparse uses 2, as before);
3 unsupported export/profile or verification failure. Normal logs show mode,
coverage, exported/retained denominator, segment count and verification status.
Quiet suppresses normal logs; debug adds no new candidate trace. New bundle errors
use fixed messages without private paths/values. Inherited engine truncation/debug
logs may still contain seed values, exactly as normal generation does.

The documented Acme/no-preset/none/default-cap example completed with 19,870
candidates, 427,730 expanded bytes, 10,297 material bytes and two segments. It
remains externally unverified unless the operator requests comparison.

## 8. Supported and rejected scope

Profile: Hashcat 6.2.6 stdout, UTF-8 values of 1–128 bytes, default dictionary
autohex enabled. Python Case/title/Leet/structural/Unicode/Reverse semantics are
materialized; only byte-safe Affix is compiled. No arbitrary input encoding
conversion, optimized-kernel flag, other version or hash-mode limit is certified.

Reject C0/C1 controls, LF/CR/NUL, Unicode line/paragraph separators, invalid Unicode
and values above 128 UTF-8 bytes. Strict export fails on any unsupported selected
value. `--hashcat-allow-partial` records exact omission reasons/counts against
retained denominator. A verified subset is still `partial-request`, not exact
full-request parity. No unsupported transform is silently treated as equivalent.

Default bounds: 1,000,000 accepted candidates evaluated, 1,024 rules per base,
64 segments. Breaches fail without partial publication, even in partial mode.
These exporter bounds do not raise Core caps or bound rejected/raw candidate CPU.
Linux /proc and atomic no-replace publication are required; normal MIMIC remains
independent of this optional platform-specific artifact workflow.

## 9. Material-base and rule syntax

Files are `segment-NNN.bases.txt`, paired `segment-NNN.rule`, plus manifest.json.
Bases are `$HEX[<UTF-8 hex>]`, decoded once by default Hashcat autohex. This avoids
accidental decoding of a literal input that itself looks like $HEX[4142]. Hex is
encoding, not encryption. Do not disable dictionary autohex.

Rules contain `:` or sequences of `^\xHH`/`$\xHH`; prepend bytes are emitted in
reverse order. Special punctuation, space, backslash, dollar, hash and multibyte
separators are operands rather than rule syntax. There are at most 31 operations
per line. Actual local 31-operation rules succeeded; 32 were rejected. The longest
compiled rule text is 155 ASCII bytes before LF. No global substitutions, Case,
Reverse, policy rejection or positional Unicode rules are guessed.

## 10. Provenance and manifest

Manifest records format/MIMIC/Python/Unicode/planning versions, captured year,
resolved public switches, applicable plan counts, ranking choice, source-class
counts, pack digests, request digest, retained-candidate provenance digest,
compiled/materialized/fallback counts, omission counters and per-file SHA-256/
bytes/lines. Private names, passwords, paths and pack labels are not copied
literally. Digests are not anonymization. Files themselves contain sensitive
derived material; complete Origins/Transformations remain a MIMIC model property.

`mode=literal-identity-only` explicitly identifies an all-literal fallback with
its measured byte cost; it is not presented as convergence or compression.
`equivalence.status=not-externally-verified` is the default. Explicit successful
comparison produces exact-set only with complete coverage; otherwise partial-
request. File digests cover data/rule files, not a circular digest of the manifest.
The manifest is neither a signature nor an attestation of an authentic executable.

To check artifact integrity without executing Hashcat, from the bundle directory:

```python
import hashlib, json
from pathlib import Path
root = Path('.')
m = json.loads((root / 'manifest.json').read_text())
assert m['format'] == 'mimic-hashcat-bundle-v1'
for segment in m['segments']:
    for kind in ('bases', 'rules'):
        item = segment[kind]
        assert item['file'] == Path(item['file']).name
        data = (root / item['file']).read_bytes()
        assert len(data) == item['bytes']
        assert hashlib.sha256(data).hexdigest() == item['sha256']
```

This checks consistency against a trusted manifest, not authenticity of untrusted
files. No manifest-supplied shell commands are executed.

## 11. MIMIC versus Hashcat comparison

For each segment, run only its pair:

```bash
hashcat --stdout -r /tmp/acme-hashcat/segment-001.rule \
  /tmp/acme-hashcat/segment-001.bases.txt
```

Repeat for listed segments. Optional verification executes all pairs before
publication and compares missing/extra/duplicate values against a disk-backed
reference from the same MIMIC pass. Backend failures, version mismatch, timeout,
unterminated output and set/multiplicity mismatch fail closed. It does not rerun
a second MIMIC generator or certify results with a Python rule interpreter.

## 12. Divergences and limits found

Legacy c/global substitution/composition mismatches are demonstrated above.
Hashcat's observed identity accepts 256-byte input, skips 257-byte input, and
suppresses an append at 255/256 bytes in the tested path. The new conservative
128-byte output envelope avoids relying on that edge behavior; it is not claimed
to be the general maximum for every Hashcat mode/kernel.

Normal MIMIC/Hashcat encounter order differs; grouping sorts byte values/rules
canonically. New differential fixtures find zero duplicates, but no engine rank/
score/causal explanation is reconstructed from Hashcat output. Changing inputs,
Policy/caps/budget requires a new bundle, not reusing old rules as a universal plan.

## 13. Real Hashcat tests

Local binary: **v6.2.6**, OpenCL/PoCL CPU backend. Restricted sandbox execution
initially could not initialize a backend; the established local tool exception
allows candidate-only stdout execution. Runtime/cache/stdout lock files are kept
inside private temporary directories using XDG/PoCL variables, without changing
HOME. Verification defaults PoCL to two threads unless already configured.

Real fixtures cover ASCII, compound title, repeated Leet none/partial/full,
uppercase eligibility, Unicode dotted-I/ß/João, literal $HEX-looking input,
prefix/suffix/between/after/before separators, special/multibyte bytes, empty and
non-numeric tokens (allowed by the existing engine), long-rule literal fallback,
Reverse, ready/dataset/packs, Combine, organization/alias, Corporate BR, PT-BR,
caps, Policy and selected score/diverse output. Five independent evaluation cases
also compare Counter multiplicities, not merely existence of expected values.

No hashes, third-party passwords, remote services, device cracking benchmarks,
downloaded dictionaries or authentication were used. Missing Hashcat/backends in
other environments cause explicitly labelled external-test skips; they are not
silently called verified. Optional export verification instead fails closed.

## 14. Performance and size

Reproduce the small test-only evaluation:

```bash
venv/bin/python -m tests.block13_evaluation --output /tmp/block13-evaluation
```

One local run per fixture; all have zero missing/extra/duplicate candidates.
Planning/export/write timings are seconds. External times include process/backend
startup; the first process uses a cold private PoCL cache. No GPU speed claim.

| Fixture | Outputs | Segments | Base / rule lines | Expanded bytes | Material bytes | Total bundle bytes |
| --- | ---: | ---: | --- | ---: | ---: | ---: |
| ASCII none | 69 | 2 | 5 / 18 | 893 | 475 | 4,498 |
| ASCII partial | 477 | 2 | 29 / 18 | 6,197 | 1,027 | 5,083 |
| ASCII full | 69 | 2 | 5 / 18 | 893 | 475 | 4,515 |
| Corporate BR + alias, none/cap256 | 15,961 | 3 | 254 / 144 | 283,998 | 11,318 | 15,953 |
| Unicode + Policy | 181 | 2 | 31 / 7 | 2,319 | 837 | 4,871 |

| Fixture | MIMIC prepare | MIMIC generate/write | Export total | Export prepare | Artifact write/fsync | External stdout |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ASCII none | 0.000090 | 0.000468 | 0.004237 | 0.000065 | 0.000218 | 26.275 |
| ASCII partial | 0.001673 | 0.007709 | 0.050748 | 0.000134 | 0.000265 | 1.730 |
| ASCII full | 0.000106 | 0.000492 | 0.004623 | 0.000058 | 0.000224 | 1.727 |
| Corporate BR | 0.001331 | 0.156184 | 0.763736 | 0.001473 | 0.000562 | 2.101 |
| Unicode + Policy | 0.000111 | 0.000953 | 0.007550 | 0.000058 | 0.000230 | 1.308 |

Export includes a real MIMIC generation, freezing, compilation, SQLite pairing/
grouping and publication; write time is not the whole export overhead. Preparation
is measured at service.prepare, not all constructor work. These are observations,
not portable throughput predictions. Total bundle exceeds expanded bytes in three
small cases despite smaller material files. Corporate BR total is about 17.8×
smaller here, but export is slower than simply generating/writing its wordlist.
No blanket compression, acceleration or authentication-effectiveness claim.

SQLite disk usage is O(N) pairs/reference; Python stores one bounded 1,024-rule
signature and at most 64 segment descriptions. Its SQLite cache is configured to
2 MiB; temporary sorts use disk. This does not bound existing Core dedup O(N),
frontier/source memory or individual metadata size. The full expanded wordlist
is not held in Python merely to build production bundles.

## 15. Determinism

Bundle file bytes and manifest digests agree with PYTHONHASHSEED **1/42/777**.
Additional six-scenario snapshots cover none/partial/full, score-v1/diverse-v1,
Corporate BR, explicit aliases, captured year 2026 and cap50. Runtime versions
are recorded; equality across different Unicode/interpreter versions is not
claimed. Timings/temp paths are excluded from manifests. Verification fields are
counts/version, not volatile timing or device identifiers.

## 16. Historical compatibility

Fresh exact-base archive versus final code: **24** application scenarios agree in
request/summary/warnings, full result digest, values/order, Origins/Transformations,
score/components, rank/encounter and evaluated/emitted counts. Covers organization
variants on/off, none/partial/full, profile/date/Combine, contextual explicit years,
ready/dataset/PT-BR, Seed/Ready packs, services, budgets and Corporate BR/diverse.
ACME+WordPress remains 159,175 evaluated / Quick 100.

**12** actual CLI modern/legacy × wordlist/legacy-rule-export × Leet-mode cases
match stdout, debug stderr and legacy rule bytes (output-path labels normalized).
**Four** real historical Job configurations agree in snapshot, preview, counts,
output digest and restart behavior, including Corporate BR/diverse. These are
representative equivalence checks, not a universal proof for arbitrary inputs.

## 17. Jobs, API and Web

New export is CLI plus a small local Python artifact function only. No visual
interface, routes, request fields, persisted snapshots, job downloads or SQLite
schema are changed. Existing Web/API/i18n/theme/security tests remain in the full
suite; no new Firefox matrix was required because no Web file changed. Installed
smoke checks exercise existing Web preview, static JS, API, Jobs and restart.
CLI-only delivery avoids a new persistent artifact/job workflow in this block.

## 18. Tests

Final prescribed suite: **1,870 passed in 264.10s**, including all **1,767** baseline
nodes and **103** new cases, with local Hashcat backend available. No existing
assertion weakened or test removed. New regressions cover actual stdout parity,
rule syntax/operand escaping/31-operation ceiling, literal fallback, invalid
Unicode/control/byte limits, Policy/caps, grouping, ready/Combine/packs, ranked
scope, strict/partial labels, corruption/mismatch detection, filesystem failures,
permissions, race publication, shell-looking paths, CLI/error privacy, unsupported
versions/platforms, no implicit subprocess and hash-seed bytes.

Hashcat-dependent tests are optional when absent/unusable and explicitly record
external parity NOT VERIFIED; normal MIMIC has no Hashcat dependency. The local
run had no such skips. Legacy suite, new tests and artifact checks use synthetic
inputs only. Exact command and JUnit/slowest timings are retained under /tmp.

## 19. Wheel/sdist and installed checks

Offline wheel/sdist builds use the existing dependencies; no dependency/version/
CI/schema changes. New bundle.py is a normal package module. Production resources
are checked byte-for-byte against distributions and an external venv. Installed
entrypoint exports/verifies a real bundle in stdout mode; Web/API/Jobs/downloads
and restart pass outside checkout. pip check passes; dependencies are copied from
the existing local environment without downloads. sdist installation also runs
without build isolation/network.

New production/test Python parses under 3.10 grammar. Local runtime is Python
3.13.5; new-feature execution on 3.10/3.11/3.12 remains for its subsequent PR CI.
The verified earlier PR #17 CI does not certify this uncommitted code. Benchmark
helpers/raw material and operator scripts do not enter runtime resources; raw
spools, wordlists, Hashcat outputs and timing files remain under /tmp/mimic13.
Inherited setuptools license-table deprecation is unchanged.

## 20. Changed files

New production module: mimic/rules/bundle.py. CLI adds opt-in artifact flags and
error translation. Legacy rules module changes documentation only. Added
tests/test_hashcat_bundle.py and tests/block13_evaluation.py, this report and
[ADR 0013](adr/0013-hashcat-convergence.md). README Hashcat section is corrected;
BACKLOG records PR #17 merge/base and current Block 13. Core, all mutators,
requests/planning, score-v1, diverse-v1, presets, catalogs, Web/API/Jobs, schema,
versions, dependencies and CI pipeline are unchanged.

## 21. Remaining risks

This is observed-output Affix compilation, not a universal symbolic Hashcat
pipeline. It materializes Case/Leet/structures and can devolve into labelled
literal export. Segmentation can hit explicit bounds; unsupported data requires
strict failure or clearly partial output. It pays full MIMIC work plus disk I/O.
Large contexts, inherited dedup/frontiers and input metadata can still cost memory/
CPU. Atomic publication is Linux-specific, not power-loss durability. Other
Hashcat versions/kernels/flags need independent proof; hashes/authentication are
outside this feature. Local binary identity is not cryptographically attested.

Files contain sensitive derived data despite autohex and digests. Existing causal
logs/snapshots retain their existing privacy limitations. No automatic cleanup of
published bundles or authenticated provenance is claimed.

## 22. Final branch and evidence

Required branch/HEAD remain unchanged; all intended files are unstaged. Three
operator scripts retain initial SHA-256 and were not executed or added to staging.
Blocks 14–21 scopes remain intact. No commit, push, merge or Block 14 implementation.

Evidence under `/tmp/mimic13`: initial hashes/status, baseline/final JUnit/logs,
raw Hashcat syntax/length/operation probes, independent reference/bundle stdout
comparisons and size/timing results, six-scenario hash snapshots, exact-base
application/CLI/Job comparisons, distribution and external-install smoke logs.
Raw synthetic evidence is outside production resources. Reusable tests/evaluation
code and these quantitative tables remain in the repository.

## 23. Technical decision

The first contract is useful and falsifiable: real Hashcat reproduces declared
frozen sets, unintended combinations are prevented by observed grouping, and
unsupported/partial/unverified/literal results are explicit. Size benefit is
measured for some affix-heavy cases; general performance improvement is not
claimed. Normal behavior and legacy rule bytes are preserved. Ready for Gate 13
review of the compiler, publication boundary, manifest contract and evidence.

**READY FOR GATE 13**

## Gate 13 follow-up (2026-10-15–16)

The initial implementation measurements above describe the pre-audit state.
Gate 13 reproduced all five output/byte tables, then demonstrated two verifier
defects: empty exports could say passed after only --version, and unexpected
child output was captured/read without byte bounds. Empty verification now
fails; bounded stdout/stderr pipes enforce deadlines, kill/reap on failure and
limit parsed lines. No generation, compilation/grouping or manifest format
semantics changed. A third correction rejects empty CLI bundle destinations
instead of falling through to normal wordlist output. See [Gate 13 audit](GATE13_AUDIT.md) for failing-before evidence,
final test counts, corrected runtime limits and release decision.

Gate 13 completed on 2026-10-16: **1,954 passed in 364.84s**, preserving the
1,870 initial nodes and adding 84 adversarial cases. Local decision:
**READY FOR COMMIT**. No commit, push, merge or Block 14 work occurred.
