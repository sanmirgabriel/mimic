# ADR 0004 — Local server-rendered Web UI

Status: implemented in Block 6.

`mimic serve` serves a dashboard at `http://127.0.0.1:8787/` together with
existing `/api/*` and `/docs`. Install the optional dependencies using
`pip install '.[web]'` from a checkout, or `pip install 'mimic[web]'` from a
built distribution. Core generation continues without Web dependencies.
Jinja2, python-multipart, HTTPX, FastAPI and Uvicorn belong to that extra.

The UI uses server-rendered Jinja templates, local CSS and HTMX 2.0.4. No Node
build or runtime CDN is required. HTMX's official minified distribution and
Zero-Clause BSD license are vendored in `mimic/web/static`; templates and static
assets are package data. A small local script switches generation modes,
confirms deletion and disables submit buttons while preserving the chosen
preview/generate action. Native `<details>` exposes advanced settings and
candidate provenance. Desktop/tablet layouts adapt using CSS media queries.
The keyboard skip link targets a focusable main landmark; table action labels
stay on one line while candidate and provenance values may wrap.

Forms translate strings, lists and selected identifiers into existing application
contracts. HTML and JSON adapters share `RecordService` for CRUD validation and
call the same repository and JobManager directly, without internal HTTP/ASGI
requests. Pydantic remains at the JSON HTTP boundary; the shared record service
has no HTTP dependency. HTML partial edits preserve omitted fields, including
profile fields, while explicit empty inputs clear the corresponding values. Saved-target
hydration uses the existing repository domain adapter, so organization
inheritance remains in domain/application code. `Target.name` and `profile.nome`
remain distinct; the UI explains their current fallback contract. The Web layer
does not assemble generators, policies or mutators, or infer origins from text.
Preview invokes `GenerationService.prepare()` and shows its actual summary and
warnings. It does not consume candidate iterators or open dataset/ready files.
Context extraction remains the deterministic `field: value` parser, with pasted
facts attributed to `web.pasted:<field>`.

The dashboard reads only stored records and lists; it shows the latest five jobs
and four engagements/targets. Job polling replaces the status/preview fragment
every two seconds only while pending or running. It reads the bounded persisted
preview (at most 200 rows), not the wordlist. Terminal fragments omit the polling
attribute. Full job detail resolves the configuration summary without consuming
sources. Download links use the existing completed-job API endpoint; cancellation
uses the existing cooperative worker contract. Origins and transformation params
are rendered from persisted structured data with presentation-only labels.

## Managed source uploads

Dataset/ready files allow `.txt`, `.lst`, `.wordlist` and `.dic`, with a 16 MiB
limit per file. Context files allow `.txt`, with a 256 KiB limit. Pasted context
is limited to 64 KiB. Text sources follow the existing UTF-8 reader contract.
The form accepts at most three files; a declared request larger than 50 MiB is
rejected before parsing. These are simple local-use bounds, not a remote upload
service contract.

Files are copied into `data_dir/uploads/<uuid>/<role>.txt`. Original browser
filenames are escaped display labels only; they never select a server path.
Only canonical UUID references and fixed roles resolve files. Root, directory
and file symlinks are rejected. Failed writes/oversized files remove partial
files and their newly created directory. An already successful upload remains
available on a validation error or configuration preview via hidden UUID fields,
so submitting the resulting form uses the same managed source.

At application startup, unreferenced upload drafts older than 24 hours are
removed. Files referenced by any persisted job, including failed/cancelled jobs,
are retained for historical configuration. Cleanup is deliberately nonrecursive:
it removes only known regular files inside managed UUID directories, skips
symlinks/unknown directories, and preserves unexpected content. Fresh drafts and
referenced files are untouched. There is no media library, periodic sweeper or
job deletion UI. Closing the server and restarting performs draft cleanup.

## Local security and errors

The existing CLI restricts bind addresses to loopback. No login or multi-user
contract is introduced. Jinja autoescape remains active; source, candidate and
error values never use `safe`. State-changing HTML forms require a random
application-scoped CSRF token. Tokens expire when the server restarts; reload
forms then. The JSON API keeps its body schemas and accepts programmatic clients without a
CSRF token. Unsafe API methods reject a supplied foreign/null `Origin` or
`Sec-Fetch-Site: cross-site`, including bodyless cancellation. Ordinary form
content types do not satisfy JSON model bodies. This browser-origin check is not
authentication; clients without browser origin headers keep the local API
contract. Local users with
access to the API/data directory retain the permissions of the single-user
application.

HTML/static responses carry a self-only CSP, `nosniff`, and a no-referrer
policy. `frame-ancestors` prevents embedding. HTMX evaluation, injected scripts
and indicator styles are disabled so polling works without inline/eval CSP
exceptions. `/docs` and `/redoc` retain their existing inline/CDN needs under a
separate CSP that still prevents framing. All other UI assets remain local.

Errors render escaped HTML with friendly 404/409/422 messages and preserve
submitted text and managed references where possible. Worker failure messages
remain sanitized by the existing Job Manager. Upload I/O errors use a generic
message. Unexpected Web failures render a generic HTML 500; traces are logged
only server-side. SQL and managed download containment are owned by the backend.
Returning through the browser back/forward cache restores submit controls;
polling failures keep the current fragment and add reconnect feedback.

## Validation and follow-ups

TestClient covers SSR CRUD, validation, escaping, uploads, inheritance,
configuration preview, job submission, terminal/polling behavior, cancellation,
download, and import optionality. CI already installs `.[dev,profile,web]` on
Python 3.10–3.12, so it discovers these tests without browser tooling. Wheel
validation must install outside the checkout and verify dashboard, local assets
and `mimic serve`; resource checks inside a checkout alone are insufficient.

FOLLOW-UP: records/job lists currently use existing unpaginated API endpoints;
pagination belongs to a later iteration if local histories become large.
FOLLOW-UP: abandoned-draft cleanup runs only on startup, and referenced uploads
are retained until a future explicit retention/job deletion policy is designed.
Gate 6 additionally uses a real Chromium browser to review screenshots and
exercise complete UI flows. That tooling and its synthetic data live in `/tmp`,
not in project dependencies or CI; the repository retains TestClient tests.
Known Target/ProfilePlan snapshot debts and greedy generation behavior remain.
No scoring, ranking, login or remote deployment is introduced.
