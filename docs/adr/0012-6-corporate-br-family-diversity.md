# ADR 0012.6 — Corporate BR sources and experimental family selection

Date: 2026-10-15. Status: implemented, opt-in; Gate 12.6 completed locally.

## Context and measurement before selection

The exact required base is `a0a10f19019957ec7509644a583e6f8d097d3cfd`.
`Acme Corp Brasil`, organization variants, Intelligence/year 2026, partial Leet,
default separators and cap 5,000 yields 127,241 policy-accepted candidates.
Its unchanged score-v1 Top-100/1,000/10,000 is entirely organization+role,
including forward/reverse templates. Source coverage and retained coverage are
separate problems. Ready weak values already exist; PT-BR already provides
mutable `Mudar`, `Senha`, `Acesso`, etc. No new corpus or generator is needed.

## Decision: source preset

`corporate-br` resolves to `corporate-br-v1`. Only missing options receive these
defaults: organization variants; Intelligence enabled; common numbers; four
recent years; corporate roles; mutable PT-BR; independent common ready passwords.
Services remain exactly the operator's selections. Nothing supplies invented
aliases, organization facts, global defaults, mutation settings or larger caps.

`GenerationRequest.from_dict` resolves individual missing fields. Explicit fields,
including False, override defaults. Direct Python construction can omit complete
option objects; explicitly supplied objects are complete operator choices. The
request holds the canonical preset version **and all resolved options**, including
False overrides normally omitted from historical serialization. A captured year
and the existing common-v1 version survive Job restoration. No preset is inferred
for historical JSON. Missing/False historical organization options remain off.

CLI uses nullable BooleanOptionalAction values until resolution. Web separates
candidate sources from selection, immediately checks the preset's seven source
controls with local JS, and changes to explicit configuration when a source is
edited. Server-side defaults/custom precedence also works without JS: preview
defaults, select explicit controls, then edit. Services, mutations, Policy and caps
always follow their own controls. Preview never generates candidates.

## Decision: candidate-family-v1

The fixed 12 identifiers, in precedence order, are:

1. `ready`: ready_candidate/common_password origin, without transformations.
2. `organization-role`: organization_role or reverse knowledge template.
3. `organization-service`: organization_service or reverse template.
4. `service-role`: service_role or reverse template.
5. `combined`: recorded Combine.
6. `organization-year`, `organization-number`, `organization-other`.
7. `ptbr-year`, `ptbr-number`, `ptbr-other`.
8. `other`.

Organization origins include organization fields and profile/target/context_file
company facts. PT-BR means an actual dataset origin whose field starts `ptbr.`.
Year/number requires recorded Affix plus the respective knowledge origin. Year
wins over common number when both exist; organization wins over PT-BR. Known
template precedence is independent of origin/transformation ordering. Unknown
metadata falls back to `other` or the supported known causal category. No candidate
is discarded. Family IDs never contain literal inputs, paths, organization IDs,
passwords, case stems or token values. First causal derivation wins: this classifier
does not invent alternative sources lost during Core dedup. Claimed provenance
is not external evidence of authenticity.

## Decision: diverse-v1

The default selector remains unchanged score-v1 Top-K. The opt-in selector:

1. Scans the same entire policy-accepted engine stream.
2. Scores each candidate once with unchanged score-v1/reference year.
3. Keeps a global K heap and the best candidate per fixed family.
4. Reserves family winners; if K<F, keeps the K best winners.
5. Fills remaining slots from the global heap, excluding reserved encounters.
6. Orders the final set by original score descending, encounter index ascending.

Selection metadata records family/version, `family-representative` or `score-fill`,
and selector version; Candidate, Origins, Transformations and scores are unchanged.
Rank means position in the retained set, not global score rank. At least one
candidate from every observed family is retained when K>=F. Output count is exactly
min(K,N), without fabricating candidates for N<K. Exhaustive+diverse is rejected.

For N accepted candidates and F<=12, retention uses K+F entries. Sorting/merging
uses O(K+F) additional references. O(N log(K+1) + K log(K+1) + F log(F+1)) work; the bounded
family scan is O(N) for fixed F. Candidate metadata size itself depends on input
size; these are entry bounds, not whole-process byte bounds. Historical Core
value/seed dedup remains O(N), independent of either selector. A global heap is
sufficient: excluding at most F reserved entries leaves at least K-F entries to
fill. At most F-1 original Top-K entries are displaced for K>=F, since the global
best is also its family's best. Checkpoints remain in the accepted stream, so
cancellation interrupts scanning before final publication.

Rejected alternatives: score bonuses would change score-v1 semantics; equal
round-robin family allocation could replace most high-priority candidates; fixed
percentage quotas need evidence not available here. Minimum representation is
explainable and has a small, provable displacement bound. It does **not** remove
all variant concentration, improve every prefix or guarantee any particular word.
Different K outputs need not nest: representatives are merged by score, not moved
to the front of every larger output.

## Persistence and compatibility

Only activated requests add preset/selector/family-version keys. Default ranking,
result and summary JSON retain historical shape. Job previews use a versioned
selection record inside an envelope in the existing score_components JSON cell;
the decoder exposes the original components list and a separate selection object.
Historical cells remain lists. No component/delta is appended or changed, no
Candidate metadata is repurposed, and no SQLite migration is necessary. The
existing bounded preview stores at most 200 explanations; full wordlist downloads
remain plain values. New experimental cells require this reader; backward reading
of these new cells by older software is not promised. Old Jobs/downloads/recovery
retain their original contract.

## Evaluation and consequences

Policy was fixed before the two synthetic 20-target evaluation fixtures. No
holdout results were used to tune weights, thresholds or literals. Diagnostic
Acme/Mudar examples are reported separately. The benchmark helper lives under
tests, not mimic; raw evidence lives under /tmp. See the implementation report
for full denominators, ranks, CPU/RSS, sibling shapes and losses.

In all three contexts, minimum representation changes 1 family to 9 at K>=100,
with 8 displaced original entries. Corporate-role share becomes 92%, 99.2%,
99.92% for 100/1,000/10,000. The two holdouts show 2/40 -> 6/40 Recall@100 and
8/40 -> 12/40 at 1,000/10,000, but improvements are the same two PT-BR literals
repeated across two organizations. The known Mudar/contextual diagnostic targets
remain absent from all retained lists. This is evidence of structural representation,
not proof of broadly improved effectiveness. Keep experimental and opt-in.

The combined preset increases scan work significantly. It adds no new generation
multiplication; it intentionally opts into existing sources. Quick still scans
all accepted candidates. No online attempt, remote model, corpus download, Block
13 work or roadmap replacement is included.

## Gate 12.6 follow-up

The adversarial [Gate audit](../GATE12_6_AUDIT.md) preserves the preset, classifier
and selector exactly. Input to selection is the existing Core value-deduplicated
accepted stream. Selection records now validate fixed family/reason/version IDs;
experimental envelopes validate structure/component types on write/read. Corrupt
or unsupported explanations receive controlled API/Web 409 responses, without
changing completed downloads or migrating SQLite. CLI/Web help now discloses
non-nested budget prefixes. All valid historical requests/outputs remain equal.

Synthetic construction bias and shared generic targets limit effectiveness claims;
mutable local chronology is not immutable blind-study preregistration. Fresh Gate
CPU/RSS observations differ from the implementation measurements; accepted work
and structural results reproduce. Keep the selector experimental and opt-in.
