# ADR 0010: Service Intelligence and a passive default credential catalog

Status: implemented; pending approval at Gate 10.

## Context and decision

Operators need technology context, documented initial credentials and a small
common weak-value library without confusing these different claims. Preserve
one engine: Service Intelligence → structured Seeds/Numbers → GenerationService
→ existing Generator → policy/dedup → score-v1/Top-K → adapters and Jobs.
The associated credential catalog has a separate read-only lookup/export path.
It never supplies username/password pairs to generation or performs login attempts.

Frozen `ServiceKnowledge`, `DefaultCredential` and
`CommonCredentialVocabulary` dataclasses describe the packaged knowledge.
`ServiceProfile` retains its existing shape and five original profiles, in their
original order and with identical tokens, roles and knowledge-v1 metadata.
Grafana and RabbitMQ profiles are appended. `plan_intelligence()` and its bounded
organization/service/role templates are reused without modification.

`mimic.intelligence.catalog` owns immutable Python tuples, local deterministic
case-insensitive lookup and CSV serialization shared by CLI and Web. No external
file loader, database, ORM, provider framework, HTTP client or downloads are
needed. The existing Pack registry remains the mechanism for large external
corpora. Catalog validation rejects duplicate IDs/pairs, dangling services and
invalid source URLs or evidence relationships.
Catalog text is limited to 4096 characters and IDs (including catalog/collection
version IDs) to 64;
control characters, line breaks, malformed hosts/ports, non-HTTPS URLs and userinfo
are rejected. Record revisions are positive integer strings. Mutable input lists
are copied into tuples, including nested documentation references.

## Evidence and applicability

Catalog version: `service-catalog-v1`; credential record version: `1`.
Official sources were reviewed on **2026-10-09**. This is a static curated record,
not an assertion that future documentation or installed products are unchanged.
Version scope remains null where the source does not establish a release range;
no universal release compatibility is inferred from a latest-docs URL.

