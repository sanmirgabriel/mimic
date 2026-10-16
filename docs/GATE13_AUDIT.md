# MIMIC — Gate 13: Hashcat Convergence audit

Started: 2026-10-15. Completed: 2026-10-16. Branch: `feat/hashcat-convergence`.
Base/HEAD: `6350d7c18053dbf3c915ca8cf71f0a3d12bd42ea`.
No commit, push, merge or Block 14 work.

## 1. Baseline, branch and working tree

Verified exact HEAD/branch, ancestry and unstaged tree before corrections. Four
tracked implementation files were modified; five intended implementation files
and the three operator lab scripts were untracked. All 192 initial repository
files were copied/hashed under `/tmp/mimic13gate/initial`; initial status/diff and
hashes remain there. Operator scripts were not executed, edited or staged.

Initial suite: **1,870 passed in 302.90s**, no failures/errors/skips, including the
1,767 historical nodes and 103 implementation cases. The Gate request records
PR #17 and post-merge main CI as approved on 2026-10-15; this is not certification
of the uncommitted Block 13. The earlier report's main-CI uncertainty described
its earlier inspection, not a new CI failure.

## 2. Architecture review

Read bundle/legacy rules/CLI, application requests/generation, domain planning,
Generator/Candidate/Seed/provenance, all five mutators, sources/packs, Intelligence/
presets and both ranking selectors; reviewed tests, benchmark, ADR and report.

The exporter round-trips a detached request, prepares GenerationService once,
uses its resolved request/summary and consumes iter_results once. A spy regression
confirms one prepare and one stream claim. No second candidate engine or hidden
export recomputation exists. Ranking still scans the accepted universe; exports
contain the retained result set. Pack digest verification may read/rewind a file
before existing engine consumption, as required by the unchanged pack contract.

## 3. Legacy exporter divergences

Confirmed independent rule lines do not represent staged Case/Leet/Affix,
independent Reverse, Policy, caps, Intelligence or ranked selection. Hashcat `c`
and Python title differ for compound words; global `sa@` is not partial positional
Leet. Full Leet combines eligible replacements, unlike independent legacy lines.
Legacy function AST excluding docstrings and all tested rule bytes remain equal
to the exact base. These historic limitations were documented, not repaired by
changing mutators or the legacy output contract.

## 4. Exact equivalence contract

Relation: UTF-8 value-set equality with the **retained request output**, limited
to the declared profile. Strict complete verification can say exact-set. Explicit
partial verification says partial-request. Unverified files retain the external
not-externally-verified status even when an independent audit compared them.
Order, rank, score, encounter, first cause, throughput and authentication success
are not equivalent properties. No automatic cracking/authentication is involved.

## 5. Transformation differential matrix

| Case | Audit evidence / behavior |
| --- | --- |
| Identity, lower, upper, compound title | Real engine reference versus actual stdout; all earlier Python case results materialized |
| Repeated Leet none/partial/full | aaaa, assista, mixed-case words; one/two substitutions preserved, simultaneous full replacements materialized |
| Independent Reverse | Existing tests plus palindromic aba; no reversal of post-Affix output |
| Prefix/suffix; before/between/after separators | Multichar xy/2026 and `$`, `#`, backslash, caret, space, accented and emoji bytes |
| Combine, organization/alias, PT-BR | Existing pack/Combine differential plus four new Corporate BR Quick/Focused score/diverse cases |
| Ready/Seed Packs | Actual registry/digest-pinned inputs in preserved implementation tests; ready bypass remains literal |
| Unicode | João and decomposed João, Straße, dotted-I, emoji, combining marks; no normalization or native byte-case inference |
| Policy / caps / dedup | Original cap 1/2/10/50/256 differential retained; new first-cause duplicate and grouping-boundary checks |
| Quick / Focused / diverse | Independent retained references at K=100/1,000; full evaluated counts agree and exceed K |

No native case, `c`, reverse or global substitution rule was introduced. Every
new non-identity rule is an observed byte-safe Affix. Materialization is explicit.

## 6. Hashcat syntax and escaping

