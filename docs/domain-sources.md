# Block 3 domain and source contracts

`mimic.domain.models` holds in-memory Engagement, Organization, Target,
Source and Generation objects. `Target.profile` is the password-engine view
of the person. When the profile has no `nome`, planning uses `Target.name` as
a target seed. An attached Organization supplies separate, non-combinable
name, alias, keyword, location, domain and relevant-date seeds. Nothing is
persisted. `Generation.sources` records requested source metadata; callers
provide extracted facts and source iterators to `prepare_generation`.

`mimic.core.seed.Seed` exposes only `candidate`, `combinable` and `mutable`.
Core imports no domain model. Legacy `base_words` and `isolated_seeds` retain
their order and semantics. New seeds are appended after legacy seeds;
ready candidates (`mutable=False`) bypass all mutators but still pass through
value dedup and policy. Extra combinable seeds can combine only with the
explicit safe partner list; corpus and built-in dataset seeds default to
non-combinable. This protects Combine from accidental O(N²) corpus input.

`prepare_generation` is a Python API shared by the CLI and future interfaces.
It records four conceptual target/date patterns; actual emitted combinations
remain the existing causal Affix transformations. No scoring or ranking is
performed.

The deterministic `.txt` context format accepts `field: value` lines, `#`
comment lines and comma-separated `apelidos`. Unknown fields and malformed
lines fail. Values remain raw facts with `context_file` origin including the
path and field. The extractor protocol can be replaced later; no free-text
inference occurs. `mimic profile inspect FILE` prints parsed `.txt`, YAML or
JSON context without generating candidates.

`mimic generate` accepts `-n/--name`, `-d/--birth-date`, `-t/--team`,
`-p/--pet`, `-c/--company`, `--context`, `--dataset`, `--candidates` and
`--ptbr`, alongside all legacy flags. The bare `mimic --names ...` form
still works. `--dataset` and `--candidates` read local files incrementally
and enforce `--max-dataset-lines` (default 100,000 physical lines). Both
skip blank/comment lines and retain file/line provenance. The limit fails
explicitly if exceeded; because output is streamed, an output file can be
partially written before that error. `--ptbr` opts into small, versioned
data files; it is never enabled implicitly.

When the same output value has several causes, first causal derivation wins.
The CLI visits combinable legacy names, inline names, profile names and
context names first; then non-combinable profile/inline/context fields; then
organization seeds (when using the Python API), ready candidate files,
dataset files, and PT-BR built-ins. Within each group it
preserves caller/file order. Ready candidates therefore precede corpus seeds
but do not override a value already produced by a target seed. Python API
callers explicitly control the order of their `extra_seeds` iterable.

Repeated context fields are retained as separate facts in file order during
generation. `profile inspect` displays repeated fields as ordered lists;
single scalar fields remain strings. It does not merge their provenance.

Follow-ups: validate and normalize the full domain object graph as its API
stabilizes; support combining multiple non-corpus extra seeds with one another;
design an atomic output strategy for late streaming errors; replace the
pattern labels with a richer behavior planner if needed. No database, UI,
LLM, scoring, ranking or global attack budget is included here.
