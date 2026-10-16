# MIMIC — Block 14: Service Catalog Expansion

Date: 2026-10-16. Local implementation for independent Gate 14 review.
No commit, push, merge or Block 15 work.

## 1. Baseline and branch

Repository: sanmirgabriel/mimic. Required and final HEAD:
`93bd6807b71fd8859a2e202dd02b6ac75020f1b4`.
Initial checkout was feat/hashcat-convergence at PR #18 head
`b5c5317eed81d4a97ce9ac88a5bba17d56d90279`, with only three operator scripts
untracked. Fetched main, confirmed the merge SHA and ancestry, checked that its
tracked tree equals the PR head, and created feat/service-catalog-expansion at
the exact mandatory base. No operator changes were discarded or staged.

[PR #18](https://github.com/sanmirgabriel/mimic/pull/18) is merged. Its post-merge
main [CI run 38909323305](https://github.com/sanmirgabriel/mimic/actions/runs/38909323305)
is completed/success for Python 3.10, 3.11 and 3.12, independently checked through
the GitHub API on 2026-10-16. That result certifies the base, not this working tree.

Read ADR 0010, previous implementation/Gate reports, ADRs 0012.6/0013, catalog,
profiles/models/planning, application requests/generation, CLI, Web routes,
template/i18n, service tests, Jobs/snapshots, README and BACKLOG before editing.
Complete pre-edit baseline: **1,954 passed in 561.20s**, no errors/failures/skips.
The initial sandbox attempt stalled in a Web TestClient and was terminated;
the completed baseline allowed the required local threads/subprocesses.

## 2. Architecture preserved

One existing engine and one packaged catalog. No database, ORM, plugin system,
provider framework, dependency, request schema, migration, login, network probe,
runtime source fetch, external corpus or second generator is introduced.
Thirty-seven protected files across Core, mutators, ranking, Hashcat, Jobs,
persistence, application and intelligence/planning.py are byte-identical to base.
score-v1, diverse-v1, candidate-family-v1, caps and source presets are unchanged.

## 3. Services before and after

Seven original profiles/knowledge records stay first, with identical values and
order: wordpress, mysql, postgresql, mssql, windows-ad, grafana, rabbitmq.
Append exactly zabbix, sonarqube, jenkins, tomcat, redis and opensearch: thirteen
profiles and thirteen knowledge records. No substitute or extra product added.

## 4. Documented credentials before and after

Two original pairs remain byte-for-byte identical, including all metadata:
Grafana's initial admin/admin and RabbitMQ's restricted initial guest/guest.
Add Zabbix Admin/zabbix and SonarQube Server admin/admin, each restricted below.
Four pairs overall is an inventory, not a quality, coverage or effectiveness
metric. Four new products deliberately have evidence without an associated pair.
The independent six usernames/six passwords in common-v1 remain unchanged.

## 5. Source evidence matrix

All new official sources were opened and reviewed on **2026-10-16**. Claims below
are paraphrases of the original text, not conclusions from blogs or wordlists.
Original Grafana/RabbitMQ evidence/review scope is preserved rather than silently
recertified. URLs are static attribution, never normal-runtime requests.

| Service/category | Official evidence actually inspected | Verified fact and recorded scope | Pair decision |
| --- | --- | --- | --- |
| Zabbix / observability, monitoring | [7.4 frontend quickstart](https://www.zabbix.com/documentation/7.4/en/manual/quickstart/login), cross-checked against [current entrypoint](https://www.zabbix.com/documentation/current/en/manual/quickstart/login) | Initial frontend Admin/zabbix, capitalization significant; immediate change recommended. Scope is the 7.4 quickstart, not every release/image or agent authentication. | One initial pair, explicit 7.4 frontend scope. |
| SonarQube Server / DevSecOps, code quality | [2025.1 user management](https://docs.sonarsource.com/sonarqube-server/2025.1/instance-administration/user-management/introduction), [first setup](https://docs.sonarsource.com/sonarqube-server/2025.1/try-out-sonarqube), [installation scope](https://docs.sonarsource.com/sonarqube-server/2025.1/setup-and-upgrade/install-the-server/introduction) | Automatically created admin/admin has Administer System permission. Docker/ZIP first setup asks for a password change. Installer scope identifies Developer/Enterprise Edition. | One initial Server 2025.1 pair; exclude Cloud, Community Build, altered accounts and unreviewed releases/provisioning. |
| Jenkins / CI/CD | [Offline setup wizard](https://www.jenkins.io/doc/book/installing/offline/) | New controller unlock uses an automatically generated installation-specific secret, followed by creating the first administrator. Unversioned handbook supplies no release range. | No fixed pair. No installation file was accessed. |
| Apache Tomcat / Java administration | [11.0.27 distributed users file](https://github.com/apache/tomcat/blob/11.0.27/conf/tomcat-users.xml), [raw tag inspected](https://raw.githubusercontent.com/apache/tomcat/11.0.27/conf/tomcat-users.xml), [Tomcat 11 Manager guide](https://tomcat.apache.org/tomcat-11.0-doc/manager-howto.html) | Factory file enables no manager-gui user; commented users/placeholders are ignored. Manager requires a configured account/role. Guide viewed identified 11.0.27. | No pair from commented examples. No claim about every installed Realm/package/container. |
| Redis / database, cache | [OSS security](https://redis.io/docs/latest/operate/oss_and_stack/management/security/), [ACL](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/), [Cloud database security](https://redis.io/docs/latest/operate/rc/security/database-security/) | Redis 6+ supports named ACL users. The documented default/nopass mode allows no-AUTH connections; requirepass is operator configured. Protected mode is conditional. Cloud databases require a password and support RBAC. Latest pages provide no universal version/deployment scope. | No universal, empty-password or OSS/Cloud hybrid pair. |
| OpenSearch / search, observability | [2.12 demo configuration](https://docs.opensearch.org/2.12/security/configuration/demo-configuration/), compared with the [latest entrypoint](https://docs.opensearch.org/latest/security/configuration/demo-configuration/) | Starting in 2.12, new Security demo clusters require a custom admin password; omission fails setup. Existing configured clusters are unaffected by this installer change. | Notes only; no historical admin/admin record and no universal current default. |

The first attempted Zabbix 7.0 browser fetch failed; it is not used as evidence.
The 7.4 page and actual version shown were checked. Tomcat raw content was read
from the official repository after browser cache failures. Additional SonarQube
password-management/installation pages were inspected, but no broader edition or
release claim was inferred from them. There was no authentication against any
of these products, nor access to real Jenkins bootstrap files.

## 6. Version scopes

New Zabbix credential: `Zabbix 7.4 frontend quickstart`.
New SonarQube credential: `SonarQube Server 2025.1; Developer/Enterprise Edition initial setup`.
Both retain record_version=1 and service-catalog-v2 introduction revision.
Tomcat notes pin the factory file to 11.0.27. OpenSearch notes pin the evidence
to 2.12 and its documented transition; they do not enumerate all future releases.
Jenkins/Redis retain explicit limits on unversioned documentation. No arbitrary
semver ranges are invented. Old nullable version scopes remain exactly unchanged.

## 7. Factory, configured, demo and managed installations

Initial Zabbix/SonarQube frontend accounts are separate from changed accounts.
Jenkins bootstrap is generated, not a reusable default. Tomcat's distributed
factory file is separate from an installed configured Realm. Redis no-AUTH,
ACL credentials, requirepass and Cloud are separate modalities. OpenSearch demo
installation is separate from existing configured clusters, production security
and managed services. These distinctions appear in CLI and localized Web notes.

## 8. Facts without fixed credentials

Jenkins, Tomcat, Redis and OpenSearch have zero cataloged pairs and nonempty
source-backed authentication information. The empty state says no initial pair
is documented **in this catalog**, not that all product distributions lack initial
accounts. Historical OpenSearch defaults are deliberately omitted because this
block does not establish a separate precise historical deployment/release record.

## 9. Versioning decision

service-catalog-v1 remains an exact ordered collection available through the
existing Python lookup/CSV functions' optional keyword-only version parameter.
service-catalog-v2 is the expanded default view. Old members retain their v1
record revision; new members use v2. Unknown collections fail even with empty
filters. Validation checks record-to-service revisions and supported record_version.

Original profile IDs/operands and knowledge-v1 common operands/templates remain
immutable. Six new profiles use knowledge-v2. The unchanged summary/template
knowledge_version identifies the planning algorithm, not the expanded registry.
Existing requests freeze explicit profile IDs and captured year; new profile
operands are addressed by new stable IDs. No extra GenerationRequest field,
Job upgrade or SQLite migration is required. Future operand changes require
retained IDs/content or explicit unsupported-snapshot rejection, never silent
ID reuse. common-v1 is untouched. [ADR 0014](adr/0014-service-catalog-expansion.md)
explains the contract and its limits.

## 10. Knowledge, profiles and pairs

ServiceKnowledge describes technology/authentication/evidence. ServiceProfile
provides at most two product tokens and one contextual role per new service.
DefaultCredential is a passive associated pair. Profile roles are Admin, admin,
administrator, manager-gui, default and admin respectively; these have different
meanings and are never a guarantee that a username exists in an installation.

Tokens are product spellings: zabbix; sonarqube/sonar; jenkins; tomcat; redis;
opensearch. Zabbix's product name coincides with its initial password, but the
profile derives it from the product name, independently of the credential record.
Changing the catalog to a synthetic canary password leaves generated results
identical. No credential pair is traversed by planning/generation, even when
that service is explicitly selected.

## 11. CLI and Web

Reuse services list/--search/show and credentials list/export. Search includes
ID, display name, aliases, profile tokens and canonical English descriptions.
CI/CD, DevSecOps, Java and cache work as category terms without a new taxonomy,
model field or API. Product aliases/IDs are language independent; category search
uses English metadata, a documented limitation.

/services and /services/ID show the expanded view, references, authentication,
record/profile versions, localized pair scopes and empty states. Collection v2
is displayed separately from a legacy member's record v1. /generate?service=ID
selects exactly that ID, without starting generation or opting into weak values.
No new routes, scanner or catalog API were introduced. There are 636 translated
keys per locale, including 106 catalog/navigation keys and 34 additions.

## 12. CSV, escaping and validation

The six-column documented CSV remains service,username,password,type,source_url,
applicability. Every row retains source, restrictions and recorded version scope.
The v1 view reproduces original bytes. Common CSV remains independent lists.
Existing formula mitigation and private stage/fsync/atomic no-overwrite publication
remain unchanged, including destination/symlink/race/failure regression checks.

Validation adds bidirectional profile/knowledge membership, duplicate profile IDs,
case-insensitive alias duplicates and cross-service ambiguous aliases. Shared
contextual tokens remain valid. Same pair/scope with changed applicability prose
is duplicate. Expanded pairs need explicit scope; unsupported catalog/profile/
credential revisions fail clearly. Source/title membership, HTTPS, empty values,
controls, line breaks, restrictions and invalid Unicode remain checked; Unicode
format controls including bidi/zero-width controls are additionally rejected.
Natural-language version-scope consistency/disjointness still requires evidence
review. HTML is accepted as text and escaped by Jinja, not executed. CSV quoting
preserves exact values apart from the documented spreadsheet apostrophe.

## 13. Generation and opt-in

plan_intelligence(), GenerationService, Core, mutators and ranking are unchanged.
Only explicit service_profiles add service seeds. Corporate BR adds no services.
Documented pairs have no path into generation; socket/accessor guards and canary
replacement tests verify passivity. Independent common ready values retain their
existing explicit option/preset and provenance. No new score weights, family,
Cartesian pair generation, template algorithm or cap was added.

## 14. Synthetic counts and performance

Reproduce with `venv/bin/python -B -m tests.block14_evaluation`. All fixtures use
year 2026, partial Leet, separator !, cap 50 and budget 100. Synthetic organization
is Synthetic; service-only cases omit organization. Corporate BR uses diverse-v1,
others default score-v1 selection. Each case is a fresh process. Timing covers
normal prepare and generation separately; peak RSS includes interpreter/imports,
retained results and Core dedup, not just catalog overhead. One local observation
per fixture is not a portable speed/memory guarantee.

| Fixture | Service seeds | Tokens / roles | All template seeds | Accepted | Retained | Prepare s | Generate s | Peak RSS KiB |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| No service, organization | 0 | 0 / 0 | 12 | 969 | 100 | 0.000352 | 0.017084 | 28,004 |
| Old WordPress only | 12 | 2 / 2 | 8 | 612 | 100 | 0.000306 | 0.010228 | 27,880 |
| New Zabbix only | 4 | 1 / 1 | 2 | 204 | 100 | 0.000264 | 0.003560 | 27,880 |
| Organization + Zabbix | 8 | 1 / 1 | 18 | 1,377 | 100 | 0.000446 | 0.021747 | 28,264 |
| Corporate BR + explicit Zabbix | 8 | 1 / 1 | 18 | 2,597 | 100 | 0.000454 | 0.059939 | 28,648 |

Global-dedup diagnostic replay is separate and excluded from these timing/RSS
samples. After existing stage caps/dedup it counts raw/unique values as
969/969, 612/612, 204/204, 1377/1377 and 2651/2597 respectively: zero global
repeat removals in the first four, 54 in Corporate BR. Every retained output has
zero duplicates. These counts do not enumerate discarded intermediate expansions.
No-service and old-service configurations also ran against the exact base and
matched request, summary, warnings, result/wordlist digests, counts and dedup.

Retained families/scores reflect unchanged causality: no-service has 100
organization-role at score 44; WordPress has 100 service-role at 40; Zabbix has
100 service-role (98 at 40, two at 32); organization+Zabbix has 98 organization-role
and two organization-service, all at 48. Corporate BR retains nine observed
families, with 92 organization-role and one each of eight others. It has 93 at
48 and seven at 0/5/13/22/22/30/40. Accepted-family and retained-origin histograms,
full requests, summary, warnings and digests are recorded in evaluation.json.
Provenance uses existing service.<ID>.token/role and knowledge_template fields.
Literal seeds/budget retention are not authentication-success probabilities.

## 15. Determinism and Python compatibility

PYTHONHASHSEED 1/42/777 compare full new-profile Corporate BR results, counts,
request/plan/warnings, provenance, scores, selection and CSV across all six new
services. Historical deterministic tests and exact-base bundle comparisons remain
in the suite. All production and test Python parses with Python 3.10 grammar.
Local runtime is Python 3.13.5; real 3.10/3.11/3.12 execution for these changes
remains for the subsequent PR CI. Base main CI success is not new-feature CI.

## 16. Historical requests, Jobs and outputs

A fresh archive of the mandatory exact base was compared with final source:
24 application scenarios match full ordered GenerationResult digests, including
values, Origins, Transformations, score components, ranks/encounters and selection;
request JSON, plan summary, warnings and evaluated/retained counts also match.
They cover none/partial/full, organization variants, old services, ready/dataset/
PT-BR, profile/date/Combine, context years, Seed/Ready packs, budgets and Corporate
BR/diverse. ACME + WordPress/year 2026 remains **159,175 evaluated / Quick 100**
using the original default cap and partial-Leet configuration.

Twelve actual CLI modern/legacy × wordlist/rule-export × Leet cases match output,
debug stderr and legacy-rule bytes after normalizing only destination labels.
Four real Jobs match snapshots, preview explanations, counts and complete download
digests across restart. Nine historical Hashcat configurations match every bundle
file digest, including manifests, corporate/Leet/selector variants and partial/
literal cases. A frozen fixture copied from the base checks every original
profile/knowledge/pair/common value and ordering, plus exact v1 CSV.

## 17. Tests and real Firefox

Final prescribed full suite: **2,038 passed in 483.25s**, no failures/errors/skips,
including actual Hashcat 6.2.6 stdout checks. All 1,954 historical nodes and 84 new
cases pass. The focused catalog/Web/Jobs/audit suite also passed 259 tests before
the final cardinality adaptation and strengthened canary assertion; the complete
run validates the final test/source state.

```bash
export TMPDIR=/home/sanmirg/mimic/venv/block14-validation-tmp
PYTHONDONTWRITEBYTECODE=1 venv/bin/python -B -m pytest \
  -q -p no:cacheprovider -ra --durations=25
```

The temporary root is ignored local test storage on disk; the normal /tmp mount
is RAM-backed. This changes no candidate-generation settings or test assertions.

All 1,954 original test node IDs are retained; 84 cases were added. Historical
fixed-cardinality assertions now explicitly test the preserved v1 view/prefix or
the new exact translation count; old per-profile behavior assertions are retained.
Tests cover every new service, official pair conditions, no-fixed-pair notes,
versions, aliases/search, serialization, CSV/no-overwrite, localization/escaping,
profile passivity and opt-in, score/family equality, API/Jobs/restart and hash seeds.

Actual Firefox ESR/Marionette passed 108 cases: nine catalog paths (list, common,
empty search and six details) × PT-BR/EN × dark/light × 375/768/1440px.
Checked locale/theme/width, document overflow, long references, expected pair counts,
source links and local script/CSS resources. Real keyboard search and Enter
navigation passed; a hostile search stayed inert, generation selected Jenkins
alone and no Job was created. Mobile dark/light screenshots were retained and
visually inspected. Credential tables retain existing local horizontal scrolling.
Inherited CSRF/CSP and theme tests stay in the complete suite.

The first post-change full run had five historical seven-profile cardinality
assertions and 63 errors from one cold Hashcat fixture startup timeout during
parallel local verification. The assertions were adapted to the exact preserved
prefix; no Hashcat code/timeout/test was relaxed. A concurrent installed Hashcat
smoke also timed out. These attempts are retained as failed evidence and are not
counted as successful validation. An isolated /tmp rerun passed 1,975 tests but repeated the same fixture timeout.
Only this task's failed-run temporary fixture trees and disposable Firefox profile
were removed; diagnostic logs and screenshots were preserved. The fixture then
passed alone in 26.54s. The definitive complete rerun places temporary fixtures
on disk via TMPDIR=venv/block14-validation-tmp, avoiding the RAM-backed /tmp.
No test, timeout, backend or production limit was changed.

## 18. Offline wheel, sdist and external installation

Offline wheel and sdist built successfully with `python -m build --no-isolation`
from a separate source copy, without downloading dependencies. Both installed
successfully with --no-index --no-deps --no-build-isolation into a fresh physical
venv at /var/tmp/mimic14-installed, outside the checkout. Existing dependencies
were copied locally; final installed MIMIC modules all resolve under that venv.
An earlier RAM-backed temporary venv was replaced for the definitive checks.

Both installed artifacts pass CLI list/show for all six additions, identical CSV,
PT-BR/EN Web details, generation preview, API/Jobs with explicit Zabbix and Corporate
BR/diverse, completed downloads, stored snapshots/previews and restart. The installed
new-service CLI also reproduces the checkout's 84-output synthetic cap-20 wordlist
from a /tmp working directory. Both pip check runs report no broken requirements.

Both installed CLI Hashcat exports use the original Synthetic Aa/no-Intelligence/
none/2025:2026 configuration and --hashcat-verify. Real Hashcat 6.2.6 emits all 106
retained values with zero missing, extra or duplicate values; manifests say
exact-set with complete coverage. This is candidate-only stdout, without hashes
or authentication. These definitive installed checks run sequentially.

All 103 runtime files match source, final wheel, final sdist and installed bytes.
Both old/new test fixtures are included in sdist; operator scripts are excluded.
The installed/default CSV SHA-256 is
`022ecfc8b157efd9ed3b5bf05629112e3d87039dabaef0e66620523d22091b0d`.
Artifact SHA-256 values are recorded in packaging/resources-final.json. Build logs,
wheel/sdist install/smoke logs and both pip-check outputs are under /tmp/mimic14.

MANIFEST.in retains the existing workplace fixture and includes the new v1 golden
fixture for source-distribution tests. No new dependency or metadata requirement.
The inherited setuptools license-table deprecation remains unrelated to this
block. Normal runtime still has no external documentation/network dependency.

## 19. Changed files

Runtime/adapters: mimic/intelligence/builtins.py, catalog.py and models.py;
mimic/cli.py; mimic/web/routes.py, i18n.py and templates/services.html.
Packaging/docs: MANIFEST.in, README.md, docs/BACKLOG.md, this report and ADR 0014.
New tests/resources: tests/test_service_catalog_expansion.py,
tests/block14_evaluation.py and tests/fixtures/service-catalog-v1.json.
Historical cardinality/version-view assertions: tests/test_service_catalog.py,
test_web_services.py, test_gate10_audit.py, test_gate12_5_audit.py and
test_password_intelligence.py. No Core/mutator/ranking/Job/schema/Hashcat changes.

## 20. Limitations

Finite manual source review does not establish all releases, images or deployed
configurations. Unversioned Jenkins/Redis sources and moving guide URLs require
future re-review. No historical OpenSearch pair is claimed. Scope disjointness
requires human/source review. Profile IDs rely on immutable packaged content,
not a request digest of built-in operands. Category search uses English canonical
descriptions. Synthetic timing/RSS and family counts make no effectiveness or
success-probability claim. Future PR CI must execute supported runtimes.
Raw evidence under /tmp is local and not committed durability; reusable regression
code and the evidence matrix are retained in this repository.

## 21. Final working tree and scope

Branch remains feat/service-catalog-expansion at the exact required HEAD.
Fifteen tracked files are modified and five intended new files are untracked;
three additional untracked files are the preserved operator scripts. All work is
unstaged. Final diff/whitespace/status/stat/name checks and new-file inspection
are recorded under /tmp/mimic14. No unexpected source/artifact file is present.

Initial/final SHA-256 checks preserve mimic_lab_web.py, mimic_offline_lab.py and
mimic_offline_lab_corrigido.py. They were not executed, edited or staged. No commit,
push or merge. Blocks 15–21 roadmap text/scope/order equals the exact base; Block
15 was not started. BACKLOG marks Block 13 merged by PR #18 and Block 14 pending Gate.

## 22. Decision

The finite expansion is supported by official evidence, explicit initial/setup
restrictions, preserved historical views and representative byte/metadata parity.
The complete suite, real browser matrix, deterministic outputs and independent
offline installed artifacts pass. Ready for independent Gate 14 review within the
stated scopes; supported-runtime PR CI remains subsequent.

**READY FOR GATE 14**

## 23. Independent Gate 14 follow-up (2026-10-16)

The implementation-stage results above are retained as historical evidence.
The [independent Gate 14 audit](GATE14_AUDIT.md) rechecked official sources,
versioned records, 77 exact-base generation scenarios, eight actual old Jobs,
three hash seeds, 132 Firefox layouts and two fresh external package installs.
It reproduced and fixed one Low-severity raw descriptor leak when CSV fdopen
fails, with failing-before/passing-after tests. No catalog fact or generation,
ranking, persistence or Hashcat contract changed during the Gate.

Final Gate suite: **2,096 passed in 416.60 seconds**, including all 1,954
historical node IDs. Installed wheel/sdist both passed real Hashcat verification
with 106 values, no missing/extra/duplicates, complete coverage and exact-set.
The Gate report supersedes the pending-review status above; no commit, push,
merge or staging was performed. Blocks 15–21 remain unchanged.