Real 6.2.6 accepts 30 and 31 operations and rejects 32. Multibyte operands count
bytes/operations, not Python characters or ASCII rule text; a 31-op hex rule is
155 text bytes. UTF-8 prepend bytes are reversed in rule order so the final prefix
has the correct byte order. Reserved punctuation is an operand via hex escaping.
Above-limit Affix outputs remain counted literal fallbacks. Empty/blank rule
files fail; `?` is rejected with a warning on **stdout** and exit 255. Consequently
nonzero exit codes must be checked before interpreting stdout as candidate data.
The exporter only emits the supported `:`, prepend and append grammar.

## 7. Unicode, autohex and byte limits

Actual autohex tests cover one-layer decoding, literal nested $HEX-looking text,
ASCII lengths 1/127/128, 64 é and 32 emoji (128 bytes), normalized/decomposed accents
and mixed multibyte input. Reject 0/129 bytes, 65 é/33 emoji, NUL/CR/LF/C0/C1,
Unicode line/paragraph separators and invalid surrogates. Codepoint count is not
the byte budget. Tests cover 127-byte base + one byte (supported final 128), and
128-byte base + one byte (129-byte outputs strictly rejected or counted omitted).
Both final values and compiled bases are checked. No other Hashcat kernel,
version, encoding conversion or optimized mode is inferred compatible.

## 8. Pair grouping correctness

The SQLite primary key is (base, rule). The exporter unifies all observed rules
for the same base, serializes that sorted set and only shares a segment across
bases whose entire rule sets agree. Near-identical signatures remain separate.
A new fixture first emits ready values that remove different later mutable
Affix outputs by real global dedup: exactly 64 signatures publish, 65 fail.
A second real-engine fixture reaches exactly 1,024 rules for one base; 1,025 fail.
Late-discovered groups and either bound remain failures even with partial enabled.
No invented engine stream or Python rule interpreter supplies these boundary cases.

## 9. No-extra/no-missing proof

For a retained value v, compile_pair either emits identity(v) or checks a final
Affix reconstruction against v before compiling literal byte operations. Hence
its pair produces exactly v in the supported parser profile. All pairs associated
with base b form R(b). A segment only groups equal R(b), so its Cartesian product
contains precisely observed pairs. Global engine value dedup makes the resulting
value mapping injective; two emitted pairs cannot stand for two different retained
values while producing the same value.

This reasoning is checked externally: independent references come from separate
GenerationService executions with the same frozen request, not exporter SQLite.
Each segment stdout is checked against that accepted reference separately, its
line count equals declared outputs, and the union Counter equals the reference
Counter with multiplicity one. Duplicates cannot be excused by presence in another
segment. Five reproduced benchmark fixtures also compare independent Counters;
all missing/extra/duplicate counts are **0**. Order is deliberately not asserted.

## 10. Strict versus partial exports

Strict unsupported selected values fail without publication. Partial permits only
recorded value-profile omissions, not scan/rules/group bounds. Denominators include
all retained candidates, including omitted ones. File counts, materialization sums,
omissions and expanded/material byte totals are checked independently.

A real verified ready fixture retained two values, exported Good and omitted one
129-byte value: coverage partial, status partial-request, exported 1/2, omission
count 1. An all-omitted export may publish an empty, explicitly partial/unverified
manifest. **Explicit verification of zero exported values now fails**, including
Policy-empty complete outputs; no external passed label can come from --version
alone. This is correction G13-01 below.

## 11. Literal fallback correctness

Identity-only bundles advertise literal-identity-only and measured byte cost.
Reverse, ready and non-compilable metadata are materialized. Compiled/literal
mixtures reproduce real outputs; forged Affix metadata cannot substitute another
value. Long operands fall back rather than generate unsupported rule lines.
Identity-only output is not described as useful rule compression.

## 12. Manifest schema and hashes

Independently recomputed data/rule SHA-256, byte/line counts, segment product
counts, exported/retained/omitted totals, material counts and provenance digest.
Format remains mimic-hashcat-bundle-v1; runtime/Python/Unicode, resolved planning
versions/year/sources/pack digests, ranking selector, limits and verification scope
are recorded. Deterministic request/provenance digests use the actual resolved
request/retained metadata; no timing/path is added to the manifest.

