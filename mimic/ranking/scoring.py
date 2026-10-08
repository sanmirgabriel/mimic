"""score-v1: only recorded causal metadata and a captured reference year."""
from types import MappingProxyType

from mimic.core.candidate import Candidate
from mimic.ranking.models import CandidateScore, ScoreComponent

ORIGIN_WEIGHTS = MappingProxyType({"ready_candidate": 50, "explicit": 32, "target": 30,
    "organization": 22, "service": 14, "corporate_role": 10, "common_number": 8,
    "dataset": 4, "ptbr": 5})
ORIGIN_CAPS = MappingProxyType({**ORIGIN_WEIGHTS, "target": 60, "organization": 44, "service": 28,
                              "recent_year": 16})
YEAR_WEIGHTS = (16, 13, 10, 7)
TRANSFORMATION_WEIGHTS = MappingProxyType({"knowledge_template": 4, "leet": -2, "affix": 0,
    "combine": -4, "reverse": -12, "organization_domain_label": -1})
CASE_WEIGHTS = MappingProxyType({"original": 0, "title": -1, "lower": -1, "upper": -2})


def score_candidate(candidate: Candidate, reference_year: int | None = None) -> CandidateScore:
    components: list[ScoreComponent] = []
    seen_fields: set[tuple[str, str]] = set()
    totals: dict[str, int] = {}
    # dict preserves first causal encounter; never iterate a set for output.
    for origin in dict.fromkeys(candidate.origins):
        source, field = origin.source, origin.field
        semantic = field.rsplit(":", 1)[-1] if source == "context_file" else field
        category = None
        weight = 0
        if source == "ready_candidate":
            category = "ready_candidate"
        elif source in {"manual", "cli", "explicit"}:
            category = "explicit"
        elif source in {"profile", "target", "context_file"}:
            category = "target"
            semantic = "nome" if semantic == "name" else semantic
        elif source == "organization":
            category = "organization"
        elif source == "dataset":
            category = "ptbr" if field.startswith("ptbr.") else "dataset"
        elif source == "knowledge":
            if field.startswith("service.") and field.endswith((".token", ".role")):
                category = "service"
            elif field == "role":
                category = "corporate_role"
            elif field == "common_number":
                category = "common_number"
            elif field == "recent_year":
                category = "recent_year"
                if reference_year is not None and origin.value.isdecimal():
                    offset = reference_year - int(origin.value)
                    weight = YEAR_WEIGHTS[offset] if 0 <= offset < len(YEAR_WEIGHTS) else 0
        if category is None:
            continue
        # Multiple values/aliases/paths in a semantic field cannot inflate it.
        key = (category, semantic) if category in {"target", "organization", "service"} else (category, "")
        if key in seen_fields:
            continue
        seen_fields.add(key)
        if category != "recent_year":
            weight = ORIGIN_WEIGHTS[category]
        remaining = ORIGIN_CAPS[category] - totals.get(category, 0)
        delta = min(weight, remaining)
        totals[category] = totals.get(category, 0) + delta
        description = f"Recorded {source}.{field}={origin.value}"
        if category == "recent_year":
            description += f"; reference year {reference_year}; recent-year bonus {weight}"
        if delta < weight:
            description += f"; category cap {ORIGIN_CAPS[category]} (requested +{weight})"
        components.append(ScoreComponent(f"origin.{category}.{semantic}", delta, description))
    for step in candidate.transformations:
        if step.kind == "case":
            mode = dict(step.params).get("mode", "unknown")
            delta = CASE_WEIGHTS.get(mode, 0)
            code = f"transformation.case.{mode}"
        else:
            delta = TRANSFORMATION_WEIGHTS.get(step.kind, 0)
            code = f"transformation.{step.kind}"
        description = f"Recorded {step.kind}: " + ", ".join(f"{key}={value}" for key, value in step.params)
        components.append(ScoreComponent(code, delta, description))
    return CandidateScore(sum(component.delta for component in components), tuple(components))
