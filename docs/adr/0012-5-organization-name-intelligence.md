# ADR 0012.5 — Organization name intelligence

Status: Gate 12.5 audited locally; ready for operator commit review. Date: 2026-10-14.
Base: `6398108f8699cd24068d06d39cf964671bab8354` (Block 12, PR #15).

## Problem and decision

The historical engine treats `acme hamburgueria` as one seed. Case changes
retain its space and cannot express `acmeHamburgueria` or an individual component.
Add a bounded lexical planner in `mimic.intelligence.organization`. Application
adapts existing company/name/alias Candidates; domain planning inserts its
noncombinable, mutable seeds after original organization seeds and before ready
sources/knowledge. The existing Generator performs Case, Leet, Affix, Reverse,
Policy, dedup and ranking. No independent password generator or numeric template
is added. The new seeds are not multiplied against service/role templates.

## Tokenization and component casing

A linear Unicode scan splits whitespace, ASCII hyphen/underscore/slash and en/em
dashes. Components contain letters, numbers and combining marks. Other punctuation
falls back to original-only planning: commas, dots, apostrophes, emoji and markup
are not stripped. This conservative policy leaves `ACME S.A.` intact rather than
inventing its components. DNS domains/labels, keywords and locations are not names.
There is no stop-word removal, translation, accent folding, Unicode normalization,
CamelCase segmentation, pair product or permutation. A one-component brand uses
its existing Case pipeline, including its historical Reverse branch.

For two to four components, emit individual original/lower/initial-title forms;
original-case, lower and all-initial-title concatenations; one concatenation per
component with just that component initial-titled over lowercase peers; and, when
the first component has at most eight characters, first-uppercase plus remaining
initial-title components. Initial-title means first codepoint uppercase and the
remaining codepoints lowercase, applied separately to each component. These are
Unicode case operations, so expansions such as `İ`/`ß` are possible; accents and
original source codepoints are retained in Origins. This supplies the four distinct
forms `acmehamburgueria`, `Acmehamburgueria`, `acmeHamburgueria`,
`AcmeHamburgueria`, plus `ACMEHamburgueria`. No 2^N enumeration is performed.

For five to eight components, individual original/initial-title forms and the
three whole-name concatenations remain; single-component title masks and the
first-uppercase pattern are omitted. For two to eight components, initials in
upper/lower case produce separate acronym rules. Digits are allowed as explicit
components/initials; they do not assert a linguistic acronym. Duplicate values
keep their first derivation.

## Limits and ordering

Only the first eight distinct explicit name values, in existing application order
(profile empresa, context empresa, organization name, aliases), are expanded.
Names above 256 codepoints receive no new seeds. All emitted values also have a
256-codepoint ceiling. Names with more than eight components receive only
original-case/lower/all-initial-title whole-name concatenations, bounded by that
ceiling. At most 24 additional seeds per name and 192 per request are allowed.
Original seeds are retained even when this additional expansion is limited.
Preview reports additional seed count, limited-name count and a fixed warning.
Gate 12.5 corrects that count when Unicode casing exceeds the output ceiling:
one name counts once even if several forms are omitted or it also uses fallback.
Unsupported punctuation produces no additional seeds, without guessing a reason
from private content. Limits apply to new expansion, not historical input lists.

Individual components precede joined forms, followed by uppercase-first and
acronyms; exact equal values retain their first rule. All-initial-title joins
precede single-component title joins. Every structural case form has its own
seed: its original Case output reaches Leet/Affix first, independently of other
case forms. Default per-stage frontier cap stays 5,000. Additional work is bounded
linearly by seed count, but the existing global dedup still has O(N) memory cost.
Reverse continues on each new seed normally. Combine never pairs these seeds.

When ready sources defer knowledge numbers, new seeds initially use the same
explicit-number stages as original context. The existing deferred replay includes
them after ready sources, with the full number list. A supplied ready value keeps
its cause ahead of a later knowledge-number affix. No source is read during preview.

## Configuration, adapters and historical Jobs

`GenerationRequest.organization_variants` is a strictly validated boolean,
default False. Missing serialized field means False forever; no runtime package
version or current organization presence changes that interpretation. True is
persisted explicitly. False is omitted by canonical serialization, preserving
historical request JSON exactly; omitted False is also the stored opt-out choice.
Summary adds its three expansion fields only for enabled requests.

Modern CLI `generate` defaults the switch on; `--no-organization-variants`
disables it, while `--organization-variants` enables it explicitly. Legacy
CLI defaults off and permits explicit activation. This toggle is independent of
`--intelligence`: explicit numeric inputs can affix structural seeds even when
knowledge numbers/years/roles are disabled. Without company/name/alias facts it
adds no seeds. One-component organizations retain historical candidate behavior.

```sh
mimic generate --organization "acme hamburgueria" --reference-year 2026 \
  --separators '@!#$' --budget exhaustive --output wordlist.txt
```

Append `--no-organization-variants` for the historical structural behavior.

The existing Web form has a checked, localized control and hidden
`organization_variants_form=1` marker. A marked POST uses checkbox presence;
any POST without this marker is historical/off. Preview/error render the resolved
choice, including unchecked state. GET exposes the modern default. Company text,
saved organizations, inherited target organizations and pasted/file context use
the same application planner. No new page or alternate generation form exists.

The existing API accepts the exact application request contract. New API clients
send `"organization_variants": true`; omitted/false remains historical/off.
The API transports raw frozen requests, so automatically enabling an omitted
field just because organization is present would make an old payload unreproducible.
No additional API marker, endpoint or implicit migration is introduced. CLI/Web
modern defaults resolve to the same explicit True consumed by API/application/Jobs.

Example modern API request (other existing options may be supplied normally):

```json
{
  "request": {
    "organization": {"name": "acme hamburgueria"},
    "organization_variants": true,
    "intelligence": {"enabled": true, "reference_year": 2026}
  }
}
```

JobManager's existing JSON roundtrip freezes True and original organization
facts. Old requests without the field regenerate historically. Completed downloads
survive restart; existing pending/running recovery semantics remain unchanged.
No database schema/version/migration is needed.

## Causal provenance and score-v1

Origins keep original source/field/value. `organization_name` records original
input, exact extracted components as JSON, component index where applicable,
component case rule, concatenate/component/acronym rule and `organization-name-v1`.
Organization-derived forms also retain organization name/ID when supplied; profile
and context forms identify their actual company input rather than assigning a
foreign organization ID. Only changed lexical values get this transformation.
Subsequent Case/Leet/Affix/Reverse steps are those really performed by the engine.
Existing first-cause dedup is unchanged and may select a prior explicit source.

Unknown transformations already receive neutral score-v1 contributions. The new
step is explained with zero delta through that existing contract; no scoring
weight/component table or ranking source is changed. Independent case seeds can
naturally have `case=original` instead of a later Case title transformation. This
is an intentional new causal history for enabled compound-name requests, not a
claim of byte compatibility or a manufactured bonus. No frequency evidence or
probability of successful authentication is asserted.

## Coverage, truncation and Top-K

With `acme hamburgueria`, reference 2026, common numbers/recent years/corporate
roles enabled and separators `@!#$`, all nine acceptance examples are generated
in exhaustive mode with none/partial leet at caps 256 and 5,000. The component
planner emits eleven additional seeds. At default cap, none evaluates 14,608
and partial evaluates 115,687; partial off evaluates 86,248.

At cap 50, common-number inputs precede recent-year inputs in historical Affix
order: `Acme123@` and `acmehamburgueria123!` survive, while the seven required
year forms do not. Full leet replaces eligible characters and does not preserve
these plain forms. Large numeric lists, separator sets and restrictive policy can
likewise reduce coverage; this is not a guarantee for every configuration.

For this organization-origin fixture, Quick 100 and Focused 1,000 retain none of
the nine acceptance examples at caps 256/5,000, despite generating all of them.
Existing organization+role templates have higher score-v1 priorities. Budgets
scan every policy-accepted candidate and cannot recover truncated frontiers.
No scoring changes are made to force literals into Top-K. Profile/context origins
may rank differently; results are source-qualified, not universal efficacy claims.

## Compatibility, performance and verification

Twenty application scenarios and two legacy/modern CLI scenarios compared against
the required base agree in disabled output bytes/order, full provenance, scores,
ranks, summaries, warnings, canonical request JSON and counters. ACME + WordPress
2026 still evaluates 159,175 and retains 100 in Quick. Block 11, Block 12, seven
services, packs, Core, mutators, ranking, API/Jobs/persistence source are unchanged.

Three fresh-process native measurements per case, partial leet, Quick and default
cap (Linux, Python 3.13.5, machine load varies):

| Synthetic scenario | Off → on engine seeds | Off → on evaluated | Median wall off → on | Median peak RSS off → on |
| --- | ---: | ---: | ---: | ---: |
| acme hamburgueria | 19 → 30 | 86,248 → 115,687 | 1.4072 → 1.8910 s | 40,696 → 40,620 KiB |
| Acme Serviços de Rede + two aliases/domain/keyword + WordPress | 104 → 133 | 447,553 → 529,101 | 7.9474 → 9.9938 s | 77,760 → 83,448 KiB |

Additional coverage has measurable CPU/scan cost. Small RSS differences are noise,
not an optimization claim. Quick does not constrain execution work. No portable
performance guarantee, real-password efficacy claim or speculative optimization.

The implementation report records original validation; [Gate 12.5](../GATE12_5_AUDIT.md)
records independent reproduction, exact candidate ranks, the Unicode disclosure
fix, 1,550 passing tests and the future diversity recommendation. Local validation
does not certify a new remote CI run on the supported Python matrix. Operator
commit/diff review, manual PR and supported-matrix CI remain subsequent.
