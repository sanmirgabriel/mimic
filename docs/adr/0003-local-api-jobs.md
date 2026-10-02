# ADR 0003 — Local API, SQLite and in-process jobs

Status: implemented in Block 5.

MIMIC remains a single-user, local-first tool. `mimic serve` listens on
`127.0.0.1:8787` by default and accepts only loopback bind addresses. There is
no login or remote deployment contract; remote access requires a separate
security design. FastAPI and Uvicorn are optional dependencies in `mimic[web]`.
The CLI generation path does not import them.
Accepted bind hosts are the literal addresses `127.0.0.1` and `::1`;
`localhost` is deliberately rejected rather than resolved through DNS.

SQLite stores engagements, organizations, targets, job metadata and the first
200 structured candidates per job. Foreign keys block deletion of referenced
domain records, so historical jobs cannot lose target metadata. Each storage
operation opens its own connection; WAL and a five-second busy timeout support
moderate local concurrency. UTC timestamps are ISO 8601 strings. Data lives
under `$XDG_DATA_HOME/mimic` or `~/.local/share/mimic`, with `--data-dir` for
other locations and tests.

The job manager uses one worker thread by default. Each job stores a serialized
`GenerationRequest` immediately and the worker reconstructs that snapshot.
Editing a stored target or organization later does not rewrite the job. The worker invokes
`GenerationService.prepare()` once and consumes the resulting one-shot
`PreparedGeneration` once. It streams values to a job-specific
`wordlist.txt.part`, batches count updates, and persists only the bounded
preview with real origins and transformations. The full wordlist stays in a
file, not a SQLite blob, to avoid loading or committing millions of candidates.
On success the `.part` file is atomically renamed to `wordlist.txt`, and only
completed jobs may download it. Cancellation is cooperative and persisted;
failed/cancelled jobs remove partial output. At startup pending/running jobs
from a prior process become failed with a restart reason. Orphan `.part` files
and final output files for non-completed jobs are removed.

State transitions are `pending → running/cancelled` and
`running → completed/failed/cancelled`. Terminal states never transition again.
The `pending → running` claim and cancellation/completion checks use conditional
SQLite updates. If cancellation commits before completion, cancellation wins;
if completion commits first, a later cancel is a no-op. A successful rename
precedes the `completed` database update, so there is no committed completed
state without the file during normal execution. A crash between rename and
update leaves an incomplete job and an orphan final file; startup marks the
job failed and removes that file. A completed record whose final file is
missing remains completed but download returns an error rather than inventing
output. Count means lines written to the temporary file before completion or
cancellation. File handles close before rename and state update.

The manager's start/stop pair owns worker threads; duplicate start is a no-op,
duplicate stop is safe, and submit after stop fails. Shutdown persists
cancellation and waits for workers to observe it at the next yielded
candidate. A blocking source can therefore delay shutdown; threads are not
force-killed. The database uses schema version 1 (`PRAGMA user_version`) and
rejects unknown future versions without introducing a migration framework.

PATCH leaves omitted fields unchanged. Explicit `null` clears optional
engagement/organization references and description; it is rejected for names,
profile and list fields. Malformed path UUIDs return HTTP 422 and valid UUIDs
without a matching record return 404.

Workers and the API both use the application service; neither assembles core
mutators. Redis/Celery would add deployment and failure modes without benefit
for this local single-user queue. Browser uploads are deferred to Block 6.
Dataset and ready-candidate paths remain lazy external inputs: their contents
can change between submission and execution. A future managed upload path can
make those inputs reproducible; this block snapshots configuration only. API
paths refer to files on the host running MIMIC, not the browser's machine.