An audit-side integrity consumer detects deliberately modified base/rule files,
missing files, undeclared extra entries, duplicate segments, wrong counts and
wrong format. This is validation of trusted emitted metadata, **not** a new
production untrusted-manifest import feature. The application has no such reader;
it does not execute manifest-supplied commands. SHA-256 is consistency evidence,
not a signature, authenticated provenance or protection against deliberate
replacement of both data and manifest.

## 13. Provenance/privacy guarantees

Complete Origins/Transformations remain MIMIC data, with an ordered retained
provenance digest in the manifest. Fixed source/step counters avoid copying private
source paths/opaque labels. Tests exclude organization/alias/pack names and paths
from manifests and recompute causal digests from independent references. Digests
are not anonymization. Autohex data still contains sensitive derived material.
Inherited candidate/debug/truncation logs keep their historical privacy contract;
new bundle errors use fixed diagnostics without adding private literals/paths.

## 14. Filesystem boundary

Existing absolute parents are traversed via O_NOFOLLOW directory FDs. Reject ..,
missing/file/symlink components, existing directories/files, broken links and
hardlinked destinations. Existing hardlink contents remain unchanged. Publication
uses the bound parent FD and Linux renameat2 RENAME_NOREPLACE, without overwrite
fallback. A parent rename followed by symlink substitution does not redirect
publication or touch the substitute directory. On this SQLite/runtime, its
canonical journal path instead raises controlled disk I/O error; cleanup succeeds
and no final bundle appears. Successful continuation after parent rename is not
promised. Input-source reading remains the existing authorized request behavior.

## 15. Atomic publication and cleanup

Staging is private on the bound filesystem. Data/rule/manifest files are 0600;
published directory is 0700. File fsync and directory fsync precede the atomic
rename. Two concurrent exporters produce exactly one complete final directory;
the losing attempt cannot replace it. Existing racing-empty-directory test remains.

Recoverable pre-publication faults cover write/ENOSPC/EACCES/fsync/rename and spool
connect/statement/close, verification failures and mid-segment failure. Destinations
remain absent or pre-existing/intact; private work disappears. Repeated injected
SQLite faults leave the /proc FD count unchanged. This is atomic visibility, not
power-loss durability, arbitrary same-user isolation, or guaranteed cleanup after
SIGKILL/filesystem damage. The atomic rename is the publication commit point.

## 16. Verification subprocess safety

Only explicit verify launches a program; normal/export-without-verify regressions
forbid both run and Popen. Arguments are lists, stdin is DEVNULL, and only version
and paired --stdout are invoked. No hashes, remote devices, accounts or auth.
Local Hashcat 6.2.6 is checked; the binary is trusted locally, not attested.

G13-02 replaces unbounded run/capture/files with a small pipe-draining helper:
32-byte version stdout; per-segment stdout <= expected outputs ×129 bytes;
stderr <=64 KiB per child; 10s version /60s segment deadlines. Oversized chunks
are rejected before writing. Reading reference-comparison lines is bounded at
130 bytes, and per-segment parsed counts cannot exceed expected outputs. Extra,
missing, duplicate, malformed or unterminated lines fail closed before publication.

Timeout, nonzero, absent executable/backend, execution permission failure,
interruption and mid-segment failure are exercised. Finally blocks kill/reap a
live child; timeout/interruption tests confirm it no longer exists. XDG/PoCL
paths remain private temporary directories; parent os.environ is unchanged.
Backend caches/compiler memory and inherited engine work have separate costs.

## 17. Real Hashcat differential fixtures

Binary: /usr/bin/hashcat **v6.2.6**, PoCL OpenCL CPU, normally two PoCL threads.
Sandbox restrictions require the established local exception for OpenCL/TestClient;
no product setting was relaxed. The audit reruns the original actual stdout tests
and adds repeated/mixed text, combining marks/emoji, multibyte op boundaries,
retained budgets, literal/partial and parser rejection cases. Fault-injection
executables are separately labelled synthetic diagnostics, not parity evidence.
No third-party passwords, hashes, corpora, downloads or online services were used.

## 18. Input and output limits

