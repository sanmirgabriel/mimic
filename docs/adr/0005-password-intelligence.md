# ADR 0005: Password Intelligence supplies engine inputs

Status: accepted for Block 7. Gate 7 audit completed; awaiting operator review.

## Context

Organization/company facts should support useful hypotheses without repeatedly
entering obvious numeric primitives and role vocabulary. The existing structured
Candidate pipeline already owns case, leet, affix, reverse, combine, policy and
first-cause dedup. A second generator would split those contracts.

## Decision

`mimic.intelligence` contains plain frozen dataclasses and functions. Application
adapts domain facts into Candidates; intelligence depends only on generic core
Candidate/Seed values. Domain planning accepts generic supplemental numeric
Candidates. Core has no knowledge of intelligence, organizations or services. A generic
Seed may override its mutation stages; the same Generator still performs
composition, caps, reverse, policy and dedup.

`IntelligenceOptions` has enabled, common_numbers, recent_years, corporate_roles,
service_profiles and reference_year. Modern CLI and Web enable it by default.
Bare application requests, old JSON snapshots and legacy top-level CLI remain
disabled unless explicitly configured. CLI supports `--no-intelligence`.

Construction of an enabled GenerationRequest captures the local calendar year
once if omitted. Serialization and the existing JobManager roundtrip retain it;
workers never resolve the current year again. Tests use explicit reference years.
The fixed window is reference year first, followed by the three previous years.
There are no future years, arbitrary ranges or automatic decades.

`knowledge-v1` contains ten common numbers and six corporate roles. Five service
profiles (wordpress, mysql, postgresql, mssql, windows-ad) each supply two or three
identifiers and two roles. These are Python package modules, with no external
file loading or runtime network access. ServiceProfile describes vocabulary,
not username/password pairs. Service-specific roles remain available when the
corporate_roles toggle is off; that toggle controls universal corporate terms.

Application selects `TargetProfile.empresa`, company context facts, organization
name and aliases, in that order, retaining their original provenance. Valid
ASCII DNS hostnames (two or more labels, optional final dot) additionally supply
the lowercase **first DNS label**: `ACME.com.br` becomes `acme`. This rule does
not guess registered domains or strip `www`: `www.acme.com` yields `www`.
URLs, ports, paths, single labels and malformed hostnames are not normalized.
The raw domain remains an explicit organization input. Normalization records
`organization_domain_label` and the original domain origin. No NLP is involved.

Names and aliases are used verbatim. Equal organization terms use first encounter
order. The bounded templates are organization/role, organization/service and
service/role, each in both orders. Service/role pairs use only that service's
own roles; no cross-service role products are made.
These emit seeds only. `knowledge_template` records both operands, template ID
and built-in version. Candidate.join retains actual origins and operand history.
Numeric primitives have knowledge.common_number / knowledge.recent_year origins
and enter the existing AffixMutator. Templates are mutable, non-combinable Seeds.

Organization-only requests have no artificial Target. CLI `--organization` and
Web organization detail/form flow adapt directly to GenerationRequest. Quick
`-c` retains profile.empresa provenance and benefits from identical assembly.

## Encounter precedence

Preserve the existing first-cause semantics, inserting intelligence between ready
candidates and datasets: **Target/Profile (including explicit adapter/context
inputs), Organization, Ready Candidate, Password Intelligence, External Dataset,
PT-BR**. Mutated output of an earlier source wins an equal value from later
sources, as before. Ready candidates bypass all mutations and Combine.
Explicit numeric operands (manual, target date and context date) precede knowledge
numbers inside AffixMutator, preserving their causal attribution on collisions.
Knowledge-derived affixes of explicit target/organization seeds belong to the
knowledge phase when ready files are configured. Explicit operands first run
with explicit numeric tokens; ready files stream next; the original contextual
operands then run with supplemental tokens in the same Generator, before
knowledge seeds and datasets. A ready `Acme123` therefore wins a knowledge affix,
while an explicit/manual `123` affix still wins ready. Deferred operands include
existing explicit Combine outputs, never knowledge templates as Combine inputs.
No ready file is materialized or scanned ahead to choose winners.

Preview counts only bounded in-memory inputs and reports options, years, services,
version, seed count and number count without iterating candidates or corpora.
Knowledge seed counts exclude unchanged organization/company operands already
supplied by domain planning. For ACME + WordPress: 38 knowledge seeds = 6 global
roles + 2 service tokens + 2 service roles + 16 organization/role templates + 4
organization/service templates + 8 service/role templates. There are 28 template
seeds and 20 service-derived seeds (a subset, not an additional count), plus one
raw organization input and 14 numeric primitives. Counts are input causes before
mutation/dedup, so equal values with different recorded causes remain distinct.
Exact duplicate Seed values/causes/capabilities are eliminated conservatively.
Enabled Intelligence without any contextual seed, profile or configured source
is rejected during prepare with a contextual-seed error. An empty Target object
is not an anchor. Service-only generation is valid and emits only that profile's
tokens, roles and internal templates: global corporate-role seeds are suppressed.
With only dataset/ready/PT-BR sources configured, knowledge adds numeric operands,
not global role seeds. Summary corporate_roles_enabled reports effective use; the
original toggle remains unchanged in the persisted request. The existing warning
list identifies source/service-only requests without target/organization context.

## Boundaries and deferred work

Small lists/templates and existing per-word stage caps bound generation. Global
dedup still retains all encountered values; it is not constant-memory streaming.
Multiple selected profiles deliberately enlarge coverage. There is no global
budget, scoring, ranking or sorting by plausibility in this block (Block 10).
External corpora and Knowledge Packs remain Block 8. A separate default credential
catalog belongs to Block 9; vocabulary is not a catalog. There is no AI, remote
authentication, service connection, password spraying or attack execution.
README remains unchanged; documentation overhaul belongs to Block 15.
