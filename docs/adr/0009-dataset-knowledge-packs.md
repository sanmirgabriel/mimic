# ADR 0009: Local dataset and knowledge packs

Status: Implemented; Gate 9 validation complete, pending approval before commit.

## Context

External UTF-8 corpora need stable identity, attribution and reproducible bytes
across CLI and Web jobs. A pack supplies data to the existing generator; it
does not introduce another mutation pipeline, ranking engine or knowledge model.

## Decision

Use the small `mimic.packs` package: immutable metadata/reference dataclasses
and one filesystem registry shared by both adapters. JSON manifests are the
index; no SQLite table, schema migration or new runtime dependency is required.

### Identity, storage and import

An identity is `id@version`. Import normalizes IDs to lowercase ASCII; versions
are bounded plain identifiers, without requiring SemVer. Display names do not
determine identity. Multiple versions coexist. The same identity/hash is
idempotent only when all immutable metadata also matches, including kind,
filename, name, attribution, license and source URL. Conflicting bytes or any
metadata change is rejected explicitly; use a new version for changes.
No remove, update or automatic version fallback is provided.

`DataPaths.packs` lives at `<data-dir>/packs/<id>/<version>/`. Each version
contains `manifest.json` and `corpus.txt`, separate from temporary Web uploads.
The original filename is attribution metadata, never a managed filesystem path.
The registry uses the configured directory, independently of process cwd.

Imports copy explicitly selected local regular text files in 64 KiB chunks,
checking UTF-8, SHA-256, bytes and physical lines. Universal CR/LF/CRLF newline
counting matches `stream_dataset`; blanks and comments count toward the line
limit. Validated payload and manifest are fsynced in a private staging directory
and published by directory rename. Exceptions remove staging files. A process
kill or machine crash may leave an ignored `.import-*` staging directory, never
an installed version; crash-recovery cleanup is deferred.

Web imports use the existing 16 MiB ceiling and accept uploaded files, never
server paths. CLI imports have a 1 GiB maximum, reducible with `--max-bytes`.
Accepted extensions are `.txt`, `.lst`, `.wordlist` and `.dic`. Archives, NUL
bytes, symlinks and nonregular sources are rejected. Descriptor-relative,
`O_NOFOLLOW` directory/file operations confine managed access on POSIX systems.
Manifests have a 64 KiB ceiling, all schema fields required (including nullable
`source_url`), strict types and duplicate-key rejection. Schema 1 serializes the
physical count as `physical_line_count`; the Python `line_count` property is a
read-only alias. Unicode surrogates and control characters are rejected in
metadata and attribution URLs. Unknown and future schema fields are rejected.
Source URLs are HTTP(S) attribution only; no runtime network access occurs.

Concurrent imports use independent staging directories. POSIX rename cannot
replace a published, nonempty version directory: the losing import reads the
winner's manifest, rejects all conflicts, verifies its corpus and cleans its
own staging. This guarantee relies on POSIX directory/descriptor operations and
an ordinary local filesystem; no non-POSIX portability is claimed. An unrelated
writer with access to managed storage is outside the publication protocol.
Failure opening a newly created staging directory removes that empty directory.
A failure fsyncing the parent after a successful rename can report an import
error while leaving a complete, verifiable installed version. Publication is
atomic visibility, not a promise of rollback or universal power-loss durability.

### Request snapshots and execution integrity

`SourceOptions.packs` is an ordered tuple of digest-pinned `PackReference`
objects. References contain id/version/SHA and frozen manifest metadata.
Requests without packs omit this optional JSON field to preserve the old
contract. API consumers may submit minimal id/version/SHA references; the
configured registry validates and expands them when creating the job snapshot.
At most 64 unique packs can be selected.

Preview and job rendering read only manifests and stored snapshots. They do not
verify hashes, count payload lines or generate candidates. Historical metadata
remains visible when the source is unavailable. Execution resolves the exact
snapshot, verifies all selected files before producing any candidate, and holds
their regular-file descriptors until completion or cancellation. Files are
hashed again while streaming to detect mismatches in the bytes actually consumed.
Missing content, changed metadata, digest, size, UTF-8 or line counts fail
explicitly; a different version is never substituted.

The existing job `.part`/atomic completion logic removes incomplete outputs
after failure or cancellation. CLI pack file output also stages before rename,
preserving an existing destination if generation fails. Stdout is a stream and
cannot retract lines already emitted if a file is edited during execution;
such an edit raises an explicit error when that source finishes.

An open descriptor pins the inode, not immutable bytes. Atomic replacement,
unlink or replacement with a symlink cannot redirect an already open descriptor:
execution can finish using its verified original content. In-place edits to
unread bytes or truncation can fail the streaming hash/size/UTF-8 checks. Edits to
already read or buffered bytes may remain invisible to that execution; a later
verification detects them. There is no filesystem snapshot, file lock or
absolute concurrent-tamper guarantee. Every detected mismatch prevents Job and
CLI file publication. SHA-256 detects content drift against a pinned reference;
it does not authenticate an operator-controlled manifest or establish trust in
the source. A writer changing both manifest and corpus can redefine what a new
unpinned selection trusts, but cannot silently change a frozen Job reference.