Defaults remain accepted scan 1,000,000, rules/base 1,024, segments 64 and value
1–128 UTF-8 bytes. Exact accepted-scan boundary succeeds, one fewer fails, with
partial both false/true. New byte/deadline captures prevent unexpected stdout or
stderr from filling an unconstrained capture file. Total backend cache size,
source metadata, raw rejected candidate CPU and whole-request disk/RSS are not
universally bounded by these limits. Segmentation can fail for legitimate inputs.

## 19. Determinism

Nine complete file/digest snapshots agree byte-for-byte under PYTHONHASHSEED
**1,42,777**: none/partial/full × score/diverse, plus partial omissions, all-omitted
and literal-only cases. All manifest bytes, counters, provenance/request hashes,
coverage labels and segment files are included; no differences were filtered.
Captured corporate year is 2026. Timing/device identifiers are outside manifest;
different Python/Unicode runtime versions are not claimed byte-identical.

## 20. Performance/CPU/memory/disk

Five independent fixture reproductions (single local observations):

| Fixture | Outputs | Segments | Base/rule lines | Expanded bytes | Material bytes | Total bundle bytes |
| --- | ---: | ---: | --- | ---: | ---: | ---: |
| ascii-none | 69 | 2 | 5 / 18 | 893 | 475 | 4,498 |
| ascii-partial | 477 | 2 | 29 / 18 | 6,197 | 1,027 | 5,083 |
| ascii-full | 69 | 2 | 5 / 18 | 893 | 475 | 4,515 |
| corporate-br | 15,961 | 3 | 254 / 144 | 283,998 | 11,318 | 15,953 |
| unicode-policy | 181 | 2 | 31 / 7 | 2,319 | 837 | 4,871 |

Every value/byte count equals the implementation report. Three small total
bundles exceed expanded wordlists; Corporate BR is about 17.8× smaller here. This
is not evidence of general compression, GPU speed or authentication effectiveness.

| Fixture | MIMIC prepare | Generate/write | Export total | Export prepare | Write/fsync | External stdout |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ascii-none | 0.000088 | 0.000462 | 0.003938 | 0.000061 | 0.000187 | 30.938 |
| ascii-partial | 0.001609 | 0.008020 | 0.136211 | 0.000177 | 0.000725 | 1.627 |
| ascii-full | 0.000217 | 0.001061 | 0.009978 | 0.000082 | 0.000400 | 2.412 |
| corporate-br | 0.001303 | 0.106527 | 0.957709 | 0.000444 | 0.000614 | 2.322 |
| unicode-policy | 0.000135 | 0.001584 | 0.007985 | 0.000102 | 0.000293 | 1.584 |

Seconds; external includes startup and first private cold PoCL compilation.
Scheduling/background validation vary; these are not controlled throughput or
before/after timing comparisons. Export includes another actual MIMIC execution
for this independent comparison; production export itself executes once.

A separate instrumented fresh-process export sample separates compilation,
grouping, SQLite statement work and file writes, sampling temporary sizes:

| Fixture | Export wall/CPU s | Compile s | Group s | SQLite execute s | Process peak KiB | Spool / temporary observed peak bytes |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| ascii-none | 0.008407 / 0.008442 | 0.000748 | 0.000214 | 0.001411 | 30,448 | 57,888 / 57,888 |
| ascii-partial | 0.042575 / 0.043126 | 0.005074 | 0.000829 | 0.005109 | 30,188 | 139,264 / 144,347 |
| ascii-full | 0.011466 / 0.011722 | 0.000817 | 0.000245 | 0.001620 | 29,676 | 82,508 / 87,023 |
| corporate-br | 1.410622 / 1.461477 | 0.213541 | 0.017360 | 0.197255 | 34,288 | 3,768,320 / 3,784,273 |
| unicode-policy | 0.016934 / 0.017318 | 0.001817 | 0.000606 | 0.002295 | 29,808 | 73,728 / 78,599 |

Instrumentation adds trace/sampling overhead. SQLite execute time includes API
calls, not all cursor stepping; grouping includes overlapping database work and
these columns must not be added as independent phases. Observed logical disk
peaks include journals/staging, sampled every 5ms and at close; not allocator,
physical-block or universal filesystem quotas. Schema/queries use primary keys
and bases(signature,base) index for ordered grouping; no reproduced significant
query bottleneck warranted changing the compiler/spool.