- [Grafana first sign-in](https://grafana.com/docs/grafana/latest/setup-grafana/sign-in-to-grafana/):
  initial admin/admin under default configuration; custom configuration can
  change it and the first successful login prompts a password change.
  [Roles and permissions](https://grafana.com/docs/grafana/latest/administration/roles-and-permissions/)
  support the admin/viewer contextual vocabulary. These roles are not extra
  documented username/password pairs.
- [RabbitMQ access control](https://www.rabbitmq.com/docs/access-control):
  a blank broker normally creates guest/guest; guest is restricted to localhost
  by default for every protocol. Importing definitions at initial boot prevents
  creation of this default user. Configuration and administrators may change or
  remove the account. All these restrictions accompany both display and export.
- [PostgreSQL authentication](https://www.postgresql.org/docs/current/auth-methods.html)
  and [initdb](https://www.postgresql.org/docs/current/app-initdb.html): methods
  depend on configuration; the bootstrap superuser defaults to the OS user
  running initdb. postgres is an installation convention, not a universal
  postgres/postgres pair. No pair is included.
- [WordPress installation](https://developer.wordpress.org/advanced-administration/before-install/howto-install/):
  the installer asks the operator to choose administrator credentials. No
  universal administrative pair is included.
- Existing MySQL, SQL Server and Windows/AD vocabulary remains contextual. Notes
  link to the [MySQL initial account](https://dev.mysql.com/doc/refman/8.4/en/default-privileges.html),
  [SQL Server authentication modes](https://learn.microsoft.com/en-us/sql/relational-databases/security/choose-an-authentication-mode)
  and [Active Directory accounts](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/manage/understand-default-user-accounts).
  No undocumented password pair is inferred from account names.

Only two associated pairs are cataloged. `documented_default`, `common_value`
and `generated_candidate` are distinct presentation categories, never confidence
percentages, authentication statuses or prevalence claims. Official attribution
establishes evidence for an initial setup, not successful authentication now.

## Common passwords: explicit opt-in and snapshots

`common-credentials` / `common-v1` contains six conventional usernames and six
weak passwords. The lists have no necessary association, frequency ordering,
probabilities or Cartesian product. Usernames are lookup/export data only.
Values retain their exact Unicode spelling and spaces; no trimming, case folding
or Unicode normalization is applied to credential values. Empty/all-space values,
duplicates and invalid text are rejected. Canonically equivalent Unicode strings
with different code points remain different values.
The common passwords are available through `--include-common-passwords`, the
matching unchecked Web source checkbox or the request source option.

`SourceOptions.include_common_passwords` defaults to false. Disabled requests
omit both this field and `common_passwords_version` from JSON, preserving the
previous serialization contract and GenerationPlanSummary shape. Enabled
requests capture `common-v1` at construction, serialize it and validate it on
roundtrip; unknown versions fail explicitly rather than silently upgrading.
The existing JobManager snapshot roundtrip freezes service IDs, this option and
its version. No persistent schema change is needed. Future collection versions
must retain supported old collections or reject unsupported snapshots explicitly.
The version identifies the exact ordered collection: any content/order change
requires a new version. Unlike external Packs, these small built-ins do not store
a content digest in the request. Pinning relies on the packaged version contract;
it cannot detect a package that incorrectly reuses an existing version for changed
data. Only common-v1 is currently supported; older/unknown versions are rejected.

Application introduces common values as generic `Seed` objects with
`mutable=False, combinable=False`. These are ready candidates: no case/leet,
number/year/separator affixes, reverse or Combine expansions. They still pass
through canonical policy, first-cause dedup and ranking. Source precedence is
unchanged when disabled; when enabled the small ready list follows explicit
Ready files/Ready packs and precedes mutable knowledge seeds. Existing deferred
numeric expansion keeps ready-value precedence over supplemental affixes.
Target/context/organization outputs retain their established earlier precedence.

Provenance is `Origin('knowledge', 'common_password', value)`, with no invented
Transformation or service attribution. The Web has a specific localized origin
label. score-v1 already treats unrecognized knowledge fields without a source
bonus; common ready values therefore receive no new priority weight. All origin
weights/caps, transformation scoring, budget presets and Top-K remain unchanged.
Documented credential pairs never enter Candidate, scoring or ranking.

## Adapters and operator flow

English CLI: `services list [--search TEXT]`, `services show ID`,
`credentials list [--service ID] [--category documented|common]` and
`credentials export --format csv --output FILE` with the same filters.
Common is global: combining it with a service filter is rejected. Documented CSV
has service,username,password,type,source_url,applicability columns; applicability
includes restrictions and any recorded version scope. Common CSV has independent
category/value rows with common_value, collection and version, never pairs.
Standard CSV quoting preserves commas/quotes; formula-like cells receive a
leading apostrophe to prevent spreadsheet evaluation. Existing export destinations
are rejected and preserved. The apostrophe is an export representation only:
canonical values in the catalog are unchanged, and consumers needing exact values
must account for this documented spreadsheet mitigation. Control characters and
embedded line breaks are invalid catalog data, while Unicode, commas and quotes
roundtrip through standard CSV parsing. Export writes a private temporary file in
the destination directory, flushes/syncs it and publishes with an atomic hard link
that refuses existing files/symlinks. Write/publication failures remove staging
without exposing partial output; filesystems without hard-link support fail
explicitly. Generation's existing output semantics are unchanged.

Web `/services` supports local search by ID, display name, aliases and tokens;
`/services/ID` shows conditions, references and distinct category badges.
`/services?category=common` displays the independent weak-value lists.
`/generate?service=ID` preselects a validated ID in the existing generation form;
GET never prepares or runs generation and existing target/organization selections
remain available. POST preview and generation use the same GenerationRequest,
CSRF validation and JobManager. No duplicate generation form or catalog Web
export endpoint is introduced; the page documents CLI export.

The PT-BR/EN request-local catalogs localize new interface text and knowledge
notes while leaving names, IDs, credential values, URLs and stored provenance
canonical. Existing theme scripts, CSP, HTMX and locale preferences are reused.
CSS uses existing semantic tokens for dark/light, wraps source URLs and keeps
credential tables inside local overflow containers on small screens.

Existing API routes, status codes, persistence and Jobs are unchanged. Their
normal request JSON transport can carry the explicit new source options. No
new catalog API is needed for the SSR/CLI workflows.

## Boundaries, compatibility and limitations

No remote login, brute force, spraying, scanning, host detection, validation,
scraping, leaked credentials, ML/LLM, frequency scoring or downloads. Runtime
queries stay local; reference URLs are optional operator navigation. README,
Core, mutators, domain planning, intelligence planning, scoring/ranking and
SQLite schemas remain unchanged. New options are off by default, and old service
profiles retain their ordering, vocabulary and generation behavior.

Tests cover evidence, association, serialization, opt-in capability semantics,
policy/dedup/ranking, bounded templates, Jobs/API, locale/escaping/CSRF and
PYTHONHASHSEED 1/42/777 equivalence. Gate validation additionally compares against
the required merge base, checks wheel/sdist and installed behavior, and exercises
actual browser layouts. New test payloads are small and use short stable IDs.
CI remains the complete suite on Python 3.10/3.11/3.12 with duration reporting.

The catalog is intentionally small, manually reviewed and not an exhaustive
technology/default inventory. Absence of a pair means none is cataloged, not that
all distributions of that product lack defaults. Further documented pairs need
precise sources and conditions; large corpora use Packs. Block 11 remains future
work and is not started here.
