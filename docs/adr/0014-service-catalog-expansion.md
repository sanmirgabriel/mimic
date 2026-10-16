# ADR 0014 — Service catalog expansion with immutable historical records

Date: 2026-10-16. Status: implemented; pending independent Gate 14 review.

## Decision and boundaries

Append exactly Zabbix, SonarQube Server, Jenkins, Apache Tomcat, Redis and
OpenSearch to the existing packaged tuples. ServiceKnowledge owns technology,
authentication conditions and official references; ServiceProfile owns a small
contextual vocabulary; DefaultCredential owns an explicitly associated,
source-qualified initial pair. The credential catalog remains passive, including
when a service is selected for generation. There is no authentication, discovery,
HTTP client, runtime scraping, downloaded corpus or credential testing.

Reuse plan_intelligence() and GenerationService unchanged. Core, mutators,
score-v1, diverse-v1, candidate-family-v1, caps, presets, API transport, Jobs,
SQLite and Hashcat exports remain unchanged. No dependencies or second knowledge
store are introduced. Service IDs are explicit opt-in generation operands.

## Collection and record version contracts

service-catalog-v1 remains the exact ordered seven-service/two-pair collection.
SERVICES_V1 and DEFAULT_CREDENTIALS_V1 retain every value and metadata field.
The standard lookup/export functions accept an optional keyword-only version;
requesting v1 returns that frozen view, including the original CSV bytes.
service-catalog-v2 identifies the thirteen-service/four-pair view. Its historical
members keep catalog_version=service-catalog-v1; new members use v2. A record's
catalog_version identifies its introduction revision, not the currently selected
collection. Unsupported collections fail explicitly, including empty lookups.

knowledge-v1 remains the unchanged common operands and planning/template
algorithm. The first seven ServiceProfiles keep that revision and exact order;
the six appended profiles use knowledge-v2. No old profile ID is remapped.
The summary/template knowledge_version remains knowledge-v1 because its algorithm
is unchanged. It does not claim that the entire expanded profile collection is
v1. Requests already snapshot the ordered selected IDs and captured year; there
is no need to add an aggregate catalog version to GenerationRequest or migrate
historical Jobs. Stable IDs pin immutable operands; future changes must retain
old IDs/operands or explicitly reject unsupported snapshots, never silently reuse
them. No generic knowledge-migration framework is added.

Credential record_version remains 1. Validation admits the two known catalog
revisions, requires the appropriate revision for each service ID, checks profile
revisions and requires credential revision 1 and matching service revision.
New credential records require explicit version_scope. Old null scopes remain
unchanged. Scope text and supporting sources are manually reviewed: natural
language version ranges cannot be proved disjoint by a syntactic validator.

## Evidence and conservative scope

Official sources were opened and reviewed on 2026-10-16. The report contains the
complete source matrix and restrictions. Versioned references are preferred:
Zabbix 7.4, SonarQube Server 2025.1, Tomcat tag 11.0.27 and OpenSearch 2.12.
Unversioned Jenkins and Redis documents establish no universal release range.

Zabbix's Admin/zabbix describes initial frontend setup and an immediate password
change recommendation. SonarQube's admin/admin describes Server 2025.1 initial
Developer/Enterprise Docker/ZIP setup, whose guide asks for a password change.
Neither pair describes an already changed account, arbitrary image, edition,
managed service or other release. Initial official attribution is not evidence
of successful authentication in an operator's installation.

Jenkins uses a generated installation-specific bootstrap password. Tomcat's
commented examples are disabled; enabling Manager needs explicit account/role
configuration. Redis OSS default/nopass, configured requirepass, ACL users and
Redis Cloud password/RBAC are distinct modes. OpenSearch 2.12 changes new demo
cluster installation to require a custom admin password, without retroactively
changing configured clusters. No historical OpenSearch pair is asserted here.
Zero cataloged pairs still comes with authentication evidence and limitations.

Profiles use only product spellings/aliases and one contextual account/role each.
Jenkins administrator is a conceptual role, not a claimed login; manager-gui is a
Tomcat role, not a shipped enabled user. Zabbix's product token happens to equal
its documented initial password: the token is justified by the product name,
not copied from DefaultCredential. There is no pair-to-seed adapter or Cartesian
username/password expansion. Existing heuristics can produce identical literals
through independent causes; common-v1 is unchanged and separately opt-in.

## Search, display, validation and exports

Discovery uses ID, display name, aliases, tokens and canonical English description.
Descriptions provide small category terms such as CI/CD, Java, cache and
DevSecOps without adding a taxonomy/model/API field. PT-BR/EN descriptions and
limitations are fully localized; category search uses the canonical English
metadata, while product IDs/aliases remain language independent.

CLI commands and Web routes are reused. The Web shows collection revision and
record/profile revision separately, references, authentication notes, localized
credential scopes and zero-pair states. The existing generation link checks only
the selected service. Generic weak values and generated hypotheses keep their
separate labels. Existing escaping, CSP, CSRF and theme behavior are retained.

Validation now checks both directions of profile/knowledge membership, duplicate
profile IDs, ambiguous cross-service aliases and case-insensitive alias duplicates.
Shared generation tokens such as db remain permitted. Same pair/scope cannot be
reintroduced merely with different applicability prose. Separate explicit scopes
require source review. Unicode format controls, including bidi overrides and
invisible format characters, join the existing rejected controls/line breaks.
HTML remains inert escaped text, not interpreted markup. HTTPS and reference
membership checks remain enforced.

CSV remains deterministic with the existing columns and includes source, all
restrictions and any version scope. Formula mitigation, quoting and atomic
no-overwrite publication are unchanged. No external URL is opened by normal
catalog lookup, generation, CLI or Web rendering.

## Validation and limits

The exact-base record fixture protects every historical catalog/profile/common
value and order. Tests exercise all six services, version failures, evidence,
CSV, unsafe metadata, localized Web, explicit profiles, unchanged scores/families,
API/Job roundtrips/restarts, passivity and hash seeds 1/42/777. Synthetic cost
measurement uses the existing engine and reports retained versus accepted work;
its separate global-dedup replay is excluded from normal timing/RSS metrics.

See [Block 14 report](../BLOCK14_IMPLEMENTATION_REPORT.md) for full-suite results,
exact-base output/Jobs/Hashcat comparisons, real Firefox layouts, offline builds
and external installs. This is a finite, manually curated catalog; evidence is
not a universal release/deployment claim or an effectiveness probability.
Blocks 15–21 retain their scope and order. No commit, push or merge.

## Independent Gate 14 follow-up

[Gate 14](../GATE14_AUDIT.md) independently verified the source qualifications,
immutable historical views, passive pairs and compatibility. Its only production
fix keeps explicit ownership of the CSV export descriptor through fdopen failure;
publication semantics remain unchanged. The complete final suite has 2,096 passing
tests. version_scope remains reviewed prose: structural validation cannot prove
that arbitrary natural-language scope matches the cited source. No new schema
or semantic version parser is introduced. Supported-runtime CI remains subsequent.
