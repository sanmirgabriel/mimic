# ADR 0002 — Reusable application service

Status: implemented in Block 4.

## Context

Generation assembly lived inside `cli.py`: it parsed arguments, then built
seeds, source precedence, mutators, the password policy and the `Generator`
inline. A future API, Web UI or background job would have had to duplicate all
of that, and any divergence would silently produce different passwords for the
same target. The engine was reusable; the *use case* around it was not.

## Decision

A new `mimic.application` package holds the shared use case. Every adapter --
the CLI today, an API/Web UI/job tomorrow -- speaks to it through the same
three objects and never reaches past them into planning or the engine.

```
adapter → GenerationRequest → GenerationService.prepare → PreparedGeneration
                                                              → iter_candidates()
```

`mimic.application` never imports `argparse`, `sys`, stdout/stderr, HTTP, HTML,
a templating engine or a database. Those are adapter concerns. The layering is:

- **core** — the generic engine (candidates, mutators, generator, policy,
  sink). Imports neither `domain` nor `application`.
- **domain** — the target/organization/source model and `domain.planning`,
  which owns source precedence and mutator/policy/Generator assembly. Imports
  `core`, never `application`.
- **application** — the use case. Imports `core`, `domain`, `profile`,
  `mutators`. Calls `domain.planning`; the reverse never happens.
- **cli** — a thin adapter over `application`.

### GenerationRequest

A frozen-ish dataclass describing one generation with no runtime object: no
`argparse.Namespace`, no open file handle, no stream, no HTTP request. It
accepts domain objects (`Target`, `Organization`) directly, structured
`context_facts` **or** a `context_path`, streaming source paths, PT-BR toggle,
and grouped options (`MutationOptions`, `PolicyOptions`, `GenerationLimits`,
`SourceOptions`). Free, adapter-specific seeds (a CLI `--names` file) are
carried as pre-attributed `Candidate` tuples: only the adapter knows a value
came from `--names`, so the adapter attributes it and the application never
fabricates a `"cli"` origin of its own.

The CLI passes a loaded profile as `Target`, quick fields as pre-attributed
`ExtractedFact` values, and `--context` as `context_path`. It does not call
the profile planner for normal generation. The separate Hashcat export path
still obtains profile date tokens directly because it exports rules rather
than using the candidate-generation service.

`to_dict()` is deterministic and JSON-safe (strings, numbers, booleans, `None`
and nested containers only), suitable for persisting a future job. `from_dict()`
rebuilds and revalidates it without silently coercing strings to booleans,
integers or transformation metadata. File paths stay configuration and are never
materialized here.

### GenerationService and PreparedGeneration

`GenerationService.prepare(request)` validates, resolves context, builds the
`GenerationOptions`, assembles the lazy source chain and delegates to
`domain.planning.prepare_generation`. It is **side-effect light**: it opens no
dataset file, generates no candidate, writes nothing and prints nothing. It
returns a `PreparedGeneration` carrying the resolved plan, deterministic
`warnings`, and a `summary()` preview.
In-memory Organization facts are snapshotted during planning so later edits to
the mutable domain object cannot change the prepared output or its counts.
Dataset contents remain intentionally read at iteration time.

`PreparedGeneration.iter_candidates()` streams `Candidate` objects lazily and
single-pass; `iter_values()` is the value projection in identical order. The
first call to either method claims the plan. A second call raises
`ApplicationError` explicitly, even if the first iterator was not exhausted.
Execution -- including opening dataset files -- happens only while iterating,
so a future job can loop and break on cancellation without any change here.

### Why output does not belong to the service

The service returns an iterator; it never writes a file or touches stdout. Each
adapter owns its own consumer: the CLI keeps its `Sink`, a future API would
stream an HTTP response, a job would persist rows. Folding output into the
service would re-couple the use case to one delivery mechanism -- exactly the
coupling this block removes.

### Plan preview and warnings

`summary()` reports what is knowable without executing: target and
organization **engine-input** counts before dedup/mutation (a date can expand
to multiple token inputs), context-fact count (parsed facts, including each
alias, kept separate from seed counts), PT-BR flag, dataset and
ready-candidate *source* counts, enabled mutators, combine flag, policy and
limits. Streaming corpora are never read to count lines; their line count is
reported as `None` (unknown), or `0` when no dataset is configured. This is the data a future Web "Generation
Preview" renders. `warnings` is a deterministic `tuple[str, ...]` (for example
`combine enabled`, `no target-specific seed`, `external dataset configured`).

### Errors

`ApplicationError` and `InvalidGenerationRequest` are the whole hierarchy. The
application never raises `SystemExit`. The CLI translates `ApplicationError`
into a message and exit code; a future API would translate it into an HTTP
response.

## Source precedence

The Block 3 causal order is unchanged and now lives entirely in
`application`/`domain.planning`, never implicit in the CLI:

```
target/profile → organization → ready candidates → external datasets → PT-BR
```

`first causal derivation wins`: for an equal value across sources, the earliest
derivation is canonical. The service does not aggregate provenance, reorder,
rank or sort. Ordering stays causal and deterministic; scoring is a later block.

## Hashcat export

Rule export keeps its own CLI flow and is deliberately **not** forced through
`GenerationService`; it produces a `.rule` file, not a candidate stream.
Converging the two onto a shared transform model is left for a future block.

## Compatibility

The CLI is byte-for-byte equivalent to Block 3: on a rich configuration
(context + dataset + ready candidates + PT-BR + combine + leet + policy) it
produces the identical ordered output it did before the refactor. The quick
CLI, the legacy flags (`--names`, `--profile`, `--numbers`, `--combine`,
`--leet`, `--export-rules`) and `profile inspect` all still work, and every
generation path now runs through the single `GenerationService`.

## Follow-ups (not implemented)

- **Target.name vs profile.nome.** The documented contract is unchanged:
  `profile.nome` wins, and `Target.name` only fills the gap when `profile.nome`
  is empty. This is now centralized in `domain.planning` and tested directly.
  A future block may redesign `Target` to remove the dual field.
- `from_dict` reconstructs candidate provenance mechanically; if requests grow,
  a dedicated (de)serializer belongs next to the models.
- Streaming-time errors (an over-limit dataset surfaced during draining) still
  reach the adapter as `ValueError`. Wrapping late errors as `ApplicationError`
  can follow once the API adapter needs it.

README is left untouched to preserve the operator's existing edits.
