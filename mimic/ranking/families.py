"""candidate-family-v1: fixed, literal-free causal structural categories.

Precedence: ready without mutations; known templates (role before service);
Combine; organization; PT-BR; other. Year before common number for mixed
origins. A profile/context company is contextual organization knowledge too.
Only the first derivation that survived Core dedup is available to classify.
"""
from mimic.core.candidate import Candidate

FAMILY_VERSION = "candidate-family-v1"
FAMILIES = ("ready", "organization-role", "organization-service", "service-role",
            "combined", "organization-year", "organization-number", "organization-other",
            "ptbr-year", "ptbr-number", "ptbr-other", "other")


def candidate_family(candidate: Candidate) -> str:
    origins, steps = candidate.origins, candidate.transformations
    if not steps and any(o.source == "ready_candidate" or
                         (o.source == "knowledge" and o.field == "common_password") for o in origins):
        return "ready"
    templates = {dict(s.params).get("template") for s in steps if s.kind == "knowledge_template"}
    for template, family in (("organization_role", "organization-role"),
                             ("organization_service", "organization-service"),
                             ("service_role", "service-role")):
        if template in templates or template + "_reverse" in templates:
            return family
    if any(s.kind == "combine" for s in steps):
        return "combined"
    organization = any(o.source == "organization" or
                       (o.source in ("profile", "target", "context_file") and
                        o.field.rsplit(":", 1)[-1] == "empresa") for o in origins)
    ptbr = any(o.source == "dataset" and o.field.startswith("ptbr.") for o in origins)
    if organization or ptbr:
        fields = {o.field for o in origins if o.source == "knowledge"}
        # Origins alone do not establish that a numeric token was appended.
        affixed = any(s.kind == "affix" for s in steps)
        suffix = ("year" if affixed and "recent_year" in fields else
                  "number" if affixed and "common_number" in fields else "other")
        return ("organization-" if organization else "ptbr-") + suffix
    return "other"