CLI stdout starts only after all selected packs pass pre-verification. An
exhaustive run then emits candidates as they arrive; a final mismatch exits 1
with an error on stderr, leaving any emitted lines in stdout, redirects or pipes.
I/O failures exit 2. Ranked output scans before emission. `-o` stages on the
destination filesystem and publishes only after successful completion; it
preserves an existing file on failure without buffering the wordlist in memory.

### Sources, types and provenance

Keep target/context/organization planning unchanged. The supplementary source
chain is:

1. Explicit ready-candidate files.
2. Selected Ready packs, in supplied order.
3. Knowledge seeds.
4. Explicit external datasets.
5. Selected Seed packs, in supplied order.
6. Existing PT-BR built-ins.

Without selected packs the previous order and output remain identical. The
generator preserves first causal derivation wins, including cross-pack
duplicates; alternative origins are not merged or selected by higher score.

Seed packs use `mutable=True, combinable=False`. Ready packs use
`mutable=False, combinable=False`, bypassing all mutation stages. Normalization,
comments, blank-line handling, policy, caps, dedup, exhaustive streaming and
Top-K continue through the existing Core. Packs never automatically become
Combine partners. Provenance uses canonical `dataset` or `ready_candidate`
sources and `pack:<id>@<version>:<physical-line>` fields, without operator paths.
Candidate/Origin/Transformation and score-v1 are unchanged. Pack language does
not grant a PT-BR scoring bonus or activate the built-in corpus.

### CLI and Web

CLI commands remain English: `packs list`, `show`, `import`, `verify`; each
supports `--data-dir`. Generation adds repeatable `--pack ID@VERSION` and
`--data-dir`, preserving existing flags. Web provides an SSR Packs page for
import, details and explicit integrity verification, plus optional checkboxes
in the existing sources disclosure. Checkbox order follows the displayed list;
the submitted order is preserved within each kind. New text uses the existing
PT-BR/EN catalogs and CSS tokens, with the existing locale/theme behavior.
Import and verification require CSRF and reject cross-origin browser posts.

### Licensing and local examples

Manifests record the operator's declared license, URL and upstream attribution.
`NOASSERTION` displays a redistribution warning. Declarations are not a legal
license audit; a repository license does not prove that every included source
has identical conditions. No corpus is downloaded or externally bundled.

SecLists can be imported from a local installation. Its current
[directory listing](https://github.com/danielmiessler/SecLists/tree/master/Passwords/Common-Credentials)
contains `xato-net-10-million-passwords-1000.txt`; the originally proposed
`10-million-password-list-top-1000.txt` is not present. SecLists declares
[MIT](https://github.com/danielmiessler/SecLists/blob/master/LICENSE), with Daniel
Miessler attribution; operators should inspect the selected material's terms.
For an existing local checkout:

```bash
mimic packs import /usr/share/seclists/Passwords/Common-Credentials/xato-net-10-million-passwords-1000.txt \
  --id seclists-common-1000 --version 1 --kind ready --language en \
  --license MIT --source-url https://github.com/danielmiessler/SecLists \
  --attribution 'SecLists / Daniel Miessler; review selected source terms'
mimic packs verify seclists-common-1000@1
mimic generate --organization ACME --pack seclists-common-1000@1 --budget focused -o acme.txt
```

The path depends on a local installation; MIMIC does not create or download it.
`tests/fixtures/br-workplace.txt` is small original professional vocabulary,
with UTF-8 accents and no frequency claim. It is a test/demo fixture, not a
production starter pack and not enabled automatically. Import explicitly:

```bash
mimic packs import tests/fixtures/br-workplace.txt --id br-workplace --version 1 \
  --kind seed --language pt-BR --license NOASSERTION
mimic generate --organization ACME --pack br-workplace@1 --budget focused -o acme.txt
```

### Tradeoffs and limits

Verification adds a complete incremental read before execution; payload is
then streamed again for generation and checked against its original digest.
There is no corpus cache or new O(N) pack preparation set. The existing Core
dedup/seed sets still retain O(N) state, and a single very long line uses memory
proportional to that line, as with direct datasets. Limits apply per file;
excess physical lines fail rather than truncate. Seed mutation can greatly
multiply work, subject to the unchanged per-word caps. Budgets limit retained
results, not the complete scan. Cancellation checkpoints run during verification
and existing ranked evaluation.

Gate 9 measured a 16 MiB single Ready line at approximately 87 MiB process RSS.
The CLI 1 GiB file ceiling alone is insufficient to bound per-line memory or
checkpoint latency tightly; operators can lower `--max-bytes`. A future simple
import-time ceiling of 1 MiB per physical line is proposed for packs only, counted
incrementally before decoding/materializing a line. It accommodates the verified
64 KiB and 1 MiB fixtures, but adopting it needs compatibility review for local
corpora. This audit does not impose a new arbitrary limit on existing inputs or
change legacy datasets. Verification remains chunked; streaming cancellation
checks each physical line, including blanks/comments, and normal generation
checkpoints. A single long line can delay the next streaming checkpoint.

Streaming also checks recorded byte/physical-line bounds and cancellation on
blank/comment lines, so a growing or comment-only source cannot evade those
checks. Firefox POSTs using `Origin: null` under the existing no-referrer policy
are accepted only with `Sec-Fetch-Site: same-origin` and a valid CSRF token;
external origins, cross-site metadata and missing tokens remain rejected.

This block does not add downloads, archives, marketplaces, updates, frequency
scoring, credential pairs, ranking diversity, learned patterns or remote login
execution. Block 10 is the next product milestone.