Integrated explicit Corporate BR verification also passed with 15,961 outputs
and zero missing/extra/duplicates. A second fresh run measured 24.508s total,
23.748s inside verification, 3.017s parent CPU and 36,812,077 bytes observed
private temporary peak, including cold backend/compiler caches. /proc VmHWM was
34,268 KiB (startup VmRSS 29,060; final 33,612 KiB). Child-family getrusage peak
was 718,636 KiB, including possible PoCL compiler children, not an aggregate
or a GPU measurement. Parent getrusage reported 311,372 KiB even **before**
generation, inherited from the launcher; it is not attributed to MIMIC allocation.
An earlier run was 33.416s and 37,963,689 temporary bytes. These cache/startup
costs explain why compact output does not imply a cheap external application.

The same synthetic executable emitted an unterminated 8 MiB diagnostic. Parent
tracemalloc peak: **17,066,798 bytes before ->115,332 after**; after fails immediately
with hashcat-output-limit-exceeded and reaps the child. Both leave no final/temp
bundle. This measures Python allocations, not total process/backend memory.
Core dedup remains O(N); SQLite is disk O(N), cache configured 2 MiB. Production
export never collects the whole wordlist in a Python list. Tests may retain small
independent references solely as an audit oracle.

## 21. CLI/error behavior

Preserved opt-in --hashcat-bundle, --hashcat-verify, --hashcat-allow-partial and
incompatibility with --output/legacy --export-rules. Quiet suppresses normal
logs; fixed diagnostics do not echo new private input. Normal logs report mode,
coverage, exported/retained, segments and verification; debug adds no new trace.

G13-03: empty --hashcat-bundle and --hashcat-bundle= previously returned 0 and
printed Q/q as a normal wordlist. They now fail argparse validation (2) before
preparation/output. A deliberately invalid UTF-8 source returns fixed input
error 1. I/O/publication failures return 2; incompatible values or unsuccessful
verification return 3. Explicit permitted partial returns 0. OS-level execution
permission errors retain the I/O classification. No new bundle behavior is
implicitly enabled in historical generation.

## 22. Historical regression

Fresh required-base archive versus final application: **24** full scenarios agree
in request JSON, summary/warnings, output bytes/order/digest, candidate metadata,
score/components/rank/encounter and counts. Includes Corporate BR/diverse, PT-BR,
services, profile/Combine/dates, packs and organization variants. **12** actual
modern/legacy CLI wordlist/legacy-rule/Leet cases agree including debug stderr
(output path labels normalized only). **Four** historical Jobs agree in snapshot,
preview/counts/digests and restart/download behavior. Additional post-G13-03 CLI
comparison is included before release. These representative checks are not a
universal mathematical proof for arbitrary historical input.

## 23. Wheel/sdist/external installation

Offline builds and fresh external venv use existing local dependencies only.
All **103 production/resource files** agree byte-for-byte with checkout, wheel,
sdist and external installation. Bundle module/installed entrypoint work outside
checkout; real verification, manifest digests/permissions, existing Web preview,
static JS, API, Jobs/download and restart pass for both distributions. pip check
passes. Operator labs/benchmark helpers do not enter distributions/runtime
resources. Tests included in sdist are test source, not production modules.
Final artifact checks are repeated after the last CLI correction.

## 24. Python supported-runtime readiness

Production and three Block 13 test/helper modules (78 Python files) parse using
Python 3.10 grammar. Local execution: 3.13.5. Versions/dependencies/schema/CI matrix
3.10/3.11/3.12 remain unchanged. This uncommitted feature has not run on those
three interpreters locally or on a new PR CI; no such execution is claimed.
No Web interface changed; existing Web/i18n/theme/security tests are retained.
Inherited setuptools license-table deprecation remains.

## 25. Demonstrated defects

| ID | Severity | Failing-before evidence | Cause |
| --- | --- | --- | --- |
| G13-01 | Medium | Policy-empty complete and all-omitted partial exports reported external passed with only --version, no --stdout | Empty segment loop skipped actual candidate execution |
| G13-02 | Medium | 8 MiB stdout/stderr/version fixtures were captured without byte limits; 8 MiB line caused ~17 MB Python allocation | run/capture plus unbounded files/readline before mismatch detection |
| G13-03 | Medium | Two empty-directory CLI spellings returned 0 and printed a normal wordlist | Truthiness confused present empty argument with absent opt-in |

Five new failing-before verifier regressions plus two CLI regressions reproduce
these in the initial implementation. No known high/critical defect remains in
the tested contract. Different native Hashcat/Python semantics were already
materialized honestly and were not reclassified as new defects.

## 26. Minimal corrections

Only new bundle verification plumbing and a two-line CLI argument guard changed
production behavior during Gate. Grouping/compiler/data layout, manifest format,
Core, mutators, score/diverse/preset, sources, requests, Jobs/API/Web and schema
were not modified. Existing mocked-verification tests stub the new bounded runner
instead of run, retaining all assertions; no-implicit-execution also forbids Popen.
README/ADR/report document empty verification/output limits; backlog records Gate.

## 27. Regression tests

Added tests/test_gate13_hashcat.py: **84** cases. Original 103 implementation nodes
and all 1,767 baseline nodes remain. Focused corrections pass, including real
Hashcat matrices and follow-up cases; two initial audit fixture assumptions were
corrected after observation: SQLite need not successfully survive parent rename,
and Hashcat parser rejection diagnostics can use stdout. Safety assertions were
kept; no historical assertion was weakened.

Final prescribed suite: **1,954 passed in 364.84s**, zero failures/errors/skips.
JUnit comparison retains every one of the 1,870 initial nodes, including all
1,767 historical nodes; 84 Gate cases are added. The completed resumed run is
`final-resumed-tests.txt` / `final-resumed.xml` under the evidence directory.
An interrupted final attempt was incomplete and is not counted as a passing run.
The earlier 1,952-case completed run preceded the two CLI-destination regressions.

## 28. Remaining limitations

Observed-output compilation pays real MIMIC generation and disk spool cost; it
is not a universal symbolic translator or a replacement generator. Finite-budget
exports preserve selected values, not order/metadata. Native rules remain Affix
only. Literal-only/partial/unverified modes are explicit; no empty verified label.
Linux /proc/renameat2, autohex and exactly Hashcat 6.2.6 are the validated profile.
Future kernels/versions/encodings need proof. Per-process pipe bounds do not cap
PoCL caches/compiler allocations or Core O(N) dedup/input metadata. Published
material is sensitive; no automatic published-artifact cleanup, trusted binary
attestation, signature, arbitrary same-user isolation or power-loss guarantee.
Broader throughput/effectiveness claims remain outside this Gate and Block 14.

## 29. Diff summary

Gate corrections: bundle runner/empty verification/line bounds, empty CLI guard,
new Gate tests, adapted runner mocks, factual README/ADR/report/backlog notes and
this audit. Original Block 13 implementation changes remain intact and unstaged.
No test/source for Blocks 14–21 is introduced or removed; roadmap rows are equal
to base. Legacy rules AST excluding docstrings remains unchanged.

## 30. Final working tree

Required branch and exact HEAD are unchanged. Four tracked files are modified
(README, BACKLOG, CLI, legacy rule docstrings); seven intended new implementation/
audit files remain untracked. Three additional untracked operator lab scripts
retain their initial SHA-256. No staged files, commit, push or merge. Final status,
diff/stat/names and new-file hashes are recorded separately under /tmp/mimic13gate.
Blocks 14–21 scope rows and protected production modules remain byte-unchanged.

Reusable regressions are in repository. Raw evidence/scripts/logs/fixtures, base
archive, JUnit, failing-before reproductions, memory/resource samples, seed files,
legacy comparisons and package/install logs are in `/tmp/mimic13gate`, outside
production resources. Temporary evidence is local, not committed durability.

## 31. Decision

The three demonstrated medium defects are closed with failing-before and
passing-after evidence. The tested frozen-set contract, atomic no-overwrite
publication, explicit partial/literal/unverified scope and historical compatibility
are supported by real Hashcat and complete local checks. Approve local operator
commit review within the documented profile; supported-runtime PR CI remains
subsequent. No commit, push, merge or Block 14 implementation was performed.

**READY FOR COMMIT**
